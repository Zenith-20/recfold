import threading

from recfold.snapshot import safe_copy, safe_repr


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