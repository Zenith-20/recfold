"""Pure-Python recursion tracing decorator and safety guards for recfold."""

from contextvars import ContextVar
import functools
from typing import Any, Callable, Dict, Optional, Set, Tuple

from recfold.models import CallNode, TraceSession
from recfold.snapshot import make_entry_snapshot, make_exit_snapshot, safe_repr

_ACTIVE_TRACE: ContextVar[Optional[Dict[str, Any]]] = ContextVar("_ACTIVE_TRACE", default=None)


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


def start_call_node(
    session: TraceSession,
    node_id: str,
    func_name: str,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    depth: int,
    parent_id: Optional[str] = None,
    max_repr_len: int = 80,
) -> CallNode:
    """Create a CallNode, capture its entry snapshot, and link it in session."""
    entry_snap = make_entry_snapshot(args, kwargs, max_len=max_repr_len)
    node = CallNode(
        node_id=node_id,
        func_name=func_name,
        args=entry_snap["args"],
        kwargs=entry_snap["kwargs"],
        depth=depth,
        parent_id=parent_id,
        entry_snapshot=entry_snap,
    )
    session.nodes[node_id] = node
    if parent_id is None:
        if session.root_id is None:
            session.root_id = node_id
    elif parent_id in session.nodes:
        session.nodes[parent_id].children_ids.append(node_id)
    return node


def finish_call_node(
    node: CallNode,
    result: Any = None,
    error: Optional[BaseException] = None,
    max_repr_len: int = 80,
) -> CallNode:
    """Record the return value or exception snapshot on a completed CallNode."""
    exit_snap = make_exit_snapshot(result, error=error, max_len=max_repr_len)
    node.result = exit_snap["result"]
    node.exit_snapshot = exit_snap
    return node


def trace(
    func: Optional[Callable[..., Any]] = None,
    *,
    max_depth: Optional[int] = 100,
    detect_cycles: bool = True,
    max_repr_len: int = 80,
) -> Any:
    """Decorator that records a recursive function's call tree into a TraceSession."""

    def decorator(target_func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(target_func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_state = _ACTIVE_TRACE.get()
            if current_state is None:
                session = TraceSession(func_name=target_func.__name__)
                state: Dict[str, Any] = {
                    "session": session,
                    "stack": [],
                    "active_keys": set(),
                    "counter": 0,
                }
                token = _ACTIVE_TRACE.set(state)
                is_root = True
            else:
                state = current_state
                session = state["session"]
                token = None
                is_root = False

            try:
                depth = len(state["stack"])
                call_key = make_call_key(target_func.__name__, args, kwargs)
                check_recursion_guards(
                    depth=depth,
                    max_depth=max_depth,
                    call_key=call_key,
                    active_keys=state["active_keys"],
                    detect_cycles=detect_cycles,
                )

                state["counter"] += 1
                node_id = str(state["counter"])
                parent_id = state["stack"][-1] if state["stack"] else None
                node = start_call_node(
                    session=session,
                    node_id=node_id,
                    func_name=target_func.__name__,
                    args=args,
                    kwargs=kwargs,
                    depth=depth,
                    parent_id=parent_id,
                    max_repr_len=max_repr_len,
                )

                state["stack"].append(node_id)
                state["active_keys"].add(call_key)
                try:
                    result = target_func(*args, **kwargs)
                except BaseException as exc:
                    finish_call_node(node, error=exc, max_repr_len=max_repr_len)
                    raise
                else:
                    finish_call_node(node, result=result, max_repr_len=max_repr_len)
                    return result
                finally:
                    state["stack"].pop()
                    state["active_keys"].discard(call_key)
            finally:
                if is_root and token is not None:
                    wrapper.last_session = session  # type: ignore[attr-defined]
                    _ACTIVE_TRACE.reset(token)

        wrapper.last_session = None  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator

def run_traced(
    func: Callable[..., Any],
    *args: Any,
    max_depth: Optional[int] = 100,
    detect_cycles: bool = True,
    max_repr_len: int = 80,
    **kwargs: Any,
) -> Tuple[Any, TraceSession]:
    """Execute a traced or plain recursive function and return (result, TraceSession)."""
    if hasattr(func, "last_session"):
        result = func(*args, **kwargs)
        return result, func.last_session  # type: ignore[attr-defined]

    traced_func = trace(
        max_depth=max_depth,
        detect_cycles=detect_cycles,
        max_repr_len=max_repr_len,
    )(func)

    func_globals = getattr(func, "__globals__", None)
    func_name = getattr(func, "__name__", None)
    rebound_global = (
        isinstance(func_globals, dict)
        and isinstance(func_name, str)
        and func_globals.get(func_name) is func
    )

    rebound_cells = []
    for cell in getattr(func, "__closure__", None) or ():
        try:
            if cell.cell_contents is func:
                rebound_cells.append(cell)
        except ValueError:
            continue

    if rebound_global:
        func_globals[func_name] = traced_func
    for cell in rebound_cells:
        cell.cell_contents = traced_func

    try:
        result = traced_func(*args, **kwargs)
    finally:
        for cell in rebound_cells:
            cell.cell_contents = func
        if rebound_global:
            func_globals[func_name] = func

    return result, traced_func.last_session  # type: ignore[attr-defined]