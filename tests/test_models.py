from recfold.models import (
    CallNode,
    DagEdge,
    DagNode,
    TraceAnalysis,
    TraceSession,
)


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


def test_trace_analysis_fields():
    analysis = TraceAnalysis(
        total_calls=10,
        unique_calls=4,
        max_depth=3,
        redundancy_ratio=0.6,
    )

    assert analysis.total_calls == 10
    assert analysis.unique_calls == 4
    assert analysis.max_depth == 3
    assert analysis.redundancy_ratio == 0.6


def test_trace_session_defaults_and_optional_analysis():
    session = TraceSession(func_name="factorial")
    other_session = TraceSession(func_name="factorial")

    assert session.func_name == "factorial"
    assert session.nodes == {}
    assert session.root_id is None
    assert session.dag_nodes == {}
    assert session.dag_edges == []
    assert session.analysis is None
    assert session.nodes is not other_session.nodes
    assert session.dag_nodes is not other_session.dag_nodes
    assert session.dag_edges is not other_session.dag_edges

    analysis = TraceAnalysis(
        total_calls=10,
        unique_calls=4,
        max_depth=3,
        redundancy_ratio=0.6,
    )
    analyzed_session = TraceSession(func_name="factorial", analysis=analysis)

    assert analyzed_session.analysis is analysis
