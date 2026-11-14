"""Safe deep copies of function arguments and local variables for recfold."""

import copy
from typing import Any, Dict, Tuple


def safe_copy(value: Any) -> Any:
    """Return a deep copy of value, or a placeholder string if it can't be copied.

    The copy never shares mutable parts with the original, so later changes
    to the original don't change the recorded snapshot.
    """
    try:
        return copy.deepcopy(value)
    except Exception:
        return f"<uncopyable {type(value).__name__}>"


def safe_repr(value: Any, max_len: int = 80) -> str:
    """Return a short text version of value, cut to at most max_len characters.

    Long values end with "..." so the visual map stays readable.
    If repr() itself fails, a placeholder string is returned instead.
    """
    try:
        text = repr(value)
    except Exception:
        text = f"<unreprable {type(value).__name__}>"
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def snapshot_args(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    """Return safe copies of a call's positional and keyword arguments.

    The result has the same shape as the input: (tuple, dict). Each value is
    copied with safe_copy, so the originals are never shared or changed.
    """
    copied_args = tuple(safe_copy(a) for a in args)
    copied_kwargs = {name: safe_copy(value) for name, value in kwargs.items()}
    return copied_args, copied_kwargs

def make_entry_snapshot(args: Tuple[Any, ...], kwargs: Dict[str, Any], max_len: int = 80) -> Dict[str, Any]:
    """Build the dict stored in CallNode.entry_snapshot when a call starts.

    "args" and "kwargs" hold safe copies of the inputs.
    "args_repr" and "kwargs_repr" hold short text versions for the visual map.
    """
    copied_args, copied_kwargs = snapshot_args(args, kwargs)
    return {
        "args": copied_args,
        "kwargs": copied_kwargs,
        "args_repr": [safe_repr(a, max_len) for a in args],
        "kwargs_repr": {name: safe_repr(value, max_len) for name, value in kwargs.items()},
    }