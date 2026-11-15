"""Pure-Python recursion tracing decorator and safety guards for recfold."""

from typing import Any, Dict, Tuple

from recfold.snapshot import safe_repr


def make_call_key(
    func_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[str, Tuple[str, ...], Tuple[Tuple[str, str], ...]]:
    """Build a hashable signature for a function call's name and arguments."""
    args_sig = tuple(safe_repr(arg) for arg in args)
    kwargs_sig = tuple(sorted((k, safe_repr(v)) for k, v in kwargs.items()))
    return (func_name, args_sig, kwargs_sig)