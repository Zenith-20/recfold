"""Safe deep copies of function arguments and local variables for recfold."""

import copy
from typing import Any


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