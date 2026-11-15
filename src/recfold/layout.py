"""Pure-Python 2D layout for recfold DAGs: assigns (x, y) pixel coordinates."""

from collections import deque
from typing import Dict, Iterable, List

from recfold.models import DagEdge, DagNode


def compute_levels(dag_nodes: Dict[str, DagNode], dag_edges: Iterable[DagEdge]) -> Dict[str, int]:
    """Return the row (level) of every node: roots are 0, others sit below all parents.

    A node's level is the length of the longest path from any root to it, so a
    shared child always appears below every caller. Edges that mention unknown
    node ids are ignored. Raises ValueError if the edges contain a cycle.
    """
    children: Dict[str, List[str]] = {node_id: [] for node_id in dag_nodes}
    indegree: Dict[str, int] = {node_id: 0 for node_id in dag_nodes}
    for edge in dag_edges:
        if edge.source_id in dag_nodes and edge.target_id in dag_nodes:
            children[edge.source_id].append(edge.target_id)
            indegree[edge.target_id] += 1

    levels = {node_id: 0 for node_id in dag_nodes}
    queue = deque(sorted(n for n, d in indegree.items() if d == 0))
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children[current]:
            levels[child] = max(levels[child], levels[current] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if visited != len(dag_nodes):
        raise ValueError("DAG contains a cycle")
    return levels
