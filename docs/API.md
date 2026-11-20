# recfold API reference

This reference describes the symbols that exist in the source package. It is
organized for two audiences:

1. [Part 1: Primary User API](#part-1-primary-user-api-recommended-entry-points)
   covers the workflow and records normally used by applications.
2. [Part 2: Low-Level and Internal Pipeline Helpers](#part-2-low-level-and-internal-pipeline-helpers)
   covers the functions used by the primary API internally.

## Domain terms

A **recursion** is a function call that occurs inside another call of the same
function or a recursive call chain. A **call tree** records each invocation as
a node and each parent-child connection as "this call invoked that call."

A **snapshot** is a best-effort copy saved at a call boundary. Entry snapshots
preserve arguments when a call begins; exit snapshots preserve results or
exception text when it finishes.

**DAG folding** is a post-hoc summary. It groups structurally matching subtrees
and represents each distinct subtree once in a **directed acyclic graph**
(DAG), meaning a graph whose connections have direction and no folded cycle.
It does not memoize the function or skip execution.

**Layout coordinates** are `(x, y)` pixel positions for node centers. The
**renderer** converts session data into graph data, SVG, HTML, and Jupyter
output. A **folded DAG** view shares matching subtrees; a **call tree** view
shows every recorded invocation separately.

There are no package-level re-exports. Import public symbols from the module
named in each section.

## Dataclass default construction

Mutable dataclass fields use `dataclasses.field(default_factory=...)` in the
source. They therefore create a new empty container for each instance:

- `CallNode.args` uses `tuple()` through `field(default_factory=tuple)`.
- `CallNode.kwargs`, `CallNode.children_ids`, `CallNode.entry_snapshot`, and
  `CallNode.exit_snapshot` use `dict` or `list` factories.
- `DagNode.incoming_edges` and `DagNode.outgoing_edges` use
  `field(default_factory=list)`.
- `TraceSession.nodes` and `TraceSession.dag_nodes` use
  `field(default_factory=dict)`.
- `TraceSession.dag_edges` uses `field(default_factory=list)`.
- `LayoutResult.positions` and `LayoutResult.levels` use
  `field(default_factory=dict)`; `LayoutResult.segments` uses
  `field(default_factory=list)`.

This distinction is important even though displayed constructor signatures
often render mutable defaults as `{}` or `[]`.

# Part 1: Primary User API (Recommended Entry Points)

## Recommended workflow

The usual workflow is:

1. Decorate a synchronous recursive function with `trace`, or call a plain
   function through `run_traced`.
2. Inspect or pass the resulting `TraceSession`.
3. Use `analyze_session` and `layout_session` or `layout_dag` when lower-level
   control is needed.
4. Render the session with `render_session` in Jupyter or `render_html` for a
   standalone file.

```python
from recfold.analyzer import analyze_session
from recfold.layout import layout_session
from recfold.renderer import render_session
from recfold.tracer import trace


@trace(max_depth=20)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


result = fibonacci(5)
session = fibonacci.last_session
analyze_session(session)
layout = layout_session(session)
widget = render_session(session, layout=layout, title="Fibonacci")

print(result)
print(session.analysis)
```

The `session` and `layout` variables are used directly here. In a Jupyter
cell, leave `widget` as the final expression or pass it to
`IPython.display.display`.

## Core data records

### `TraceSession`

Plain-language meaning: the container for one traced execution. It contains
the original call tree and, after analysis, the folded DAG and statistics.

Import and exact fields:

```python
from recfold.models import TraceSession


TraceSession(
    func_name: str,
    nodes: Dict[str, CallNode] = field(default_factory=dict),
    root_id: Optional[str] = None,
    dag_nodes: Dict[str, DagNode] = field(default_factory=dict),
    dag_edges: List[DagEdge] = field(default_factory=list),
    analysis: Optional[TraceAnalysis] = None,
)
```

- `func_name`: name of the function traced for this session.
- `nodes`: original call nodes keyed by call ID.
- `root_id`: ID of the first recorded call, or `None` for an empty session.
- `dag_nodes`: folded DAG nodes keyed by DAG ID.
- `dag_edges`: directed folded-DAG edges.
- `analysis`: post-hoc `TraceAnalysis`, or `None` before analysis.

```python
from recfold.models import TraceSession


session = TraceSession(func_name="factorial")
print(session.func_name)
print(session.nodes)
```

### `CallNode`

Plain-language meaning: one invocation in the original call tree.

```python
from recfold.models import CallNode


CallNode(
    node_id: str,
    func_name: str,
    args: Tuple[Any, ...] = field(default_factory=tuple),
    kwargs: Dict[str, Any] = field(default_factory=dict),
    result: Any = None,
    depth: int = 0,
    parent_id: Optional[str] = None,
    children_ids: List[str] = field(default_factory=list),
    entry_snapshot: Dict[str, Any] = field(default_factory=dict),
    exit_snapshot: Dict[str, Any] = field(default_factory=dict),
)
```

- `node_id`: call identifier, assigned in call-entry order.
- `func_name`: function name for this occurrence.
- `args`: copied positional arguments stored on entry.
- `kwargs`: copied keyword arguments stored on entry.
- `result`: copied result, or `None`.
- `depth`: call depth within the trace.
- `parent_id`: caller node ID, or `None` for the root.
- `children_ids`: direct child IDs in execution order.
- `entry_snapshot`: entry values and representations.
- `exit_snapshot`: exit values or exception text.

```python
from recfold.models import CallNode


node = CallNode(node_id="1", func_name="factorial", args=(5,))
print(node.node_id)
print(node.func_name)
print(node.args)
```

### `DagNode`

Plain-language meaning: one representative subtree in the folded DAG.
`call_count` says how many original call nodes were grouped into it.

```python
from recfold.models import DagNode


DagNode(
    dag_id: str,
    func_name: str,
    args_sig: str,
    call_count: int = 1,
    incoming_edges: List[DagEdge] = field(default_factory=list),
    outgoing_edges: List[DagEdge] = field(default_factory=list),
)
```

- `dag_id`: identifier used in the DAG.
- `func_name`: representative function name.
- `args_sig`: representative argument text.
- `call_count`: number of original call occurrences represented.
- `incoming_edges`: edges entering this node.
- `outgoing_edges`: edges leaving this node.

```python
from recfold.models import DagNode


node = DagNode(dag_id="d1", func_name="factorial", args_sig="(5,)", call_count=1)
print(node.dag_id)
print(node.func_name)
print(node.args_sig)
```

### `DagEdge`

Plain-language meaning: one directed connection from a caller DAG node to a
callee DAG node.

```python
from recfold.models import DagEdge


DagEdge(
    source_id: str,
    target_id: str,
    label: Optional[str] = None,
)
```

- `source_id`: caller DAG ID.
- `target_id`: callee DAG ID.
- `label`: optional display text, commonly `"x2"` when a caller invokes the
  same representative subtree twice.

```python
from recfold.models import DagEdge


edge = DagEdge(source_id="d1", target_id="d2", label="x2")
print(edge.source_id)
print(edge.target_id)
print(edge.label)
```

### `TraceAnalysis`

Plain-language meaning: summary counts for a trace and its DAG fold.

```python
from recfold.models import TraceAnalysis


TraceAnalysis(
    total_calls: int = 0,
    unique_calls: int = 0,
    max_depth: int = 0,
    redundancy_ratio: float = 0.0,
)
```

- `total_calls`: number of original reachable call nodes.
- `unique_calls`: number of folded DAG nodes.
- `max_depth`: maximum depth minus minimum depth among recorded nodes.
- `redundancy_ratio`: `(total_calls - unique_calls) / total_calls`, or `0.0`
  for an empty trace.

```python
from recfold.models import TraceAnalysis


analysis = TraceAnalysis(
    total_calls=15,
    unique_calls=6,
    max_depth=4,
    redundancy_ratio=(15 - 6) / 15,
)
print(analysis)
```

### `LayoutResult`

Plain-language meaning: the complete set of two-dimensional coordinates and
canvas dimensions needed to draw a DAG.

```python
from recfold.layout import LayoutResult


LayoutResult(
    positions: Dict[str, Tuple[float, float]] = field(default_factory=dict),
    levels: Dict[str, int] = field(default_factory=dict),
    segments: List[Tuple[str, str, float, float, float, float]] = field(default_factory=list),
    width: float = 0.0,
    height: float = 0.0,
    node_width: float = 140,
    node_height: float = 48,
)
```

- `positions`: DAG ID to `(x, y)` node-center coordinates.
- `levels`: DAG ID to top-to-bottom level.
- `segments`: source ID, target ID, and line start/end coordinates.
- `width`: drawing width in pixels.
- `height`: drawing height in pixels.
- `node_width`: node box width in pixels.
- `node_height`: node box height in pixels.

The source uses y coordinates that grow downward.

```python
from recfold.layout import LayoutResult


layout = LayoutResult(
    positions={"d1": (90.0, 44.0)},
    levels={"d1": 0},
    width=180.0,
    height=88.0,
)
print(layout.positions)
print(layout.width)
print(layout.height)
```

## Tracing entry points

### `trace`

Plain-language meaning: a decorator that wraps a synchronous recursive function
and records calls, parent-child relationships, arguments, results, and
exceptions. It traces execution; it does not memoize or speed up the function.

```python
from recfold.tracer import trace


def trace(
    func: Optional[Callable[..., Any]] = None,
    *,
    max_depth: Optional[int] = 100,
    detect_cycles: bool = True,
    max_repr_len: int = 80,
) -> Any
```

- `func`: a function when used as `@trace`, or `None` when used as
  `@trace(max_depth=...)`.
- `max_depth`: maximum call depth relative to each root call; `None` disables
  the depth guard.
- `detect_cycles`: if `True`, raises `RecursionError` when an active call has
  the same function name and representation-based argument key.
- `max_repr_len`: maximum text length used for argument/result representations.

Returns a wrapped callable. The wrapped callable has `last_session`, initially
`None` and set to the current `TraceSession` after a root call finishes.

```python
from recfold.tracer import trace


@trace(max_depth=20)
def factorial(n):
    if n < 2:
        return 1
    return n * factorial(n - 1)


answer = factorial(5)
print(answer)
print(factorial.last_session)
```

### `run_traced`

Plain-language meaning: execute a function once and return both its answer and
the recorded `TraceSession`, including for a function that was not decorated.

```python
from recfold.tracer import run_traced


def run_traced(
    func: Callable[..., Any],
    *args: Any,
    max_depth: Optional[int] = 100,
    detect_cycles: bool = True,
    max_repr_len: int = 80,
    **kwargs: Any,
) -> Tuple[Any, TraceSession]
```

- `func`: synchronous callable to execute.
- `*args`: positional arguments passed to `func`.
- `max_depth`: depth guard; `None` disables it.
- `detect_cycles`: enable representation-based repeated-active-call checking.
- `max_repr_len`: text representation limit.
- `**kwargs`: keyword arguments passed to `func`.

Returns `(result, TraceSession)`.

```python
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


answer, session = run_traced(countdown, 4)
print(answer)
print(len(session.nodes))
```

## Analysis and layout entry points

### `analyze_session`

Plain-language meaning: inspect a session's call tree, fold it into a DAG,
and replace that session's DAG fields and analysis with the new results.
The original `session.nodes` call tree remains unchanged.

```python
from recfold.analyzer import analyze_session


def analyze_session(
    session: TraceSession,
    max_len: int = 80,
) -> TraceSession
```

- `session`: call tree to analyze in place.
- `max_len`: maximum character length for DAG argument labels.

Returns the same `TraceSession` object after setting `dag_nodes`,
`dag_edges`, and `analysis`.

```python
from recfold.analyzer import analyze_session
from recfold.tracer import run_traced


def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


_, session = run_traced(fibonacci, 5)
analyzed = analyze_session(session)
print(analyzed is session)
print(session.analysis)
```

### `layout_dag`

Plain-language meaning: calculate node levels, horizontal order, pixel
coordinates, canvas dimensions, and line endpoints for a folded DAG.

```python
from recfold.layout import layout_dag


def layout_dag(
    dag_nodes: Dict[str, DagNode],
    dag_edges: Iterable[DagEdge],
    node_width: float = 140,
    node_height: float = 48,
    h_gap: float = 40,
    v_gap: float = 70,
    margin: float = 20,
) -> LayoutResult
```

- `dag_nodes`: DAG nodes keyed by DAG ID.
- `dag_edges`: directed edges.
- `node_width`: node box width.
- `node_height`: node box height.
- `h_gap`: horizontal gap between neighboring node centers.
- `v_gap`: vertical gap between levels.
- `margin`: canvas margin.

Raises `ValueError` if the edges contain a cycle.

```python
from recfold.layout import layout_dag
from recfold.models import DagEdge, DagNode


nodes = {
    "d1": DagNode(dag_id="d1", func_name="root", args_sig="()"),
    "d2": DagNode(dag_id="d2", func_name="child", args_sig="()"),
}
edges = [DagEdge(source_id="d1", target_id="d2")]
layout = layout_dag(nodes, edges)

print(layout.positions)
print(layout.width)
print(layout.height)
```

### `layout_session`

Plain-language meaning: use the DAG already stored on a `TraceSession` and
compute its layout.

```python
from recfold.layout import layout_session


def layout_session(
    session: TraceSession,
    **options: float,
) -> LayoutResult
```

- `session`: session containing `dag_nodes` and `dag_edges`.
- `options`: keyword layout options forwarded to `layout_dag`, including
  `node_width`, `node_height`, `h_gap`, `v_gap`, and `margin`.

```python
from recfold.analyzer import analyze_session
from recfold.layout import layout_session
from recfold.tracer import run_traced


def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


_, session = run_traced(fibonacci, 5)
analyze_session(session)
layout = layout_session(session, node_width=180, h_gap=50)
print(layout.positions)
```

## Rendering entry points

### `render_session`

Plain-language meaning: build a Jupyter notebook display widget that contains
the interactive call tree and folded DAG.

```python
from recfold.renderer import render_session


def render_session(
    session: TraceSession,
    layout: Optional[LayoutResult] = None,
    *,
    title: Optional[str] = None,
    height: int = 560,
) -> RecursionWidget
```

- `session`: traced or analyzed `TraceSession`.
- `layout`: optional custom layout for the folded DAG. Tree layout is derived
  separately.
- `title`: optional document and heading title.
- `height`: iframe height in pixels; must be an integer at least 320.

Returns a `RecursionWidget`.

```python
from recfold.renderer import render_session
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


_, session = run_traced(countdown, 4)
widget = render_session(session, title="Countdown", height=620)
print(type(widget).__name__)
```

In Jupyter, leave `widget` as the final expression or display it explicitly:

```python
from IPython.display import display
from recfold.renderer import render_session
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


_, session = run_traced(countdown, 4)
widget = render_session(session)
display(widget)
```

### `render_html`

Plain-language meaning: produce a complete, self-contained HTML document
containing interactive call-tree and DAG views.

```python
from recfold.renderer import render_html


def render_html(
    session: TraceSession,
    layout: Optional[LayoutResult] = None,
    *,
    title: Optional[str] = None,
) -> str
```

- `session`: traced or analyzed `TraceSession`.
- `layout`: optional layout for the folded DAG.
- `title`: optional document and visible heading.

Returns the complete HTML document as a `str`. It contains no external assets
or network requests.

```python
from pathlib import Path

from recfold.renderer import render_html
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


_, session = run_traced(countdown, 4)
html = render_html(session, title="Countdown trace")
Path("countdown.html").write_text(html, encoding="utf-8")
print(Path("countdown.html").is_file())
```

### `RecursionWidget`

Plain-language meaning: a frozen data object that stores captured HTML and
the notebook iframe height.

```python
from recfold.renderer import RecursionWidget


@dataclass(frozen=True)
class RecursionWidget:
    html: str = field(repr=False)
    height: int = 560
```

Constructors may use `RecursionWidget(html=..., height=...)`.

#### `RecursionWidget._repr_html_`

Plain-language meaning: Jupyter rich-display protocol. It returns sandboxed
iframe markup containing the captured HTML.

```python
def _repr_html_(self) -> str
```

Raises `ValueError` when `height` is not an integer or is less than 320.

#### `RecursionWidget.save`

Plain-language meaning: write the widget's captured HTML to a UTF-8 file.

```python
def save(
    self,
    path: Union[str, Path],
    *,
    overwrite: bool = False,
) -> Path
```

- `path`: destination file name or `Path`.
- `overwrite`: replace an existing file when `True`; otherwise use exclusive
  creation and leave existing files unchanged.

Returns the destination `Path`. The parent directory must exist. Existing-file
conflict raises `FileExistsError` in the default mode.

```python
from recfold.renderer import render_session
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


_, session = run_traced(countdown, 3)
widget = render_session(session)
saved = widget.save("countdown.html")
print(saved)
```

## Accessibility and text alternatives

The renderer exposes nodes as keyboard-focusable SVG buttons with accessible
labels and native tooltips. Tab moves between controls and nodes; Enter or
Space selects a node. Arrow keys pan the graph, `+` and `-` zoom, and `0` fits
it.

The **call tree** text description is: every recorded invocation is a separate
node, and each arrow goes from a caller to a call it invoked. The **folded DAG**
description is: matching subtrees share a node, the `×N` node suffix reports
the represented occurrence count, and an edge label such as `x2` reports two
representative invocations of that target by the source.

The inspector lists the selected node and each original occurrence. It exposes
call ID, depth, parent ID, arguments, result or error, and entry/exit snapshot
dictionaries. The low-level `build_render_data` function also provides a
JSON-compatible, text-oriented representation.

# Part 2: Low-Level and Internal Pipeline Helpers

These helpers are orchestrated automatically by the Part 1 entry points:
`trace`, `run_traced`, `analyze_session`, `layout_dag`, `layout_session`,
`render_session`, and `render_html`. They are documented for completeness,
inspection, debugging, and custom extensions. They are not the recommended
starting point for ordinary use.

## Tracer helpers

### `make_call_key`

```python
from recfold.tracer import make_call_key


def make_call_key(
    func_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[str, Tuple[str, ...], Tuple[Tuple[str, str], ...]]
```

Returns a hashable tuple containing the function name, positional
representations, and sorted keyword-name/representation pairs.

```python
from recfold.tracer import make_call_key


key = make_call_key("add", (1, 2), {"base": 10})
print(key)
```

### `check_recursion_guards`

```python
from recfold.tracer import check_recursion_guards


def check_recursion_guards(
    depth: int,
    max_depth: Optional[int],
    call_key: Tuple[Any, ...],
    active_keys: Set[Tuple[Any, ...]],
    detect_cycles: bool = True,
) -> None
```

Raises `RecursionError` if `depth > max_depth`, or if `detect_cycles` is true
and `call_key` is present in `active_keys`. It returns `None` otherwise.

```python
from recfold.tracer import check_recursion_guards


check_recursion_guards(
    depth=2,
    max_depth=10,
    call_key=("factorial", ("2",), ()),
    active_keys=set(),
)
print("guards passed")
```

### `start_call_node`

```python
from recfold.tracer import start_call_node


def start_call_node(
    session: TraceSession,
    node_id: str,
    func_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    depth: int,
    parent_id: Optional[str] = None,
    max_repr_len: int = 80,
) -> CallNode
```

Creates a `CallNode`, captures an entry snapshot, inserts it into
`session.nodes`, sets the root when needed, and appends the node ID to a known
parent's `children_ids`. Returns the created node.

```python
from recfold.models import TraceSession
from recfold.tracer import start_call_node


session = TraceSession(func_name="factorial")
node = start_call_node(
    session=session,
    node_id="1",
    func_name="factorial",
    args=(5,),
    kwargs={},
    depth=0,
)
print(session.root_id)
print(node.node_id)
```

### `finish_call_node`

```python
from recfold.tracer import finish_call_node


def finish_call_node(
    node: CallNode,
    result: Any = None,
    error: Optional[BaseException] = None,
    max_repr_len: int = 80,
) -> CallNode
```

Creates an exit snapshot, stores the copied result or exception text on
`node`, and returns the same node.

```python
from recfold.models import CallNode
from recfold.tracer import finish_call_node


node = CallNode(node_id="1", func_name="factorial")
finished = finish_call_node(node, result=120)
print(finished is node)
print(finished.result)
```

## Snapshot helpers

### `safe_copy`

```python
from recfold.snapshot import safe_copy


def safe_copy(value: Any) -> Any
```

Attempts `copy.deepcopy(value)`. Returns `"<uncopyable TypeName>"` if copying
raises any exception.

```python
from recfold.snapshot import safe_copy


original = [1, 2]
copied = safe_copy(original)
copied.append(3)
print(original)
print(copied)
```

### `safe_repr`

```python
from recfold.snapshot import safe_repr


def safe_repr(value: Any, max_len: int = 80) -> str
```

Attempts `repr(value)`. Truncates text to `max_len`; if `repr` raises, returns
`"<unreprable TypeName>"`.

```python
from recfold.snapshot import safe_repr


print(safe_repr([1, 2, 3]))
print(safe_repr("long text", max_len=5))
```

### `snapshot_args`

```python
from recfold.snapshot import snapshot_args


def snapshot_args(
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[Tuple[Any, ...], Dict[str, Any]]
```

Returns separate safe copies of positional and keyword arguments. It preserves
tuple/dict structure.

```python
from recfold.snapshot import snapshot_args


args, kwargs = snapshot_args(([1],), {"path": ["start"]})
print(args)
print(kwargs)
```

### `make_entry_snapshot`

```python
from recfold.snapshot import make_entry_snapshot


def make_entry_snapshot(
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    max_len: int = 80,
) -> Dict[str, Any]
```

Returns `args`, `kwargs`, `args_repr`, and `kwargs_repr` entries.

```python
from recfold.snapshot import make_entry_snapshot


snapshot = make_entry_snapshot((5,), {"memo": None})
print(snapshot)
```

### `make_exit_snapshot`

```python
from recfold.snapshot import make_exit_snapshot


def make_exit_snapshot(
    result: Any,
    error: Optional[BaseException] = None,
    max_len: int = 80,
) -> Dict[str, Any]
```

Returns `result`, `result_repr`, and `error`. When `error` is not `None`,
`error` is text in the form `"ExceptionType: exception text"`.

```python
from recfold.snapshot import make_exit_snapshot


success = make_exit_snapshot(120)
failure = make_exit_snapshot(None, error=ValueError("bad n"))
print(success)
print(failure)
```

### `snapshot_locals`

```python
from recfold.snapshot import snapshot_locals


def snapshot_locals(local_vars: Dict[str, Any]) -> Dict[str, Any]
```

Copies caller-provided local values. It skips names beginning with `"__"` and
module, function, and builtin-function objects. The tracer does not call this
automatically.

```python
from recfold.snapshot import snapshot_locals


locals_copy = snapshot_locals({"n": 5, "path": [1, 2], "__name__": "demo"})
print(locals_copy)
```

## Folding and statistics helpers

### `args_signature`

```python
from recfold.analyzer import args_signature


def args_signature(
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    max_len: int = 80,
) -> str
```

Returns display text for positional arguments followed by keyword arguments
sorted by name. A single positional argument retains tuple syntax.

```python
from recfold.analyzer import args_signature


print(args_signature((3,), {}, max_len=80))
print(args_signature((1,), {"memo": True}, max_len=80))
```

### `compute_subtree_keys`

```python
from recfold.analyzer import compute_subtree_keys


def compute_subtree_keys(
    nodes: Dict[str, CallNode],
    root_id: Optional[str],
) -> Dict[str, int]
```

Returns one structural integer key per reachable node. Matching includes
function name, full argument representation, result representation, error text,
and ordered child keys. Missing child IDs are skipped.

```python
from recfold.models import CallNode
from recfold.analyzer import compute_subtree_keys


nodes = {
    "1": CallNode(node_id="1", func_name="leaf", args=(2,), result=2),
    "2": CallNode(node_id="2", func_name="leaf", args=(2,), result=2),
}
print(compute_subtree_keys(nodes, "1"))
```

### `fold_tree`

```python
from recfold.analyzer import fold_tree


def fold_tree(
    nodes: Dict[str, CallNode],
    root_id: Optional[str],
    max_len: int = 80,
) -> Tuple[Dict[str, DagNode], List[DagEdge], Dict[str, str]]
```

Returns `(dag_nodes, dag_edges, node_to_dag)`. DAG IDs follow top-down,
left-to-right first occurrence. The final mapping maps original call IDs to
DAG IDs. An edge invoking the same target `n` times uses label `"xn"`.

```python
from recfold.analyzer import fold_tree
from recfold.models import CallNode


root = CallNode(node_id="1", func_name="root", children_ids=["2"])
leaf = CallNode(node_id="2", func_name="leaf", args=(1,))
dag_nodes, dag_edges, mapping = fold_tree(
    {"1": root, "2": leaf},
    root_id="1",
)
print(dag_nodes)
print(dag_edges)
print(mapping)
```

### `compute_max_depth`

```python
from recfold.analyzer import compute_max_depth


def compute_max_depth(nodes: Dict[str, CallNode]) -> int
```

Returns `max(node.depth) - min(node.depth)`, or `0` if `nodes` is empty.

```python
from recfold.analyzer import compute_max_depth
from recfold.models import CallNode


nodes = {
    "1": CallNode(node_id="1", func_name="root", depth=3),
    "2": CallNode(node_id="2", func_name="leaf", depth=5),
}
print(compute_max_depth(nodes))
```

### `compute_stats`

```python
from recfold.analyzer import compute_stats


def compute_stats(
    nodes: Dict[str, CallNode],
    dag_nodes: Dict[str, Any],
) -> TraceAnalysis
```

Returns total call count, unique DAG count, relative depth, and redundancy
ratio.

```python
from recfold.analyzer import compute_stats
from recfold.models import CallNode, DagNode


nodes = {"1": CallNode(node_id="1", func_name="root")}
dag_nodes = {"d1": DagNode(dag_id="d1", func_name="root", args_sig="()")}
print(compute_stats(nodes, dag_nodes))
```

## Layout helpers

### `compute_levels`

```python
from recfold.layout import compute_levels


def compute_levels(
    dag_nodes: Dict[str, DagNode],
    dag_edges: Iterable[DagEdge],
) -> Dict[str, int]
```

Returns the longest root-to-node path length for every known node. Unknown
node IDs in edges are ignored. Raises `ValueError` if the graph contains a
cycle.

```python
from recfold.layout import compute_levels
from recfold.models import DagEdge, DagNode


nodes = {
    "d1": DagNode(dag_id="d1", func_name="root", args_sig="()"),
    "d2": DagNode(dag_id="d2", func_name="child", args_sig="()"),
}
edges = [DagEdge(source_id="d1", target_id="d2")]
print(compute_levels(nodes, edges))
```

### `order_within_levels`

```python
from recfold.layout import order_within_levels


def order_within_levels(
    levels: Dict[str, int],
    dag_edges: Iterable[DagEdge],
    sweeps: int = 4,
) -> List[List[str]]
```

Returns top-to-bottom rows ordered to reduce edge crossings. Ordering starts
by sorted ID and is deterministic.

```python
from recfold.layout import order_within_levels


levels = {"d1": 0, "d2": 1}
print(order_within_levels(levels, []))
```

### `assign_coordinates`

```python
from recfold.layout import assign_coordinates


def assign_coordinates(
    layers: List[List[str]],
    node_width: float = 140,
    node_height: float = 48,
    h_gap: float = 40,
    v_gap: float = 70,
    margin: float = 20,
) -> Dict[str, Tuple[float, float]]
```

Returns a node-ID-to-center-coordinate mapping. Rows are horizontally
centered, and y coordinates grow downward.

```python
from recfold.layout import assign_coordinates


print(assign_coordinates([["d1"], ["d2"]]))
```

### `center_over_children`

```python
from recfold.layout import center_over_children


def center_over_children(
    layers: List[List[str]],
    positions: Dict[str, Tuple[float, float]],
    dag_edges: Iterable[DagEdge],
    min_step: float,
) -> Dict[str, Tuple[float, float]]
```

Returns a copy of positions with parent nodes moved toward the mean x
coordinate of their children. It preserves y values and minimum horizontal
spacing.

```python
from recfold.layout import center_over_children


positions = {"d1": (90.0, 44.0), "d2": (90.0, 162.0)}
print(center_over_children([["d1"], ["d2"]], positions, [], 180.0))
```

### `compute_canvas_size`

```python
from recfold.layout import compute_canvas_size


def compute_canvas_size(
    positions: Dict[str, Tuple[float, float]],
    node_width: float = 140,
    node_height: float = 48,
    margin: float = 20,
) -> Tuple[float, float]
```

Returns `(width, height)` in pixels needed to fit every node and margin.

```python
from recfold.layout import compute_canvas_size


print(compute_canvas_size({"d1": (90.0, 44.0)}))
```

### `edge_segments`

```python
from recfold.layout import edge_segments


def edge_segments(
    positions: Dict[str, Tuple[float, float]],
    dag_edges: Iterable[DagEdge],
    node_height: float = 48,
) -> List[Tuple[str, str, float, float, float, float]]
```

Returns one tuple per known edge containing source ID, target ID, start x,
start y, end x, and end y. Lines start at source bottom-center and end at
target top-center.

```python
from recfold.layout import edge_segments
from recfold.models import DagEdge


positions = {"d1": (90.0, 44.0), "d2": (90.0, 162.0)}
edges = [DagEdge(source_id="d1", target_id="d2")]
print(edge_segments(positions, edges))
```

## Renderer helpers

### `build_render_data`

```python
from recfold.renderer import build_render_data


def build_render_data(
    session: TraceSession,
    layout: Optional[LayoutResult] = None,
    *,
    folded: bool = True,
) -> Dict[str, Any]
```

Builds JSON-compatible graph and inspector data without changing `session`.
Only calls reachable from `session.root_id` are used. `folded=True` returns the
folded DAG; `folded=False` returns the original call tree. A supplied layout
must have exactly the selected graph's node IDs and finite positive dimensions.
Cycles or shared node IDs in the raw tree raise `ValueError`.

```python
from recfold.renderer import build_render_data
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


_, session = run_traced(countdown, 3)
dag_data = build_render_data(session)
tree_data = build_render_data(session, folded=False)
print(dag_data["stats"])
print(tree_data["mode"])
```

### `render_svg`

```python
from recfold.renderer import render_svg


def render_svg(data: Dict[str, Any]) -> str
```

Returns escaped, keyboard-focusable SVG text for data from
`build_render_data`. It includes node labels, native tooltips, arrows, and
error styling. It does not include HTML controls or the inspector.

```python
from recfold.renderer import build_render_data, render_svg
from recfold.tracer import run_traced


def countdown(n):
    if n == 0:
        return 0
    return countdown(n - 1)


_, session = run_traced(countdown, 3)
data = build_render_data(session)
svg = render_svg(data)
print(svg.startswith("<svg"))
