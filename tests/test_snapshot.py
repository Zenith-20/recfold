import threading

from recfold.snapshot import (
    make_entry_snapshot,
    make_exit_snapshot,
    safe_copy,
    safe_repr,
    snapshot_args,
)


def test_safe_copy_simple_values():
    assert safe_copy(5) == 5
    assert safe_copy("hello") == "hello"
    assert safe_copy(None) is None


def test_safe_copy_is_independent_of_original():
    original = [1, [2, 3], {"a": [4]}]
    copied = safe_copy(original)
    original[1].append(99)
    original[2]["a"].append(99)
    assert copied == [1, [2, 3], {"a": [4]}]
    assert copied is not original


def test_safe_copy_generator_gives_placeholder():
    gen = (x for x in range(3))
    assert safe_copy(gen) == "<uncopyable generator>"


def test_safe_copy_lock_gives_placeholder():
    lock = threading.Lock()
    result = safe_copy(lock)
    assert isinstance(result, str)
    assert result.startswith("<uncopyable")


def test_safe_repr_short_value_unchanged():
    assert safe_repr(42) == "42"
    assert safe_repr("hi") == "'hi'"
    assert safe_repr([1, 2]) == "[1, 2]"


def test_safe_repr_long_value_is_cut():
    text = safe_repr(list(range(1000)), max_len=20)
    assert len(text) == 20
    assert text.endswith("...")
    assert text.startswith("[0, 1, 2")


def test_safe_repr_broken_repr_gives_placeholder():
    class Broken:
        def __repr__(self):
            raise ValueError("boom")

    assert safe_repr(Broken()) == "<unreprable Broken>"


def test_snapshot_args_keeps_shape():
    args, kwargs = snapshot_args((1, "a"), {"n": 5})
    assert args == (1, "a")
    assert isinstance(args, tuple)
    assert kwargs == {"n": 5}


def test_snapshot_args_is_independent_of_original():
    data = [1, 2]
    memo = {"x": [0]}
    args, kwargs = snapshot_args((data,), {"memo": memo})
    data.append(3)
    memo["x"].append(9)
    assert args == ([1, 2],)
    assert kwargs == {"memo": {"x": [0]}}


def test_snapshot_args_empty():
    assert snapshot_args((), {}) == ((), {})


def test_snapshot_args_uncopyable_gives_placeholder():
    gen = (x for x in range(3))
    args, kwargs = snapshot_args((gen,), {"g": gen})
    assert args == ("<uncopyable generator>",)
    assert kwargs == {"g": "<uncopyable generator>"}

def test_make_entry_snapshot_has_all_keys():
    snap = make_entry_snapshot((5,), {"memo": {}})
    assert set(snap.keys()) == {"args", "kwargs", "args_repr", "kwargs_repr"}


def test_make_entry_snapshot_values():
    snap = make_entry_snapshot((5, "x"), {"memo": {1: 1}})
    assert snap["args"] == (5, "x")
    assert snap["kwargs"] == {"memo": {1: 1}}
    assert snap["args_repr"] == ["5", "'x'"]
    assert snap["kwargs_repr"] == {"memo": "{1: 1}"}


def test_make_entry_snapshot_is_independent_of_original():
    data = [1, 2]
    snap = make_entry_snapshot((data,), {})
    data.append(3)
    assert snap["args"] == ([1, 2],)


def test_make_entry_snapshot_shortens_long_repr():
    snap = make_entry_snapshot((list(range(1000)),), {}, max_len=20)
    assert len(snap["args_repr"][0]) == 20

def test_make_exit_snapshot_has_all_keys():
    snap = make_exit_snapshot(8)
    assert set(snap.keys()) == {"result", "result_repr", "error"}


def test_make_exit_snapshot_values():
    snap = make_exit_snapshot([1, 2])
    assert snap["result"] == [1, 2]
    assert snap["result_repr"] == "[1, 2]"
    assert snap["error"] is None


def test_make_exit_snapshot_is_independent_of_original():
    result = [1, 2]
    snap = make_exit_snapshot(result)
    result.append(3)
    assert snap["result"] == [1, 2]


def test_make_exit_snapshot_records_error():
    snap = make_exit_snapshot(None, error=ValueError("bad input"))
    assert snap["result"] is None
    assert snap["error"] == "ValueError: bad input"