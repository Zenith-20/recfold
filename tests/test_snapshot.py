import threading

from recfold.snapshot import safe_copy


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
    