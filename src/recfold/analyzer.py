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