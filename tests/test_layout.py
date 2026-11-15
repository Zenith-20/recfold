import pytest

from recfold.layout import compute_levels, order_within_levels
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


def count_crossings(layers, es):
    pos = {n: i for row in layers for i, n in enumerate(row)}
    row_of = {n: r for r, row in enumerate(layers) for n in row}
    pairs = [(row_of[e.source_id], pos[e.source_id], pos[e.target_id]) for e in es
             if e.source_id in pos and e.target_id in pos and row_of[e.target_id] == row_of[e.source_id] + 1]
    crossings = 0
    for i, (r1, s1, t1) in enumerate(pairs):
        for r2, s2, t2 in pairs[i + 1:]:
            if r1 == r2 and (s1 - s2) * (t1 - t2) < 0:
                crossings += 1
    return crossings


def test_order_within_levels_empty():
    assert order_within_levels({}, []) == []


def test_order_within_levels_groups_by_level_sorted_by_id():
    assert order_within_levels({"b": 0, "a": 0, "c": 1}, []) == [["a", "b"], ["c"]]


def test_order_within_levels_removes_simple_crossing():
    levels = {"a": 0, "b": 0, "x": 1, "y": 1}
    es = edges(("a", "y"), ("b", "x"))
    layers = order_within_levels(levels, es)
    assert layers[0] == ["a", "b"]
    assert layers[1] == ["y", "x"]
    assert count_crossings(layers, es) == 0


def test_order_within_levels_keeps_every_node_exactly_once():
    levels = {"r": 0, "a": 1, "b": 1, "c": 1, "d": 2, "e": 2}
    es = edges(("r", "a"), ("r", "b"), ("r", "c"), ("a", "e"), ("c", "d"), ("b", "d"))
    layers = order_within_levels(levels, es)
    assert sorted(n for row in layers for n in row) == sorted(levels)
    assert [len(r) for r in layers] == [1, 3, 2]


def test_order_within_levels_is_deterministic():
    levels = {"r": 0, "a": 1, "b": 1, "c": 2, "d": 2}
    es = edges(("r", "a"), ("r", "b"), ("a", "d"), ("b", "c"))
    assert order_within_levels(levels, es) == order_within_levels(dict(levels), list(es))
