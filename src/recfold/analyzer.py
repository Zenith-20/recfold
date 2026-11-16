"""Pure-Python tree-to-DAG folding and call statistics for recfold."""

from typing import Any, Dict, List, Optional, Tuple

from recfold.models import CallNode, DagEdge, DagNode, TraceAnalysis, TraceSession
from recfold.snapshot import safe_repr

# Used when building fold keys: long values must not be cut, or two different
# calls could look the same and be merged by mistake.
_FULL_REPR = 10**9


def args_signature(args: Tuple[Any, ...], kwargs: Dict[str, Any], max_len: int = 80) -> str:
    """Return a short text label for a call's arguments, e.g. "(3,)" or "(1, k=2)".

    Positional values come first, then keyword values sorted by name. A single
    positional argument keeps the trailing comma, like Python's tuple repr.
    Each value is shortened with safe_repr(max_len).
    """
    parts = [safe_repr(a, max_len) for a in args]
    parts += [f"{name}={safe_repr(kwargs[name], max_len)}" for name in sorted(kwargs)]
    if len(args) == 1 and not kwargs:
        return f"({parts[0]},)"
    return "(" + ", ".join(parts) + ")"

def compute_subtree_keys(nodes: Dict[str, CallNode], root_id: Optional[str]) -> Dict[str, int]:
    """Return a number for every node reachable from root_id; equal numbers mean equal subtrees.

    Two calls share a key only if they have the same function name, arguments,
    result, error, and children in the same order with equal keys. So a
    memoizable call such as fib(2) gets one key wherever it appears, while an
    impure call that returned something different does not. Children ids that
    are missing from nodes are skipped. Works without recursion, so very deep
    trees are fine.
    """
    if root_id is None or root_id not in nodes:
        return {}
    table: Dict[Tuple[Any, ...], int] = {}
    keys: Dict[str, int] = {}
    stack = [(root_id, False)]
    while stack:
        node_id, children_done = stack.pop()
        node = nodes[node_id]
        kids = [c for c in node.children_ids if c in nodes]
        if not children_done:
            stack.append((node_id, True))
            stack.extend((c, False) for c in reversed(kids) if c not in keys)
            continue
        if node_id in keys:
            continue
        content = (
            node.func_name,
            args_signature(node.args, node.kwargs, max_len=_FULL_REPR),
            safe_repr(node.result, _FULL_REPR),
            node.exit_snapshot.get("error"),
            tuple(keys[c] for c in kids),
        )
        keys[node_id] = table.setdefault(content, len(table))
    return keys