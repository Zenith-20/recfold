"""Renderer contracts: real traces, safe output, and notebook integration."""

import copy
import json

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
