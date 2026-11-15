import pytest

from recfold.models import TraceSession
from recfold.tracer import (
    check_recursion_guards,
    finish_call_node,
    make_call_key,
    start_call_node,
    trace,
)


def test_make_call_key_handles_unhashable_and_distinguishes_calls():
    key1 = make_call_key("solve", ([1, 2],), {"memo": {"a": 1}})
    key2 = make_call_key("solve", ([1, 2],), {"memo": {"a": 1}})
    key3 = make_call_key("solve", ([1, 2, 3],), {"memo": {"a": 1}})
    key4 = make_call_key("other", ([1, 2],), {"memo": {"a": 1}})

    assert hash(key1) == hash(key2)
    assert key1 == key2
    assert key1 != key3
    assert key1 != key4


def test_check_recursion_guards_depth_and_cycles():
    key_a = make_call_key("f", (5,), {})
    key_b = make_call_key("f", (4,), {})
    active = {key_a}

    # Valid call within max_depth and not currently active
    check_recursion_guards(depth=2, max_depth=2, call_key=key_b, active_keys=active)

    # Exceeds max_depth
    with pytest.raises(RecursionError, match="Maximum trace depth"):
        check_recursion_guards(depth=3, max_depth=2, call_key=key_b, active_keys=active)

    # Active cycle detected when detect_cycles=True
    with pytest.raises(RecursionError, match="Infinite recursion cycle"):
        check_recursion_guards(depth=1, max_depth=10, call_key=key_a, active_keys=active, detect_cycles=True)

    # Same key allowed if cycle detection is turned off
    check_recursion_guards(depth=1, max_depth=10, call_key=key_a, active_keys=active, detect_cycles=False)


def test_start_call_node_links_root_and_children():
    session = TraceSession(func_name="solve")
    items = [1, 2]

    root = start_call_node(
        session=session,
        node_id="1",
        func_name="solve",
        args=(items,),
        kwargs={"flag": True},
        depth=0,
        parent_id=None,
    )
    items.append(99)  # Mutating original input after call starts

    child = start_call_node(
        session=session,
        node_id="2",
        func_name="solve",
        args=([1],),
        kwargs={},
        depth=1,
        parent_id="1",
    )

    assert session.root_id == "1"
    assert set(session.nodes.keys()) == {"1", "2"}
    assert root.args == ([1, 2],)
    assert root.entry_snapshot["args"] == ([1, 2],)
    assert root.entry_snapshot["args_repr"] == ["[1, 2]"]
    assert root.children_ids == ["2"]
    assert child.parent_id == "1"
    assert child.depth == 1


def test_finish_call_node_records_result_and_errors():
    session = TraceSession(func_name="solve")
    node = start_call_node(session, "1", "solve", (3,), {}, depth=0)

    ret_val = [10, 20]
    finish_call_node(node, result=ret_val)
    ret_val.append(30)  # Mutate original return list afterward

    assert node.result == [10, 20]
    assert node.exit_snapshot == {
        "result": [10, 20],
        "result_repr": "[10, 20]",
        "error": None,
    }

    err_node = start_call_node(session, "2", "solve", (-1,), {}, depth=1, parent_id="1")
    finish_call_node(err_node, error=ValueError("negative input"))

    assert err_node.result is None
    assert err_node.exit_snapshot["error"] == "ValueError: negative input"


def test_trace_decorator_records_tree_and_enforces_guards():
    @trace
    def fib(n: int) -> int:
        if n <= 1:
            return n
        return fib(n - 1) + fib(n - 2)

    assert fib(3) == 2
    session = fib.last_session
    assert session is not None
    assert session.func_name == "fib"
    assert session.root_id == "1"
    # fib(3) calls fib(2) [which calls fib(1), fib(0)] and fib(1) -> 5 calls total
    assert len(session.nodes) == 5
    assert session.nodes["1"].result == 2
    assert session.nodes["1"].children_ids == ["2", "5"]

    @trace(max_depth=2)
    def countdown(n: int) -> int:
        if n == 0:
            return 0
        return countdown(n - 1)

    with pytest.raises(RecursionError, match="Maximum trace depth"):
        countdown(5)

    @trace
    def infinite(x: int) -> int:
        return infinite(x)

    with pytest.raises(RecursionError, match="Infinite recursion cycle"):
        infinite(1)
    assert infinite.last_session is not None
    assert infinite.last_session.root_id == "1"