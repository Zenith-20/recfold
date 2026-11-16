"""Renderer contracts: real traces, safe output, and notebook integration."""

import copy
from html.parser import HTMLParser
import json
import os
import xml.etree.ElementTree as ET

import pytest

from recfold.layout import LayoutResult, layout_session
from recfold.models import CallNode, TraceSession
from recfold.tracer import trace


@pytest.fixture
def fib_session():
    @trace
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    fib(4)
    return fib.last_session


def test_build_render_data_folds_real_trace_without_mutating_it(fib_session):
    from recfold.renderer import build_render_data

    before = copy.deepcopy(fib_session)
    data = build_render_data(fib_session)
    assert fib_session == before
    assert data["mode"] == "dag"
    assert data["root_id"] == "d1"
    assert len(data["nodes"]) == 5
    assert len(data["edges"]) == 6
    assert data["stats"] == {
        "total_calls": 9, "unique_calls": 5, "max_depth": 3,
        "redundancy_ratio": 4 / 9,
    }
    repeated = next(n for n in data["nodes"] if n["args"] == "(2,)")
    assert repeated["count"] == 2
    assert len(repeated["calls"]) == 2
    assert all(c["result"] == "1" for c in repeated["calls"])
    assert json.loads(json.dumps(data)) == data


def test_build_render_data_tree_preserves_each_call(fib_session):
    from recfold.renderer import build_render_data

    data = build_render_data(fib_session, folded=False)
    assert data["mode"] == "tree"
    assert data["root_id"] == "1"
    assert len(data["nodes"]) == 9
    assert len(data["edges"]) == 8
    assert {n["id"] for n in data["nodes"]} == set(fib_session.nodes)
    assert all(n["count"] == 1 and len(n["calls"]) == 1 for n in data["nodes"])


def test_build_render_data_uses_supplied_layout(fib_session):
    from recfold.analyzer import analyze_session
    from recfold.renderer import build_render_data

    analyze_session(fib_session)
    layout = layout_session(fib_session, node_width=200, margin=35)
    data = build_render_data(fib_session, layout)
    assert data["width"] == layout.width
    assert data["node_width"] == 200
    assert {n["id"]: (n["x"], n["y"]) for n in data["nodes"]} == layout.positions


def test_build_render_data_empty():
    from recfold.renderer import build_render_data

    data = build_render_data(TraceSession("empty"))
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["root_id"] is None
    assert data["stats"]["total_calls"] == 0
    assert data["width"] > 0 and data["height"] > 0


def test_build_render_data_records_errors_and_uncopyable_values():
    from recfold.renderer import build_render_data

    @trace
    def fail(value):
        raise ValueError("bad <input>")

    with pytest.raises(ValueError):
        fail(iter([1]))
    data = build_render_data(fail.last_session)
    call = data["nodes"][0]["calls"][0]
    assert call["error"] == "ValueError: bad <input>"
    assert "args" in call["entry"] and "result" in call["exit"]
    json.dumps(data)


def test_build_render_data_rejects_cycles_before_folding():
    from recfold.renderer import build_render_data

    session = TraceSession("f", nodes={"1": CallNode("1", "f", children_ids=["1"])}, root_id="1")
    with pytest.raises(ValueError, match="tree"):
        build_render_data(session)


def test_build_render_data_rejects_missing_root():
    from recfold.renderer import build_render_data

    session = TraceSession("f", nodes={"1": CallNode("1", "f")})
    with pytest.raises(ValueError, match="root"):
        build_render_data(session)


def test_build_render_data_rejects_mismatched_layout(fib_session):
    from recfold.renderer import build_render_data

    with pytest.raises(ValueError, match="layout"):
        build_render_data(fib_session, LayoutResult())


def test_build_render_data_ignores_unreachable_and_missing_children(fib_session):
    from recfold.renderer import build_render_data

    fib_session.nodes["unused"] = CallNode("unused", "other")
    fib_session.nodes["1"].children_ids.append("missing")
    data = build_render_data(fib_session)
    assert data["stats"]["total_calls"] == 9


def test_build_render_data_preserves_repeated_edge_labels():
    from recfold.renderer import build_render_data

    @trace
    def leaf():
        return 1

    @trace
    def parent():
        return leaf() + leaf()

    parent()
    data = build_render_data(parent.last_session)
    assert len(data["edges"]) == 1
    assert data["edges"][0]["label"] == "x2"


def test_render_svg_draws_accessible_nodes_and_edges(fib_session):
    from recfold.renderer import build_render_data, render_svg

    data = build_render_data(fib_session)
    root = ET.fromstring(render_svg(data))
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.attrib["viewBox"] == "0 0 360 442"
    nodes = root.findall(".//s:g[@data-node-id]", ns)
    assert len(nodes) == 5
    assert all(n.attrib["role"] == "button" and n.attrib["tabindex"] == "0" for n in nodes)
    assert len(root.findall(".//s:line", ns)) == 6
    assert all(n.find("s:title", ns) is not None for n in nodes)


def test_render_svg_escapes_labels_and_node_attributes():
    from recfold.renderer import build_render_data, render_svg

    bad = '\"><script>alert("x")</script>&'
    session = TraceSession(bad, {bad: CallNode(bad, bad, args=(bad,))}, root_id=bad)
    svg = render_svg(build_render_data(session, folded=False))
    root = ET.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.findall(".//s:script", ns) == []
    assert root.find(".//s:g[@data-node-id]", ns).attrib["data-node-id"] == bad
    assert "&lt;script&gt;" in svg


def test_render_svg_empty_state_and_independent_ids(fib_session):
    from recfold.renderer import build_render_data, render_svg

    empty = render_svg(build_render_data(TraceSession("empty")))
    assert "No calls recorded" in empty
    first = ET.fromstring(render_svg(build_render_data(fib_session)))
    second = ET.fromstring(render_svg(build_render_data(fib_session)))
    ids1 = {e.attrib["id"] for e in first.iter() if "id" in e.attrib}
    ids2 = {e.attrib["id"] for e in second.iter() if "id" in e.attrib}
    assert ids1 and ids1.isdisjoint(ids2)


def test_render_svg_shows_edge_multiplicity_and_error_style():
    from recfold.renderer import build_render_data, render_svg

    @trace
    def leaf():
        raise ValueError("oops")

    @trace
    def parent():
        for _ in range(2):
            try:
                leaf()
            except ValueError:
                pass

    parent()
    svg = render_svg(build_render_data(parent.last_session))
    assert ">x2<" in svg
    assert 'class="rf-node rf-error"' in svg


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.payload = ""
        self.in_payload = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "script" and attrs.get("id") == "rf-data":
            self.in_payload = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False

    def handle_data(self, data):
        if self.in_payload:
            self.payload += data


def test_render_html_is_self_contained_with_both_views(fib_session):
    from recfold.renderer import render_html

    html = render_html(fib_session, title="My recursion")
    parser = DocumentParser()
    parser.feed(html)
    payload = json.loads(parser.payload)
    assert len(payload["dag"]["nodes"]) == 5
    assert len(payload["tree"]["nodes"]) == 9
    assert html.startswith("<!DOCTYPE html>")
    assert "My recursion" in html
    assert "Select a call" in html
    assert "JavaScript" in html  # static fallback guidance
    assert not any(tag == "script" and "src" in attrs for tag, attrs in parser.tags)
    assert not any(tag == "link" for tag, _ in parser.tags)


def test_render_html_cannot_close_script_or_inject_markup():
    from recfold.renderer import render_html

    hostile = '</script><script>window.injected=true</script><img src=x onerror="alert(1)">\u2028&'
    session = TraceSession(hostile, {"1": CallNode("1", hostile, args=(hostile,))}, root_id="1")
    html = render_html(session, title=hostile)
    parser = DocumentParser()
    parser.feed(html)
    assert len([t for t, _ in parser.tags if t == "script"]) == 2
    assert not any(t == "img" for t, _ in parser.tags)
    assert json.loads(parser.payload)["dag"]["func_name"] == hostile
    assert "\\u003c/script\\u003e" in parser.payload


def test_render_html_empty_session():
    from recfold.renderer import render_html

    html = render_html(TraceSession("empty"))
    assert "No calls recorded" in html


@pytest.fixture
def browser_page():
    """Opt in with RECFOLD_BROWSER_TESTS=1; no browser dependency for normal tests."""
    if os.environ.get("RECFOLD_BROWSER_TESTS") != "1":
        pytest.skip("Set RECFOLD_BROWSER_TESTS=1 to run optional Playwright checks")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 700})
        yield page
        browser.close()


def test_browser_graph_switch_inspect_zoom_and_pan(browser_page, fib_session):
    from recfold.renderer import render_html

    page = browser_page
    errors = []
    requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.set_content(render_html(fib_session))
    graph = page.locator('.rf-view:not([hidden]) svg')
    assert graph.locator('[data-node-id]').count() == 5
    graph.locator('[data-node-id="d3"]').click()
    assert page.locator('#rf-call option').count() == 2
    assert "Result" in page.locator('#rf-details').inner_text()
    page.locator('#rf-call').select_option("1")
    assert "Call #7" in page.locator('#rf-details').inner_text()
    original = graph.get_attribute("viewBox")
    page.get_by_role("button", name="Zoom in", exact=True).click()
    assert graph.get_attribute("viewBox") != original
    page.get_by_role("button", name="Fit graph", exact=True).click()
    assert graph.get_attribute("viewBox") == original
    box = graph.bounding_box()
    page.mouse.move(box["x"] + 12, box["y"] + 12)
    page.mouse.down()
    page.mouse.move(box["x"] + 70, box["y"] + 40)
    page.mouse.up()
    assert graph.get_attribute("viewBox") != original
    page.get_by_role("button", name="Call tree", exact=True).click()
    graph = page.locator('.rf-view:not([hidden]) svg')
    assert graph.locator('[data-node-id]').count() == 9
    first = graph.locator('[data-node-id="1"]')
    first.focus()
    first.press("Enter")
    assert first.get_attribute("aria-pressed") == "true"
    assert "Call #1" in page.locator('#rf-details').inner_text()
    assert not errors
    assert not requests


def test_browser_hostile_values_are_text_and_mobile_fits(browser_page):
    from recfold.renderer import render_html

    hostile = '</script><img src=x onerror="window.injected=true">'
    session = TraceSession("unsafe", {"1": CallNode("1", "unsafe", args=(hostile,))}, root_id="1")
    page = browser_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.set_content(render_html(session, title=hostile))
    page.locator('.rf-view:not([hidden]) [data-node-id]').click()
    assert hostile in page.locator('#rf-details').inner_text()
    assert page.locator('img').count() == 0
    assert page.evaluate('window.injected === undefined')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_widget_notebook_representation_uses_isolated_srcdoc(fib_session):
    from recfold.renderer import RecursionWidget, render_html

    document = render_html(fib_session)
    widget = RecursionWidget(document, height=620)
    parser = DocumentParser()
    parser.feed(widget._repr_html_())
    frames = [attrs for tag, attrs in parser.tags if tag == "iframe"]
    assert len(frames) == 1
    assert frames[0]["sandbox"] == "allow-scripts"
    assert frames[0]["srcdoc"] == document
    assert frames[0]["height"] == "620"
    assert frames[0]["title"]
    assert not any(tag == "script" for tag, _ in parser.tags)


@pytest.mark.parametrize("height", [0, -1, 319, 3.5, True, '500" onload="alert(1)'])
def test_widget_rejects_invalid_height(height):
    from recfold.renderer import RecursionWidget

    with pytest.raises(ValueError, match="height"):
        RecursionWidget("<html></html>", height=height)._repr_html_()


def test_browser_two_notebook_widgets_are_independent(browser_page, fib_session):
    from recfold.renderer import RecursionWidget, render_html

    page = browser_page
    html = RecursionWidget(render_html(fib_session))._repr_html_()
    page.set_content(html + html)
    first = page.frame_locator('iframe').nth(0)
    second = page.frame_locator('iframe').nth(1)
    first.get_by_role('button', name='Call tree', exact=True).click()
    assert first.locator('.rf-view:not([hidden]) [data-node-id]').count() == 9
    assert second.locator('.rf-view:not([hidden]) [data-node-id]').count() == 5
    first.locator('.rf-view:not([hidden]) [data-node-id="1"]').click()
    assert "Call #1" in first.locator('#rf-details').inner_text()
    assert second.locator('#rf-details').inner_text() == ""
    # allow-scripts without allow-same-origin must block host DOM access.
    frame = page.frames[1]
    assert frame.evaluate('''() => {
        try { return parent.document.body === null; }
        catch (error) { return error.name === 'SecurityError'; }
    }''')
