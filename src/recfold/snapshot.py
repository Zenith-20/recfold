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