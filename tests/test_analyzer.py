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