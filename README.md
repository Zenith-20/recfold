# recfold

Explore recursive Python calls as an interactive call tree or folded directed
acyclic graph (DAG), directly in a Jupyter notebook. Click a node to inspect its
recorded inputs, result, errors, and repeated occurrences.

The package uses only the Python standard library at runtime. Its renderer
embeds its own HTML, SVG, CSS, and JavaScript: no Graphviz, CDN, browser extension,
ipywidgets, or extra visualization software is required.

## Install from this repository

Python 3.9 or newer is required. Until a PyPI release is published, install the
source checkout:

```sh
git clone https://github.com/Zenith-20/recfold.git
cd recfold
python -m venv venv
```

Activate the environment using the command for your terminal:

| Terminal | Command |
| --- | --- |
| Windows PowerShell | `.\venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `venv\Scripts\activate.bat` |
| macOS / Linux | `source venv/bin/activate` |

Then install the project and its test runner:

```sh
python -m pip install -e .
python -m pip install pytest
python -m pytest
```

In an existing JupyterHub notebook, install into the active kernel with
`%pip install -e /path/to/recfold`. The checkout must be on the JupyterHub server;
a path on your laptop is not a path on that server. Restart the kernel if needed.
Use the branch containing the renderer until that work is merged into `main`.

## First visualization

Run this in a notebook cell:

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
widget  # Keep this as the last expression so Jupyter displays it.
```

This example records **15 calls**, folds them into **6 unique subtrees**, and
reports maximum depth **4** and **60% repeated calls**. The root is at depth 0.

- **Folded DAG / Call tree:** switch between shared subtrees and individual calls.
- **Select a node:** see its recorded arguments, result, parent, and snapshots.
- **Recorded occurrence:** inspect individual calls represented by a folded node.
- **Zoom and pan:** use the buttons, drag the background, or use the keyboard.
- **Keyboard:** Tab to a node and press Enter/Space; use +/− to zoom, 0 to fit,
  and arrow keys to pan. Ctrl/⌘ + scroll also zooms.
- **Errors:** calls with recorded errors have red outlines and error details.

Folding summarizes work **after it has happened**. It does not memoize your
function, skip recursive calls, or accelerate its execution.

## Export without a notebook

```python
widget.save("fib.html")
```

Open the file in a browser. It remains interactive offline. Existing files are
preserved; use `widget.save("fib.html", overwrite=True)` to replace one.
Exports include the recorded values, so inspect them before sharing.

You can also trace a plain recursive function:

```python
from recfold.tracer import run_traced

def factorial(n):
    return 1 if n <= 1 else n * factorial(n - 1)

answer, session = run_traced(factorial, 5)
render_session(session)
```

## Documentation and examples

- [Renderer API, integration, and troubleshooting](docs/renderer.md)
- [Runnable notebook: Fibonacci, backtracking inputs, and errors](docs/recfold_demo.ipynb)
- [Member 6 implementation and validation](docs/member6.md)

Import functions from their modules, as above; `recfold.__init__` currently has
no package-level re-exports.

## How it fits together

```text
models.py    Shared CallNode, DagNode, DagEdge, TraceSession, and statistics
snapshot.py  Safe argument/result copies and readable representations
tracer.py    Decorator, call tree, depth guard, and repeated-active-call guard
analyzer.py  Equivalent-subtree folding and summary statistics
layout.py    Pure-Python node coordinates and edge geometry
renderer.py Interactive HTML/SVG output and notebook display
```

Rendering accepts an existing `TraceSession`. It does not execute the function
again or change the session. Advanced users can pass an existing DAG layout;
see the API guide.

## Current limits

- Tracing supports ordinary synchronous functions. Async and generator bodies
  are not traced through execution; prefer `@trace` for recursive methods.
- Cycle detection uses shortened argument representations and can reject
  distinct long inputs. For a known terminating function, consider
  `@trace(detect_cycles=False, max_depth=...)` with a suitable depth bound.
- Input snapshots and results are recorded, but arbitrary local variables and
  every intermediate backtracking mutation are not captured automatically.
- Folding compares function names, representations, errors, and ordered child
  subtrees. It is not a proof that calls are mathematically equivalent or pure.
- Large recursion trees still execute and are retained in memory. Start with
  small teaching examples; layout and browser rendering are not virtualized.
- Notebook output must be trusted and its frontend must permit sandboxed
  `srcdoc` iframes and inline scripts. Administrator restrictions on JupyterHub
  may require opening the exported HTML instead.

## Development

Follow the team's one-function loop: add a failing test, implement one function,
run `python -m pytest`, then commit and push that function with its tests.
Keep changes within your assigned module and its tests/documentation.

Optional renderer browser checks are development-only:

```sh
python -m pip install playwright
python -m playwright install chromium
```

On macOS/Linux:

```sh
RECFOLD_BROWSER_TESTS=1 python -m pytest tests/test_renderer.py
```

On PowerShell:

```powershell
$env:RECFOLD_BROWSER_TESTS = "1"
python -m pytest tests/test_renderer.py
```

Without that opt-in flag, browser tests are skipped and only pytest is needed.

## License

[MIT](LICENSE).
