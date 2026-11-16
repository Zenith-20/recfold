"""Dependency-free HTML/SVG rendering of recorded recursion sessions."""

from dataclasses import asdict
from html import escape
import json
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


_STYLE = """
:root { color-scheme: light; font-family: system-ui, -apple-system, sans-serif;
  color: #172b3a; background: #fff; font-size: 14px; }
* { box-sizing: border-box; }
body { margin: 0; }
button, select { font: inherit; }
button { border: 1px solid #cbd5e1; border-radius: 7px; background: #fff;
  color: #172b3a; padding: 7px 11px; cursor: pointer; min-height: 36px; }
button:hover { background: #f1f5f9; }
button:focus-visible, select:focus-visible, summary:focus-visible {
  outline: 3px solid #0f766e; outline-offset: 2px; }
button[aria-pressed="true"] { color: #fff; background: #115e59; border-color: #115e59; }
[hidden] { display: none !important; }
.rf-app { display: flex; flex-direction: column; height: 100vh; min-height: 480px; }
.rf-header { display: flex; align-items: center; gap: 12px; padding: 16px 20px 12px; }
.rf-brand { background: #115e59; color: white; padding: 7px 9px; border-radius: 9px;
  font-weight: 750; letter-spacing: -.5px; }
h1 { font-size: 16px; margin: 0; overflow-wrap: anywhere; }
.rf-subtitle { margin: 3px 0 0; color: #526475; font-size: 12px; }
.rf-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  padding: 0 20px 14px; margin: 0; }
.rf-stats div { border-left: 2px solid #d4e5e2; padding-left: 10px; }
.rf-stats dt { color: #526475; font-size: 11px; }
.rf-stats dd { font-size: 20px; font-weight: 650; margin: 2px 0 0; }
.rf-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 10px 16px; border-block: 1px solid #e2e8f0; }
.rf-modes, .rf-zoom { display: flex; align-items: center; gap: 5px; }
.rf-zoom { margin-left: auto; }
#rf-zoom-label { min-width: 44px; text-align: center; font-variant-numeric: tabular-nums; font-size: 12px; }
.rf-workspace { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 280px; }
.rf-stage { min-width: 0; min-height: 260px; background: #f8fafc;
  background-image: radial-gradient(#dbe5ec .8px, transparent .8px); background-size: 18px 18px; overflow: hidden; }
.rf-view { width: 100%; height: 100%; }
.rf-svg { display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; }
.rf-svg:active { cursor: grabbing; }
.rf-inspector { border-left: 1px solid #e2e8f0; padding: 16px; overflow: auto; min-width: 0; }
.rf-inspector h2 { margin: 0 0 8px; font-size: 14px; overflow-wrap: anywhere; }
.rf-help { color: #526475; line-height: 1.5; font-size: 12px; }
.rf-inspector label { display: block; font-size: 12px; margin-bottom: 5px; }
#rf-call { width: 100%; padding: 7px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #172b3a; }
#rf-details h3 { font-size: 12px; margin: 16px 0 8px; }
#rf-details dl { margin: 0; }
#rf-details dt { font-size: 11px; font-weight: 650; color: #526475; margin-top: 10px; }
#rf-details dd { margin: 4px 0 0; }
#rf-details pre { font: 12px/1.5 ui-monospace, monospace; white-space: pre-wrap;
  overflow-wrap: anywhere; margin: 0; padding: 7px; border-radius: 5px; background: #f1f5f9; }
#rf-details .rf-error-text { color: #9f1239; background: #fff1f2; }
#rf-details details { margin-top: 12px; font-size: 12px; }
#rf-details summary { cursor: pointer; color: #115e59; padding: 4px 0; }
.rf-footer { border-top: 1px solid #e2e8f0; padding: 8px 16px; color: #526475; font-size: 11px; }
.rf-notice { margin: 0; padding: 8px 16px; background: #fffbeb; font-size: 12px; }
@media (max-width: 640px) {
  .rf-app { height: auto; min-height: 100vh; }
  .rf-header { padding: 12px; }
  .rf-stats { padding: 0 12px 12px; gap: 6px; }
  .rf-stats dd { font-size: 18px; }
  .rf-toolbar { padding: 8px; }
  .rf-workspace { display: block; }
  .rf-stage { height: 340px; }
  .rf-inspector { border-left: 0; border-top: 1px solid #e2e8f0; max-height: 360px; }
}
"""


_SCRIPT = r"""
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('rf-data').textContent);
  const views = new Map([...document.querySelectorAll('.rf-view')].map(el => [el.dataset.mode, el]));
  const details = document.getElementById('rf-details');
  const picker = document.getElementById('rf-call');
  const heading = document.getElementById('rf-inspector-title');
  const status = document.getElementById('rf-status');
  let mode = 'dag', selected = null, svg, base, view;

  function updateView() {
    svg.setAttribute('viewBox', view.join(' '));
    document.getElementById('rf-zoom-label').textContent = Math.round(base[2] / view[2] * 100) + '%';
  }
  function zoom(factor) {
    const width = Math.max(base[2] / 5, Math.min(base[2] * 5, view[2] / factor));
    const height = width * base[3] / base[2];
    view = [view[0] + (view[2] - width) / 2, view[1] + (view[3] - height) / 2, width, height];
    updateView();
  }
  function showCall(index) {
    details.replaceChildren();
    if (!selected) return;
    const call = selected.calls[index];
    if (!call) return;
    const title = document.createElement('h3');
    title.textContent = `Call #${call.id} · depth ${call.depth}`;
    details.append(title);
    const list = document.createElement('dl');
    const fields = [['Arguments', call.args], ['Keyword arguments', call.kwargs], ['Result', call.result]];
    if (call.error !== null) fields.push(['Error', call.error]);
    fields.push(['Parent call', call.parent_id === null ? 'Root call' : '#' + call.parent_id]);
    for (const [name, value] of fields) {
      const term = document.createElement('dt'), definition = document.createElement('dd');
      const text = document.createElement('pre');
      term.textContent = name; text.textContent = value;
      if (name === 'Error') text.className = 'rf-error-text';
      definition.append(text); list.append(term, definition);
    }
    details.append(list);
    for (const [name, snapshot] of [['Entry snapshot', call.entry], ['Exit snapshot', call.exit]]) {
      const disclosure = document.createElement('details'), summary = document.createElement('summary');
      const text = document.createElement('pre');
      summary.textContent = name; text.textContent = JSON.stringify(snapshot, null, 2);
      disclosure.append(summary, text); details.append(disclosure);
    }
  }
  function selectNode(id) {
    selected = data[mode].nodes.find(node => node.id === id);
    if (!selected) return;
    for (const el of svg.querySelectorAll('[data-node-id]')) {
      el.setAttribute('aria-pressed', String(el.dataset.nodeId === id));
    }
    for (const edge of svg.querySelectorAll('.rf-edge')) {
      edge.classList.toggle('rf-connected', edge.dataset.source === id || edge.dataset.target === id);
    }
    heading.textContent = selected.name + selected.args;
    document.getElementById('rf-empty-help').hidden = true;
    document.getElementById('rf-picker-wrap').hidden = false;
    picker.replaceChildren();
    selected.calls.forEach((call, index) => {
      const option = document.createElement('option');
      option.value = String(index); option.textContent = `Call #${call.id} · depth ${call.depth}`;
      picker.append(option);
    });
    status.textContent = `${selected.count} recorded call(s). Select an occurrence to inspect its saved state.`;
    showCall(0);
  }
  function switchMode(next) {
    mode = next; selected = null;
    for (const [name, el] of views) el.hidden = name !== mode;
    for (const button of document.querySelectorAll('[data-mode-button]')) {
      button.setAttribute('aria-pressed', String(button.dataset.modeButton === mode));
    }
    svg = views.get(mode).querySelector('svg');
    base = [0, 0, Math.max(data[mode].width, 280), Math.max(data[mode].height, 120)];
    view = [...base]; updateView();
    for (const el of svg.querySelectorAll('[data-node-id]')) el.setAttribute('aria-pressed', 'false');
    for (const el of svg.querySelectorAll('.rf-connected')) el.classList.remove('rf-connected');
    heading.textContent = 'Select a call';
    document.getElementById('rf-empty-help').hidden = false;
    document.getElementById('rf-picker-wrap').hidden = true;
    details.replaceChildren();
    status.textContent = mode === 'dag' ? 'Identical subtrees share a node. ×N shows recorded call count.' : 'Every recorded call has its own node, in execution-tree order.';
  }
  for (const button of document.querySelectorAll('[data-mode-button]')) {
    button.addEventListener('click', () => switchMode(button.dataset.modeButton));
  }
  picker.addEventListener('change', () => showCall(Number(picker.value)));
  document.getElementById('rf-zoom-in').addEventListener('click', () => zoom(1.25));
  document.getElementById('rf-zoom-out').addEventListener('click', () => zoom(0.8));
  document.getElementById('rf-fit').addEventListener('click', () => { view = [...base]; updateView(); });
  for (const container of views.values()) {
    const drawing = container.querySelector('svg');
    drawing.setAttribute('tabindex', '0');
    drawing.addEventListener('click', event => {
      const node = event.target.closest('[data-node-id]');
      if (node) selectNode(node.dataset.nodeId);
    });
    drawing.addEventListener('keydown', event => {
      const node = event.target.closest('[data-node-id]');
      if (node && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault(); selectNode(node.dataset.nodeId);
      } else if (event.key === '+' || event.key === '=') {
        event.preventDefault(); zoom(1.25);
      } else if (event.key === '-') {
        event.preventDefault(); zoom(0.8);
      } else if (event.key === '0') {
        event.preventDefault(); view = [...base]; updateView();
      } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
        event.preventDefault();
        const step = view[2] / 12;
        if (event.key === 'ArrowLeft') view[0] -= step;
        if (event.key === 'ArrowRight') view[0] += step;
        if (event.key === 'ArrowUp') view[1] -= step;
        if (event.key === 'ArrowDown') view[1] += step;
        updateView();
      }
    });
    let drag = null;
    drawing.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.target.closest('[data-node-id]')) return;
      const matrix = drawing.getScreenCTM();
      if (!matrix) return;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, view: [...view], scale: matrix.a };
      drawing.setPointerCapture(event.pointerId);
    });
    drawing.addEventListener('pointermove', event => {
      if (!drag || drag.id !== event.pointerId) return;
      view = [drag.view[0] - (event.clientX - drag.x) / drag.scale,
              drag.view[1] - (event.clientY - drag.y) / drag.scale, drag.view[2], drag.view[3]];
      updateView();
    });
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      drawing.addEventListener(name, () => { drag = null; });
    }
    drawing.addEventListener('wheel', event => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault(); zoom(event.deltaY < 0 ? 1.1 : 1 / 1.1);
    }, { passive: false });
  }
  switchMode('dag');
  document.getElementById('rf-script-notice').hidden = true;
})();
"""


def render_html(
    session: TraceSession,
    layout: Optional[LayoutResult] = None,
    *,
    title: Optional[str] = None,
) -> str:
    """Return an offline HTML document with tree/DAG views and state inspection.

    The optional layout applies to the folded DAG; the call tree is laid out
    separately. No external assets, JavaScript libraries, or network calls are
    used. Trace values are escaped in markup and encoded safely in inert JSON;
    the inspector inserts textContent, never trace-provided HTML.
    """
    dag = build_render_data(session, layout)
    tree = build_render_data(session, folded=False)
    payload = json.dumps({"dag": dag, "tree": tree}, ensure_ascii=True, allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    heading = escape(title if title is not None else session.func_name + " · recursion map")
    stats = dag["stats"]
    stat_html = "".join(
        f'<div><dt>{label}</dt><dd>{value}</dd></div>'
        for label, value in (
            ("Recorded calls", stats["total_calls"]),
            ("Unique subtrees", stats["unique_calls"]),
            ("Max depth", stats["max_depth"]),
            ("Repeated calls", f'{stats["redundancy_ratio"]:.0%}'),
        )
    )
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{heading}</title><style>{_STYLE}</style></head><body>'
        '<main class="rf-app"><header class="rf-header"><span class="rf-brand">recfold</span>'
        f'<div><h1>{heading}</h1><p class="rf-subtitle">Follow the calls. Find the repeated work.</p></div></header>'
        f'<dl class="rf-stats">{stat_html}</dl>'
        '<p id="rf-script-notice" class="rf-notice">If controls are inactive, trust and rerun this notebook output '
        'or open the saved HTML in a browser with JavaScript enabled.</p>'
        '<nav class="rf-toolbar" aria-label="Graph controls"><div class="rf-modes" role="group" aria-label="Graph view">'
        '<button type="button" data-mode-button="dag" aria-pressed="true">Folded DAG</button>'
        '<button type="button" data-mode-button="tree" aria-pressed="false">Call tree</button></div>'
        '<div class="rf-zoom"><button type="button" id="rf-zoom-out" aria-label="Zoom out">−</button>'
        '<output id="rf-zoom-label" aria-label="Zoom level">100%</output>'
        '<button type="button" id="rf-zoom-in" aria-label="Zoom in">+</button>'
        '<button type="button" id="rf-fit" aria-label="Fit graph">Fit</button></div></nav>'
        '<div class="rf-workspace"><section class="rf-stage" aria-label="Recursion graph">'
        f'<div class="rf-view" data-mode="dag">{render_svg(dag)}</div>'
        f'<div class="rf-view" data-mode="tree" hidden>{render_svg(tree)}</div></section>'
        '<aside class="rf-inspector" aria-label="Call inspector"><h2 id="rf-inspector-title">Select a call</h2>'
        '<p id="rf-empty-help" class="rf-help">Click a node, or focus it with Tab and press Enter, '
        'to inspect its recorded arguments and result.</p>'
        '<p id="rf-status" class="rf-help" role="status" aria-live="polite"></p>'
        '<div id="rf-picker-wrap" hidden><label for="rf-call">Recorded occurrence</label>'
        '<select id="rf-call"></select></div><div id="rf-details"></div></aside></div>'
        '<footer class="rf-footer">Drag the background to pan · + / − to zoom · 0 to fit · '
        'Arrow keys to pan · Ctrl/⌘ + scroll to zoom</footer></main>'
        f'<script type="application/json" id="rf-data">{payload}</script>'
        f'<script>{_SCRIPT}</script></body></html>'
    )
