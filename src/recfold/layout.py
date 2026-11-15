"""Pure-Python 2D layout for recfold DAGs: assigns (x, y) pixel coordinates."""

from collections import deque
from typing import Dict, Iterable, List, Tuple

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


def _count_crossings(layers: List[List[str]], dag_edges: Iterable[DagEdge]) -> int:
    """Count edge crossings between each pair of neighbouring rows."""
    position = {n: i for row in layers for i, n in enumerate(row)}
    row_of = {n: r for r, row in enumerate(layers) for n in row}
    pairs: List[Tuple[int, int, int]] = []
    for edge in dag_edges:
        s, t = edge.source_id, edge.target_id
        if s in row_of and t in row_of and row_of[t] == row_of[s] + 1:
            pairs.append((row_of[s], position[s], position[t]))
    crossings = 0
    for i, (r1, s1, t1) in enumerate(pairs):
        for r2, s2, t2 in pairs[i + 1:]:
            if r1 == r2 and (s1 - s2) * (t1 - t2) < 0:
                crossings += 1
    return crossings


def _reorder_row(row: List[str], neighbours: Dict[str, List[str]], reference: List[str]) -> List[str]:
    """Sort a row by the average position of each node's neighbours in reference row."""
    ref_pos = {n: i for i, n in enumerate(reference)}
    current = {n: i for i, n in enumerate(row)}

    def barycenter(node: str) -> float:
        spots = [ref_pos[m] for m in neighbours.get(node, []) if m in ref_pos]
        return sum(spots) / len(spots) if spots else float(current[node])

    return sorted(row, key=lambda n: (barycenter(n), current[n], n))


def order_within_levels(
    levels: Dict[str, int],
    dag_edges: Iterable[DagEdge],
    sweeps: int = 4,
) -> List[List[str]]:
    """Return rows of node ids (top to bottom), ordered left to right to cut crossings.

    Rows start sorted by id, then barycenter sweeps (down, then up) move each
    node toward the average position of its neighbours. The ordering with the
    fewest crossings is returned; ties keep the earliest one, so the result is
    deterministic.
    """
    if not levels:
        return []
    edge_list = list(dag_edges)
    layers: List[List[str]] = [[] for _ in range(max(levels.values()) + 1)]
    for node_id in sorted(levels):
        layers[levels[node_id]].append(node_id)

    parents: Dict[str, List[str]] = {}
    kids: Dict[str, List[str]] = {}
    for edge in edge_list:
        if edge.source_id in levels and edge.target_id in levels:
            parents.setdefault(edge.target_id, []).append(edge.source_id)
            kids.setdefault(edge.source_id, []).append(edge.target_id)

    best = [list(row) for row in layers]
    best_score = _count_crossings(best, edge_list)
    for _ in range(sweeps):
        for r in range(1, len(layers)):
            layers[r] = _reorder_row(layers[r], parents, layers[r - 1])
        for r in range(len(layers) - 2, -1, -1):
            layers[r] = _reorder_row(layers[r], kids, layers[r + 1])
        score = _count_crossings(layers, edge_list)
        if score < best_score:
            best, best_score = [list(row) for row in layers], score
    return best


def assign_coordinates(
    layers: List[List[str]],
    node_width: float = 140,
    node_height: float = 48,
    h_gap: float = 40,
    v_gap: float = 70,
    margin: float = 20,
) -> Dict[str, Tuple[float, float]]:
    """Return the (x, y) centre of every node, in pixels (y grows downward).

    Row r sits at the same height for all its nodes; each row is centred on the
    widest row, with h_gap between neighbours and v_gap between rows.
    """
    if not layers:
        return {}
    step = node_width + h_gap
    widest = max(len(row) for row in layers) * step - h_gap
    positions: Dict[str, Tuple[float, float]] = {}
    for level, row in enumerate(layers):
        row_width = len(row) * step - h_gap
        start_x = margin + (widest - row_width) / 2
        y = margin + level * (node_height + v_gap) + node_height / 2
        for index, node_id in enumerate(row):
            positions[node_id] = (start_x + index * step + node_width / 2, float(y))
    return positions
