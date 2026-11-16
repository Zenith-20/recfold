"""Renderer contracts: real traces, safe output, and notebook integration."""

import copy
import json
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
