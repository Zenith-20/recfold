"""Pure-Python recursion tracing decorator and safety guards for recfold."""

from typing import Any, Dict, Optional, Set, Tuple

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


def check_recursion_guards(
    depth: int,
    max_depth: Optional[int],
    call_key: Tuple[Any, ...],
    active_keys: Set[Tuple[Any, ...]],
    detect_cycles: bool = True,
) -> None:
    """Raise RecursionError if depth exceeds max_depth or an active cycle is found."""
    if max_depth is not None and depth > max_depth:
        raise RecursionError(f"Maximum trace depth ({max_depth}) exceeded")
    if detect_cycles and call_key in active_keys:
        raise RecursionError(f"Infinite recursion cycle detected in '{call_key[0]}'")