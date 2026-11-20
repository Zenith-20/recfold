# recfold

`recfold` is a Python package for inspecting recursive function calls in Jupyter notebooks or standalone HTML files. It records traced calls in a call tree, folds structurally matching subtrees into a directed acyclic graph (DAG), and lets you inspect arguments, return values, errors, and boundary snapshots for individual calls.

## Scope and design choices

### No third-party runtime dependencies

`recfold` uses only the Python standard library at runtime. Its visualization is generated as self-contained HTML, SVG, CSS, and JavaScript. Runtime use does not require Graphviz, native C binaries, external CDNs, browser extensions, or `ipywidgets`. Notebook display still depends on the frontend permitting sandboxed `srcdoc` iframes and inline scripts.

### Tree-to-DAG folding and redundancy metrics

Tracing records calls that pass the configured depth and repeated-active-call guards. `recfold` then folds subtrees with matching structural keys into shared DAG nodes and calculates a structural redundancy ratio:

```text
redundancy ratio = (recorded calls - unique folded subtrees) / recorded calls
```

For `fib(5)`, `recfold` records 15 calls and folds them into 6 unique subtrees. The ratio is `(15 - 6) / 15 = 0.6`, or 60%.

This is a post-hoc structural summary of the recorded trace, not an optimization. Folding does not memoize the traced function, speed up execution, or skip function calls. Recursive calls still execute, and the raw call tree remains in memory.

### Entry and exit snapshots

At call entry, `recfold` deep-copies positional and keyword arguments; at normal return, it deep-copies the result. If the function raises, the exit snapshot records the exception text. This can preserve a mutable argument, such as a backtracking path, as it appeared at each call boundary rather than exposing later mutations in earlier snapshots.

These are boundary snapshots, not a step-by-step debugger. The tracer does not automatically capture local variables or intermediate mutations. Each argument and result is copied separately; references shared across separately copied values are not preserved. Values that cannot be deep-copied are replaced with placeholder text.

### Structural views with occurrence records

The renderer provides interactive **Call tree** and **Folded DAG** views. Select a node and use the **Recorded occurrence** dropdown to inspect the corresponding call ID, depth, parent ID, arguments, result or error, and entry/exit snapshots. The occurrences retain the original call records; call IDs are assigned in call-entry order.

## Installation

Python 3.9 or newer is required. Install from a local clone:

```sh
git clone https://github.com/Zenith-20/recfold.git
cd recfold
python -m pip install -e .
```

If you are using JupyterHub, ensure the repository is on the server's filesystem and install it into your active kernel:

```python
%pip install -e /path/on/server/to/recfold
```

## Quick start

Run this in a Jupyter notebook cell:

```python
from recfold.tracer import trace
from recfold.renderer import render_session

@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

answer = fib(5)
print(answer)  # 5

widget = render_session(fib.last_session, title="Fibonacci: repeated work")
widget  # Keep as the last expression so Jupyter displays the widget
```

For a plain recursive function, `run_traced` returns the result and trace
session:

```python
from recfold.tracer import run_traced
from recfold.renderer import render_session

def factorial(n):
    if n < 2:
        return 1
    return n * factorial(n - 1)

answer, session = run_traced(factorial, 5)
widget = render_session(session)
widget
```

## Offline HTML export

To save the visualization as a standalone HTML document:

```python
widget.save("fib.html")

# Use overwrite=True to replace an existing file
widget.save("fib.html", overwrite=True)
```

The exported document contains the graph views, styles, scripts, and rendered trace data. It makes no network requests and can be opened offline in a JavaScript-enabled browser. Review the included trace data before sharing.

## Accessible description of the visual output

The rendered page contains two alternative views. In the **Call tree**, every
invocation is a separate labeled node; parent nodes connect to the calls they
made. In the **Folded DAG**, structurally matching subtrees share a node, and
the node label's `×N` suffix reports how many original occurrences it
represents. An edge label such as `x2` means that two calls to the same
subtree were made by the representative caller. The inspector identifies the
selected node, lists each recorded occurrence, and exposes its arguments,
return value or error, and entry/exit snapshots.

The graph controls support keyboard focus, Enter/Space selection, arrow-key
panning, plus/minus zoom, and Fit. For a text-only workflow, use the
`build_render_data()` JSON-compatible dictionary or inspect `TraceSession`,
`CallNode`, `DagNode`, and `TraceAnalysis` directly in Python.

## Current limitations

* **Synchronous execution only:** The decorator does not trace the execution of async function bodies or generator bodies. They return coroutine or generator objects when called; tracing does not await or iterate them.
* **Representation-based cycle guard:** The active-call guard compares function names and argument `repr()` strings, using the default 80-character limit. Distinct values with the same representation can be mistaken for a repeated active call. For terminating recursion where this is a concern, `@trace(detect_cycles=False, max_depth=...)` disables that guard while retaining a depth bound.
* **No automatic local-variable capture:** The tracer snapshots arguments at entry and return values or exceptions at exit. `snapshot_locals()` is available in `recfold.snapshot`, but the tracer does not call it.
* **Structural matching is not semantic proof:** Folding keys use function names, argument and result representations, exception text, and ordered child subtree keys. Matching keys do not establish mathematical equivalence or purity.
* **No virtualization:** Both graph views are rendered with all included nodes and edges. Large traces can require substantial memory and browser rendering work.

## Project structure

```text
models.py    Dataclasses for calls, DAG nodes/edges, sessions, and statistics
snapshot.py  Deep-copying and string truncation utilities
tracer.py    @trace decorator, call stack tracking, and depth/cycle guards
analyzer.py  Subtree folding logic and redundancy statistics
layout.py    Pure-Python 2D node positioning and straight edge geometry
renderer.py  Self-contained HTML/SVG generator and Jupyter widget wrapper
```

There is no console-script entry point or package-level re-export; import
functions from their modules as shown above.

## Development and testing

To run the unit test suite:

```sh
python -m pip install pytest
python -m pytest
```

### Optional browser tests

End-to-end UI tests (verifying click selection, panning, zooming, and keyboard navigation in Chromium) require Playwright:

```sh
python -m pip install playwright
python -m playwright install chromium
```

Run them by setting the opt-in environment variable:

* **macOS / Linux:**
  ```sh
  RECFOLD_BROWSER_TESTS=1 python -m pytest tests/test_renderer.py
  ```
* **Windows PowerShell:**
  ```powershell
  $env:RECFOLD_BROWSER_TESTS = "1"
  python -m pytest tests/test_renderer.py
  ```

Without this flag, browser tests are skipped automatically.

## Further documentation

* [Complete recfold API reference](https://github.com/Zenith-20/recfold/blob/main/docs/API.md)
* [Renderer API, integration, and troubleshooting](https://github.com/Zenith-20/recfold/blob/main/docs/renderer.md)
* [Demo notebook: Fibonacci, backtracking, and error guards](https://github.com/Zenith-20/recfold/blob/main/docs/recfold_demo.ipynb)

## License

[MIT](https://github.com/Zenith-20/recfold/blob/main/LICENSE)