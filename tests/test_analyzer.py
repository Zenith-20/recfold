from recfold.analyzer import (
    args_signature,
    compute_subtree_keys,
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