# Renderer guide

The renderer is a standard-library-only module. It accepts completed or partial
traces from the other modules and produces an interactive browser document.
All public entry points below live in `recfold.renderer`.

## Quick API reference

| Entry point | Returns | Use |
| --- | --- | --- |
| `render_session(session, layout=None, *, title=None, height=560)` | `RecursionWidget` | Display in a notebook or export |
| `render_html(session, layout=None, *, title=None)` | `str` | Standalone HTML document |
| `build_render_data(session, layout=None, *, folded=True)` | `dict` | JSON-compatible graph and inspector data |
| `render_svg(data)` | `str` | SVG for data returned by `build_render_data` |
| `widget._repr_html_()` | `str` | Jupyter rich-display protocol; normally called automatically |
| `widget.save(path, *, overwrite=False)` | `pathlib.Path` | UTF-8 standalone HTML export |

`height` is the notebook iframe height in pixels and must be an integer >= 320.
`title` changes the document title and visible heading. The default combines the
traced function name and “recursion map”.

The normal workflow needs only `render_session(session)`. Analysis and layout
are calculated internally without mutating the supplied session. The widget
captures its HTML when created; rerender after changing a session.

## JupyterHub, JupyterLab, and Notebook

The active kernel must be able to import recfold. In the notebook:

```python
%pip install -e /path/on/server/to/recfold
```

After tracing a function, either leave the widget as the final expression or
display it explicitly:

```python
from IPython.display import display
from recfold.renderer import render_session

widget = render_session(session, height=620)
display(widget)
```

IPython belongs to the notebook environment; the recfold package does not
import it or declare it as a dependency. Multiple output widgets can appear in
one notebook. Each has its own sandboxed iframe, document, CSS, and scripts.

The iframe permits scripts but does not grant same-origin access to the notebook
page. No network resources are loaded, and no kernel callbacks are needed for
interaction. Saved HTML likewise works offline.

Notebook trust settings and frontend/admin policies can suppress HTML or scripts.
Trust a notebook only if you trust its source, then rerun the visualization cell.
If a managed JupyterHub still blocks the widget, export it and open the HTML in
a regular browser. A local JupyterLab check cannot guarantee every Hub policy.

## Passing Member 5's layout

```python
from recfold.analyzer import analyze_session
from recfold.layout import layout_session
from recfold.renderer import render_session

analyze_session(session)
positions = layout_session(session, node_width=180, h_gap=50, v_gap=80)
render_session(session, positions, title="Custom spacing")
```

The supplied layout applies to the **folded DAG**. The renderer calculates the
call-tree layout separately. Layout node IDs must exactly match the folded DAG
for the current raw trace. Dimensions must be finite positive numbers, and
coordinates must be finite. A stale or mismatched layout raises `ValueError`.

The renderer uses layout node centers and box dimensions, and derives edge
endpoints from them. It does not rely on potentially stale `layout.segments`.
The drawing uses straight edges; the layout does not route them around other
nodes or guarantee zero crossings.

## What the inspector shows

Select a node by mouse, touch, or Tab followed by Enter/Space. Its incoming and
outgoing edges are highlighted. For a folded node, use “Recorded occurrence” to
choose a particular original call.

Each occurrence shows:

- Original call ID, depth, and parent call ID.
- Copied positional and keyword arguments.
- Copied result and any recorded exception text.
- Expandable entry and exit snapshot dictionaries.

Snapshots contain representations of recorded Python values. Inspector values
are limited to 2,000 characters each; graph labels are shortened to fit their
boxes. Full recorded Python objects remain in `session.nodes`. Copy failures
are shown as placeholders supplied by `snapshot.py`.

`snapshot_locals()` exists in the snapshot module but is not called by the
current tracer. The widget therefore cannot reconstruct all local-variable
changes or every step of a backtracking algorithm. Passing a mutable path as an
argument does let you inspect its saved state at each recursive entry, as shown
in the demo notebook.

## Tree, DAG, and statistics

The raw call tree is authoritative. Even if `session.dag_nodes` or
`session.analysis` already exists, the renderer derives its view from the raw
calls so a stale analysis is not displayed accidentally. A DAG-only session
without raw calls is not an input to this high-level API.

Only calls reachable from `root_id` are shown. Missing child IDs are skipped,
matching the analyzer. Unreachable nodes are excluded from renderer statistics.
A nonempty trace needs a valid root. Cyclic structures and repeated references
to the same tree-node ID raise `ValueError` before the analyzer is called.

In the **call tree**, every invocation has a separate node. In the **DAG**,
equivalent subtrees share one node. The folding rules are owned by
`analyzer.compute_subtree_keys`: function name, argument representation, result
representation, error, and ordered child subtree keys must match.

Node `×N` means N original invocations were grouped there. Edge `xN` means one
representative parent invokes that equivalent child N times; it is not a global
edge-call total.

Statistics stay the same when switching views:

```text
Recorded calls  = number of reachable original call nodes
Unique subtrees = number of folded DAG nodes
Max depth       = maximum recorded depth minus minimum recorded depth
Repeated calls  = (recorded calls - unique subtrees) / recorded calls
```

Empty traces show zero statistics and “No calls recorded”. Folding does not
perform memoization or prove that repeated work can safely be skipped.

## Inspecting partial traces and errors

```python
from recfold.tracer import trace
from recfold.renderer import render_session

@trace(max_depth=3)
def countdown(n):
    return 0 if n == 0 else countdown(n - 1)

try:
    countdown(10)
except RecursionError:
    pass

render_session(countdown.last_session, title="Depth guard: partial trace")
```

The guard rejects a call before creating its node. The partial trace contains
the already-entered calls, with errors recorded while the exception propagates.
For a decorated outermost function, `last_session` remains available after an
exception. The renderer does not swallow errors or run the function again.

## Export and lower-level use

```python
from pathlib import Path
from recfold.renderer import render_session, render_html, build_render_data, render_svg

widget = render_session(session)
saved_path = widget.save("trace.html")
# To intentionally replace that file:
widget.save(saved_path, overwrite=True)

document = render_html(session)
data = build_render_data(session)
svg = render_svg(data)
Path("trace.svg").write_text(svg, encoding="utf-8")
```

`render_svg` draws nodes, labels, arrows, and tooltips. Its inspector, view
switching, and zoom/pan handlers come from `render_html`; a bare SVG does not
contain the complete interactive UI. The HTML export contains both graphs and
their inspection data. The save destination's parent directory must exist.

Text is escaped in HTML/SVG attributes and content. Embedded JSON escapes `<`,
`>`, and `&`, including possible `</script>` strings. The inspector uses DOM
`textContent`, not HTML insertion. This protects rendering of trace text; it
does not sandbox the Python function being traced or its custom `repr` methods.

## Performance and troubleshooting

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError: recfold` | Install the checkout into the active kernel with `%pip`; verify the selected kernel |
| `ModuleNotFoundError: recfold.renderer` | Use a checkout/branch containing Member 6's renderer |
| Only `RecursionWidget(height=...)` appears | Use a notebook rich-display output, not `print(widget)` |
| Widget is blank or controls inactive | Trust and rerun the output; check iframe/script policy; try exported HTML |
| Graph is too small | Zoom in or enlarge the iframe; Fit restores the initial view |
| Long labels appear shortened | Use the tooltip and inspector; original snapshots remain in Python |
| Locals or async execution missing | These are current tracer limitations, not hidden UI controls |
| A long-input function raises a false cycle error | Review the tracer's repr-based guard; use an explicit depth bound if disabling it |
| Browser is slow on a huge trace | Reduce the input; both complete graphs and snapshots are embedded without virtualization |

The renderer deliberately leaves the tracing, snapshot, folding, and layout
algorithms in their owning modules. Fixes to those behaviors should be handled
by the corresponding team member.
