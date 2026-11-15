from recfold.tracer import make_call_key


def test_make_call_key_handles_unhashable_and_distinguishes_calls():
    key1 = make_call_key("solve", ([1, 2],), {"memo": {"a": 1}})
    key2 = make_call_key("solve", ([1, 2],), {"memo": {"a": 1}})
    key3 = make_call_key("solve", ([1, 2, 3],), {"memo": {"a": 1}})
    key4 = make_call_key("other", ([1, 2],), {"memo": {"a": 1}})

    assert hash(key1) == hash(key2)
    assert key1 == key2
    assert key1 != key3
    assert key1 != key4