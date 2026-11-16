"""Dependency-free HTML/SVG rendering of recorded recursion sessions."""

from dataclasses import asdict
from html import escape
import math
from typing import Any, Dict, Optional
from uuid import uuid4

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


def render_svg(data: Dict[str, Any]) -> str:
    """Draw data from build_render_data as escaped, keyboard-focusable SVG.

    IDs are unique per drawing. Long labels are shortened in the boxes, with
    full labels in native SVG tooltips. Event handling is added by render_html.
    """
    marker_id = "rf-arrow-" + uuid4().hex
    width, height = max(data["width"], 280), max(data["height"], 120)
    nw, nh = data["node_width"], data["node_height"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="rf-svg" '
        f'viewBox="0 0 {width:g} {height:g}" role="group" '
        f'aria-label="{escape(data["func_name"], quote=True)} recursion graph">',
        '<style>.rf-node rect{fill:#fff;stroke:#94a3b8;stroke-width:1.5}'
        '.rf-node{cursor:pointer;outline:none}'
        '.rf-node:hover rect,.rf-node:focus rect{stroke:#0f766e;stroke-width:3}'
        '.rf-node[aria-pressed="true"] rect{fill:#ccfbf1;stroke:#0f766e;stroke-width:3}'
        '.rf-error rect{fill:#fff1f2;stroke:#be123c}'
        '.rf-node text{fill:#172b3a;font-family:ui-monospace,monospace}'
        '.rf-edge line{stroke:#94a3b8;stroke-width:1.5}'
        '.rf-edge text{font:11px system-ui;fill:#475569;paint-order:stroke;stroke:#f8fafc;stroke-width:4px}'
        '.rf-edge.rf-connected line{stroke:#0f766e;stroke-width:2.5}'
        '</style>',
        f'<defs><marker id="{marker_id}" markerWidth="8" markerHeight="8" '
        'refX="8" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,0 L8,4 L0,8 Z" fill="#64748b"/></marker></defs>',
    ]
    for edge in data["edges"]:
        parts.append(
            f'<g class="rf-edge" data-source="{escape(edge["source"], quote=True)}" '
            f'data-target="{escape(edge["target"], quote=True)}">'
            f'<line x1="{edge["x1"]:g}" y1="{edge["y1"]:g}" '
            f'x2="{edge["x2"]:g}" y2="{edge["y2"]:g}" marker-end="url(#{marker_id})"/>'
        )
        if edge["label"]:
            parts.append(
                f'<text x="{(edge["x1"] + edge["x2"]) / 2 + 7:g}" '
                f'y="{(edge["y1"] + edge["y2"]) / 2:g}">{escape(edge["label"])}</text>'
            )
        parts.append('</g>')
    for node in data["nodes"]:
        label = f'{node["name"]}{node["args"]} — {node["count"]} call(s)'
        name = node["name"]
        suffix = f' ×{node["count"]}' if node["count"] > 1 else ""
        limit = max(4, int((nw - 20) / 7))
        name_limit = max(4, limit - len(suffix))
        name = name if len(name) <= name_limit else name[:name_limit - 1] + "…"
        args = node["args"]
        args = args if len(args) <= limit else args[:limit - 1] + "…"
        error_class = " rf-error" if any(c["error"] for c in node["calls"]) else ""
        parts.append(
            f'<g class="rf-node{error_class}" data-node-id="{escape(node["id"], quote=True)}" '
            f'transform="translate({node["x"]:g} {node["y"]:g})" '
            f'role="button" tabindex="0" aria-pressed="false" aria-label="{escape(label, quote=True)}">'
            f'<title>{escape(label)}</title>'
            f'<rect x="{-nw / 2:g}" y="{-nh / 2:g}" width="{nw:g}" height="{nh:g}" rx="8"/>'
            f'<text text-anchor="middle" y="-4" font-size="12" font-weight="600">{escape(name + suffix)}</text>'
            f'<text text-anchor="middle" y="13" font-size="11">{escape(args)}</text></g>'
        )
    if not data["nodes"]:
        parts.append('<text x="24" y="64" fill="#475569" font-family="system-ui" font-size="14">No calls recorded</text>')
    parts.append('</svg>')
    return "".join(parts)
