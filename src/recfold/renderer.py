"""Dependency-free HTML/SVG rendering of recorded recursion sessions."""

from dataclasses import asdict
import math
from typing import Any, Dict, Optional

from recfold.analyzer import args_signature, compute_stats, fold_tree
from recfold.layout import LayoutResult, layout_dag
from recfold.models import DagEdge, DagNode, TraceSession
from recfold.snapshot import safe_repr


def build_render_data(
    session: TraceSession,
    layout: Optional[LayoutResult] = None,
    *,
    folded: bool = True,
) -> Dict[str, Any]:
    """Build JSON-compatible graph and inspector data without changing session.

    The raw tree is authoritative. Only calls reachable from root_id are used;
    missing children are skipped, like analyzer.py. Cycles or shared tree-node
    IDs are rejected before folding. A supplied layout must match the selected
    graph (folded DAG by default). Arbitrary Python values become bounded text,
    never executable HTML. Inspection text is limited to 2,000 characters per
    value; original snapshots remain available on the session.
    """
    if session.nodes and session.root_id not in session.nodes:
        raise ValueError("A nonempty trace needs a valid root_id")
    reachable = {}
    pending = [session.root_id] if session.root_id in session.nodes else []
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            raise ValueError("Recorded calls must form a tree, without cycles or shared node IDs")
        node = session.nodes[node_id]
        reachable[node_id] = node
        pending.extend(c for c in reversed(node.children_ids) if c in session.nodes)

    folded_nodes, folded_edges, folded_map = fold_tree(reachable, session.root_id)
    stats = compute_stats(reachable, folded_nodes)
    if folded:
        graph_nodes, graph_edges, mapping = folded_nodes, folded_edges, folded_map
    else:
        graph_nodes = {
            i: DagNode(i, n.func_name, args_signature(n.args, n.kwargs))
            for i, n in reachable.items()
        }
        graph_edges = [
            DagEdge(i, child)
            for i, n in reachable.items()
            for child in n.children_ids if child in reachable
        ]
        mapping = {i: i for i in reachable}

    if layout is None:
        layout = layout_dag(graph_nodes, graph_edges)
    if set(layout.positions) != set(graph_nodes):
        raise ValueError("The supplied layout must contain exactly the selected graph's nodes")
    dimensions = (layout.width, layout.height, layout.node_width, layout.node_height)
    if any(not math.isfinite(v) or v <= 0 for v in dimensions):
        raise ValueError("The layout dimensions must be finite positive numbers")
    if any(not math.isfinite(v) for xy in layout.positions.values() for v in xy):
        raise ValueError("The layout coordinates must be finite numbers")

    calls: Dict[str, Any] = {i: [] for i in graph_nodes}
    for node_id, node in reachable.items():
        error = node.exit_snapshot.get("error")
        calls[mapping[node_id]].append({
            "id": node_id,
            "parent_id": node.parent_id,
            "depth": node.depth,
            "args": safe_repr(node.args, 2000),
            "kwargs": safe_repr(node.kwargs, 2000),
            "result": safe_repr(node.result, 2000),
            "error": error if isinstance(error, str) or error is None else safe_repr(error, 2000),
            "entry": {str(k): safe_repr(v, 2000) for k, v in node.entry_snapshot.items()},
            "exit": {str(k): safe_repr(v, 2000) for k, v in node.exit_snapshot.items()},
        })

    # Derive endpoints from the supplied centres so the geometry and graph
    # cannot disagree because of stale LayoutResult.segments.
    edges = []
    for edge in graph_edges:
        x1, y1 = layout.positions[edge.source_id]
        x2, y2 = layout.positions[edge.target_id]
        edges.append({
            "source": edge.source_id, "target": edge.target_id, "label": edge.label,
            "x1": x1, "y1": y1 + layout.node_height / 2,
            "x2": x2, "y2": y2 - layout.node_height / 2,
        })
    return {
        "mode": "dag" if folded else "tree",
        "func_name": session.func_name,
        "root_id": mapping.get(session.root_id),
        "stats": asdict(stats),
        "width": layout.width, "height": layout.height,
        "node_width": layout.node_width, "node_height": layout.node_height,
        "nodes": [
            {
                "id": i, "name": n.func_name, "args": n.args_sig,
                "count": n.call_count,
                "x": layout.positions[i][0], "y": layout.positions[i][1],
                "calls": calls[i],
            }
            for i, n in graph_nodes.items()
        ],
        "edges": edges,
    }
