import pytest

from recfold.layout import (
    assign_coordinates,
    center_over_children,
    compute_canvas_size,
    compute_levels,
    order_within_levels,
)
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


def test_assign_coordinates_empty():
    assert assign_coordinates([]) == {}


def test_assign_coordinates_single_node_defaults():
    # margin 20, node 140x48 -> center at (20 + 70, 20 + 24)
    assert assign_coordinates([["a"]]) == {"a": (90.0, 44.0)}


def test_assign_coordinates_row_spacing_and_levels():
    pos = assign_coordinates(
        [["a"], ["b", "c"]], node_width=100, node_height=40, h_gap=20, v_gap=60, margin=10
    )
    # widest row is level 1: 100 + 20 + 100 = 220 wide
    # level 1 centre y = margin 10 + (node 40 + v_gap 60) + half node 20
    assert pos["b"] == (60.0, 130.0)
    assert pos["c"] == (180.0, 130.0)
    # level 0 is centered over the wide row
    assert pos["a"] == (120.0, 30.0)


def test_assign_coordinates_nodes_in_row_never_overlap():
    layers = [["a"], ["b", "c", "d"], ["e", "f"]]
    pos = assign_coordinates(layers, node_width=80, h_gap=10)
    for row in layers:
        xs = [pos[n][0] for n in row]
        for left, right in zip(xs, xs[1:]):
            assert right - left >= 80 + 10


def test_assign_coordinates_left_to_right_follows_row_order():
    pos = assign_coordinates([["z", "a", "m"]])
    assert pos["z"][0] < pos["a"][0] < pos["m"][0]
    assert pos["z"][1] == pos["a"][1] == pos["m"][1]


SPACING = dict(node_width=100, node_height=40, h_gap=20, v_gap=60, margin=10)


def test_center_over_children_moves_parents_to_children_mean():
    layers = [["x", "y"], ["a", "b", "c", "d"]]
    es = edges(("x", "a"), ("x", "b"), ("y", "c"), ("y", "d"))
    pos = assign_coordinates(layers, **SPACING)
    moved = center_over_children(layers, pos, es, min_step=120)
    assert moved["x"][0] == 120.0  # mean of a (60) and b (180)
    assert moved["y"][0] == 360.0  # mean of c (300) and d (420)


def test_center_over_children_keeps_rows_apart():
    layers = [["p", "q"], ["a", "b"]]
    es = edges(("p", "a"), ("p", "b"), ("q", "a"), ("q", "b"))
    pos = assign_coordinates(layers, **SPACING)
    moved = center_over_children(layers, pos, es, min_step=120)
    assert moved["q"][0] - moved["p"][0] >= 120
    assert moved["p"][0] < moved["q"][0]


def test_center_over_children_leaves_bottom_row_and_y_untouched():
    layers = [["x"], ["a", "b"]]
    pos = assign_coordinates(layers, **SPACING)
    moved = center_over_children(layers, pos, edges(("x", "a")), min_step=120)
    assert moved["a"] == pos["a"] and moved["b"] == pos["b"]
    assert all(moved[n][1] == pos[n][1] for n in pos)


def test_center_over_children_does_not_mutate_input():
    layers = [["x", "y"], ["a", "b", "c", "d"]]
    pos = assign_coordinates(layers, **SPACING)
    before = dict(pos)
    center_over_children(layers, pos, edges(("x", "a")), min_step=120)
    assert pos == before


def test_center_over_children_nodes_without_children_stay_put():
    layers = [["x", "y"], ["a", "b", "c", "d"]]
    pos = assign_coordinates(layers, **SPACING)
    moved = center_over_children(layers, pos, edges(("x", "a")), min_step=120)
    assert moved["x"][0] == 60.0  # x moves over its only child a
    assert moved["y"] == pos["y"]  # y has no children, so it stays


def test_compute_canvas_size_empty_is_just_margins():
    assert compute_canvas_size({}, margin=15) == (30.0, 30.0)


def test_compute_canvas_size_single_node_matches_default_layout():
    pos = assign_coordinates([["a"]])
    assert compute_canvas_size(pos) == (180.0, 88.0)  # 140+2*20, 48+2*20


def test_compute_canvas_size_covers_every_node_with_margin():
    layers = [["a"], ["b", "c", "d"]]
    pos = assign_coordinates(layers, **SPACING)
    width, height = compute_canvas_size(pos, node_width=100, node_height=40, margin=10)
    assert width == 10 + 3 * 100 + 2 * 20 + 10
    assert height == 10 + 40 + 60 + 40 + 10
    for x, y in pos.values():
        assert 10 <= x - 50 and x + 50 <= width - 10
        assert 10 <= y - 20 and y + 20 <= height - 10
