from recfold.models import CallNode, DagEdge, DagNode


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


def test_dag_node_and_edge_fields():
    edge = DagEdge(source_id="1", target_id="2", label="recursive")
    node = DagNode(
        dag_id="1",
        func_name="factorial",
        args_sig="(3,)",
        incoming_edges=[edge],
        outgoing_edges=[edge],
    )

    assert edge.source_id == "1"
    assert edge.target_id == "2"
    assert edge.label == "recursive"
    assert node.dag_id == "1"
    assert node.func_name == "factorial"
    assert node.args_sig == "(3,)"
    assert node.call_count == 1
    assert node.incoming_edges == [edge]
    assert node.outgoing_edges == [edge]


def test_dag_node_edge_lists_are_independent():
    first = DagNode(dag_id="1", func_name="factorial", args_sig="(3,)")
    second = DagNode(dag_id="2", func_name="factorial", args_sig="(2,)")

    assert first.incoming_edges == []
    assert first.outgoing_edges == []
    assert first.incoming_edges is not second.incoming_edges
    assert first.outgoing_edges is not second.outgoing_edges
    assert DagEdge(source_id="1", target_id="2").label is None
