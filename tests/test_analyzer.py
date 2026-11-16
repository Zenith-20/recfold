from recfold.analyzer import (
    args_signature,
    compute_max_depth,
    compute_stats,
    compute_subtree_keys,
    fold_tree,
)

from recfold.analyzer import (
    args_signature,
)
from recfold.layout import compute_levels, layout_session
from recfold.models import CallNode, TraceAnalysis, TraceSession
from recfold.tracer import run_traced


def build_tree(spec):
    """Turn nested (func, args, result, [children]) tuples into a nodes dict.

    Node ids are "1", "2", ... in pre-order, like tracer.py assigns them.
    Returns (nodes, root_id).
    """
    nodes = {}

    def add(item, depth, parent_id):
        func, args, result, children = item
        node_id = str(len(nodes) + 1)
        nodes[node_id] = CallNode(
            node_id=node_id, func_name=func, args=args, result=result,
            depth=depth, parent_id=parent_id,
        )
        if parent_id is not None:
            nodes[parent_id].children_ids.append(node_id)
        for child in children:
            add(child, depth + 1, node_id)

    add(spec, 0, None)
    return nodes, "1"


def fib_spec(n):
    if n < 2:
        return ("fib", (n,), n, [])
    left, right = fib_spec(n - 1), fib_spec(n - 2)
    return ("fib", (n,), left[2] + right[2], [left, right])


# ---------- 1. args_signature ----------

def test_args_signature_single_arg_looks_like_a_tuple():
    assert args_signature((3,), {}) == "(3,)"


def test_args_signature_no_args():
    assert args_signature((), {}) == "()"


def test_args_signature_several_args_and_sorted_kwargs():
    assert args_signature((1, "a"), {"z": 2, "b": [1]}) == "(1, 'a', b=[1], z=2)"


def test_args_signature_truncates_long_values():
    sig = args_signature(("x" * 200,), {}, max_len=10)
    assert sig == "('xxxxxx...,)"

# ---------- 2. compute_subtree_keys ----------

def test_subtree_keys_empty_tree():
    assert compute_subtree_keys({}, None) == {}


def test_subtree_keys_same_call_same_key():
    nodes, root = build_tree(fib_spec(4))
    keys = compute_subtree_keys(nodes, root)
    assert set(keys) == set(nodes)
    fib2_ids = [i for i, n in nodes.items() if n.args == (2,)]
    assert len(fib2_ids) == 2
    assert keys[fib2_ids[0]] == keys[fib2_ids[1]]
    # fib(0)..fib(4): five distinct subtrees.
    assert len(set(keys.values())) == 5


def test_subtree_keys_different_results_differ():
    # An impure function: same args, different answers -> must not be merged.
    nodes, root = build_tree(("g", (), 0, [("h", (1,), "a", []), ("h", (1,), "b", [])]))
    keys = compute_subtree_keys(nodes, root)
    assert keys["2"] != keys["3"]


def test_subtree_keys_different_children_differ():
    nodes, root = build_tree(
        ("g", (), 0, [("h", (1,), 0, [("k", (), 0, [])]), ("h", (1,), 0, [])])
    )
    keys = compute_subtree_keys(nodes, root)
    assert keys["2"] != keys["4"]


def test_subtree_keys_handles_very_deep_trees():
    # Deeper than Python's default recursion limit: must not use recursion.
    spec = ("f", (0,), 0, [])
    for i in range(1, 3000):
        spec = ("f", (i,), 0, [spec])
    nodes, root = build_tree_iterative(spec)
    keys = compute_subtree_keys(nodes, root)
    assert len(keys) == 3000


def build_tree_iterative(spec):
    nodes = {}
    stack = [(spec, 0, None)]
    while stack:
        (func, args, result, children), depth, parent_id = stack.pop()
        node_id = str(len(nodes) + 1)
        nodes[node_id] = CallNode(node_id=node_id, func_name=func, args=args,
                                  result=result, depth=depth, parent_id=parent_id)
        if parent_id is not None:
            nodes[parent_id].children_ids.append(node_id)
        for child in reversed(children):
            stack.append((child, depth + 1, node_id))
    return nodes, "1"

# ---------- 3. fold_tree ----------

def dag_by_sig(dag_nodes):
    return {d.args_sig: d for d in dag_nodes.values()}


def test_fold_tree_empty():
    assert fold_tree({}, None) == ({}, [], {})


def test_fold_tree_fib4_merges_repeated_calls():
    nodes, root = build_tree(fib_spec(4))
    dag_nodes, dag_edges, node_to_dag = fold_tree(nodes, root)

    assert len(nodes) == 9
    assert len(dag_nodes) == 5
    by_sig = dag_by_sig(dag_nodes)
    assert {s: d.call_count for s, d in by_sig.items()} == {
        "(4,)": 1, "(3,)": 1, "(2,)": 2, "(1,)": 3, "(0,)": 2,
    }
    assert all(d.func_name == "fib" for d in dag_nodes.values())

    pairs = {(dag_nodes[e.source_id].args_sig, dag_nodes[e.target_id].args_sig) for e in dag_edges}
    assert pairs == {
        ("(4,)", "(3,)"), ("(4,)", "(2,)"), ("(3,)", "(2,)"),
        ("(3,)", "(1,)"), ("(2,)", "(1,)"), ("(2,)", "(0,)"),
    }
    assert len(dag_edges) == 6


def test_fold_tree_ids_and_mapping():
    nodes, root = build_tree(fib_spec(3))
    dag_nodes, _, node_to_dag = fold_tree(nodes, root)
    assert node_to_dag[root] == "d1"
    assert dag_nodes["d1"].args_sig == "(3,)"
    assert set(node_to_dag) == set(nodes)
    assert set(node_to_dag.values()) == set(dag_nodes)
    assert all(dag_id == d.dag_id for dag_id, d in dag_nodes.items())


def test_fold_tree_fills_incoming_and_outgoing_edges():
    nodes, root = build_tree(fib_spec(3))
    dag_nodes, dag_edges, _ = fold_tree(nodes, root)
    for edge in dag_edges:
        assert edge in dag_nodes[edge.source_id].outgoing_edges
        assert edge in dag_nodes[edge.target_id].incoming_edges
    assert dag_nodes["d1"].incoming_edges == []


def test_fold_tree_repeated_child_gets_one_labelled_edge():
    nodes, root = build_tree(("g", (), 0, [("h", (1,), 5, []), ("h", (1,), 5, [])]))
    dag_nodes, dag_edges, _ = fold_tree(nodes, root)
    assert len(dag_nodes) == 2
    assert len(dag_edges) == 1
    assert dag_edges[0].label == "x2"
    assert dag_by_sig(dag_nodes)["(1,)"].call_count == 2


def test_fold_tree_single_edges_have_no_label():
    nodes, root = build_tree(fib_spec(3))
    _, dag_edges, _ = fold_tree(nodes, root)
    assert all(e.label is None for e in dag_edges)


def test_fold_tree_output_is_acyclic_for_layout():
    nodes, root = build_tree(fib_spec(6))
    dag_nodes, dag_edges, _ = fold_tree(nodes, root)
    levels = compute_levels(dag_nodes, dag_edges)
    assert levels["d1"] == 0
    assert max(levels.values()) == 5  # 6->5->4->3->2->1

# ---------- 4. compute_max_depth ----------

def test_max_depth_empty():
    assert compute_max_depth({}) == 0


def test_max_depth_single_call():
    nodes, _ = build_tree(("f", (), 0, []))
    assert compute_max_depth(nodes) == 0


def test_max_depth_fib4():
    nodes, _ = build_tree(fib_spec(4))
    assert compute_max_depth(nodes) == 3


def test_max_depth_is_relative_to_shallowest_call():
    nodes, _ = build_tree(fib_spec(3))
    for node in nodes.values():
        node.depth += 5
    assert compute_max_depth(nodes) == 2

# ---------- 5. compute_stats ----------

def test_stats_empty():
    assert compute_stats({}, {}) == TraceAnalysis(0, 0, 0, 0.0)


def test_stats_fib4():
    nodes, root = build_tree(fib_spec(4))
    dag_nodes, _, _ = fold_tree(nodes, root)
    stats = compute_stats(nodes, dag_nodes)
    assert stats.total_calls == 9
    assert stats.unique_calls == 5
    assert stats.max_depth == 3
    assert abs(stats.redundancy_ratio - 4 / 9) < 1e-9


def test_stats_no_repeats_means_zero_redundancy():
    nodes, root = build_tree(("f", (2,), 0, [("f", (1,), 0, [("f", (0,), 0, [])])]))
    dag_nodes, _, _ = fold_tree(nodes, root)
    assert compute_stats(nodes, dag_nodes).redundancy_ratio == 0.0


def test_stats_matches_models_example():
    # 10 calls folded into 4 unique ones -> 60% of the calls were repeats.
    nodes = {str(i): CallNode(node_id=str(i), func_name="f") for i in range(10)}
    dag_nodes = {f"d{i}": None for i in range(4)}
    assert compute_stats(nodes, dag_nodes).redundancy_ratio == 0.6