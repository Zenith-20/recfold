from recfold.models import CallNode


def test_call_node_fields():
    node = CallNode(
        node_id="1",
        func_name="factorial",
        args=(3,),
        kwargs={},
        result=6,
        depth=0,
    )

    assert node.node_id == "1"
    assert node.func_name == "factorial"
    assert node.args == (3,)
    assert node.kwargs == {}
    assert node.result == 6
    assert node.depth == 0


def test_call_node_default_fields_use_independent_factories():
    first = CallNode(node_id="1", func_name="factorial")
    second = CallNode(node_id="2", func_name="factorial")

    assert first.args == ()
    assert first.kwargs == {}
    assert first.result is None
    assert first.depth == 0
    assert first.parent_id is None
    assert first.children_ids == []
    assert first.entry_snapshot == {}
    assert first.exit_snapshot == {}
    assert first.kwargs is not second.kwargs
    assert first.children_ids is not second.children_ids
    assert first.entry_snapshot is not second.entry_snapshot
    assert first.exit_snapshot is not second.exit_snapshot
