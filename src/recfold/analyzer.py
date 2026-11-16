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

def fold_tree(
    nodes: Dict[str, CallNode],
    root_id: Optional[str],
    max_len: int = 80,
) -> Tuple[Dict[str, DagNode], List[DagEdge], Dict[str, str]]:
    """Fold a call tree into a DAG where each distinct subtree appears once.

    Returns (dag_nodes, dag_edges, node_to_dag):
    - dag_nodes maps a dag id ("d1", "d2", ...) to its DagNode; ids follow the
      order in which calls are first met in a top-down, left-to-right walk,
      so the root is always "d1". call_count says how many tree calls were
      folded into the node.
    - dag_edges has one edge per (caller, callee) pair. If one call makes the
      same sub-call n > 1 times, its edge gets the label "xn".
    - node_to_dag maps every tree node id to the dag id it was folded into.
    The result never has a cycle, because a subtree can't contain itself.
    """
    keys = compute_subtree_keys(nodes, root_id)
    if not keys:
        return {}, [], {}

    dag_nodes: Dict[str, DagNode] = {}
    dag_of_key: Dict[int, str] = {}
    node_to_dag: Dict[str, str] = {}
    first_of_dag: List[str] = []
    stack = [root_id]
    while stack:
        node_id = stack.pop()
        node = nodes[node_id]
        key = keys[node_id]
        if key not in dag_of_key:
            dag_id = f"d{len(dag_nodes) + 1}"
            dag_of_key[key] = dag_id
            dag_nodes[dag_id] = DagNode(
                dag_id=dag_id,
                func_name=node.func_name,
                args_sig=args_signature(node.args, node.kwargs, max_len),
                call_count=0,
            )
            first_of_dag.append(node_id)
        dag_id = dag_of_key[key]
        dag_nodes[dag_id].call_count += 1
        node_to_dag[node_id] = dag_id
        stack.extend(c for c in reversed(node.children_ids) if c in keys)

    dag_edges: List[DagEdge] = []
    for node_id in first_of_dag:
        source = node_to_dag[node_id]
        counts: Dict[str, int] = {}
        for child_id in nodes[node_id].children_ids:
            if child_id in keys:
                target = dag_of_key[keys[child_id]]
                counts[target] = counts.get(target, 0) + 1
        for target, count in counts.items():
            edge = DagEdge(source, target, f"x{count}" if count > 1 else None)
            dag_edges.append(edge)
            dag_nodes[source].outgoing_edges.append(edge)
            dag_nodes[target].incoming_edges.append(edge)
    return dag_nodes, dag_edges, node_to_dag

def compute_max_depth(nodes: Dict[str, CallNode]) -> int:
    """Return how many levels the deepest call sits below the top call (0 if empty).

    Uses CallNode.depth, measured from the shallowest call, so a trace that
    started at depth 5 still reports depth counted from its own root.
    """
    if not nodes:
        return 0
    depths = [node.depth for node in nodes.values()]
    return max(depths) - min(depths)