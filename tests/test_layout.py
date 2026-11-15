import pytest

from recfold.layout import compute_levels
from recfold.models import DagEdge, DagNode


def make_nodes(*ids):
    return {i: DagNode(dag_id=i, func_name="f", args_sig=f"({i})") for i in ids}


def edges(*pairs):
    return [DagEdge(source_id=s, target_id=t) for s, t in pairs]


def test_compute_levels_empty():
    assert compute_levels({}, []) == {}


def test_compute_levels_single_node():
    assert compute_levels(make_nodes("a"), []) == {"a": 0}


def test_compute_levels_chain():
    levels = compute_levels(make_nodes("a", "b", "c"), edges(("a", "b"), ("b", "c")))
    assert levels == {"a": 0, "b": 1, "c": 2}


def test_compute_levels_diamond_uses_longest_path():
    # a -> b -> d, a -> c -> d, plus shortcut a -> d: d must sit below b and c.
    nodes = make_nodes("a", "b", "c", "d")
    es = edges(("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("a", "d"))
    assert compute_levels(nodes, es) == {"a": 0, "b": 1, "c": 1, "d": 2}


def test_compute_levels_multiple_roots():
    nodes = make_nodes("a", "b", "c")
    levels = compute_levels(nodes, edges(("a", "c"), ("b", "c")))
    assert levels == {"a": 0, "b": 0, "c": 1}


def test_compute_levels_ignores_unknown_ids():
    levels = compute_levels(make_nodes("a", "b"), edges(("a", "b"), ("a", "zzz"), ("q", "b")))
    assert levels == {"a": 0, "b": 1}


def test_compute_levels_raises_on_cycle():
    nodes = make_nodes("a", "b", "c")
    with pytest.raises(ValueError):
        compute_levels(nodes, edges(("a", "b"), ("b", "c"), ("c", "b")))
