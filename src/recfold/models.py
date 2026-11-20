"""Dataclass records used throughout recfold."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CallNode:
    """One invocation recorded in a recursive call tree.

    ``node_id`` identifies the occurrence, ``parent_id`` identifies its caller,
    and ``children_ids`` lists directly called recursive occurrences in
    execution order. Entry and exit dictionaries preserve boundary snapshots.
    """

    node_id: str
    func_name: str
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    depth: int = 0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    entry_snapshot: Dict[str, Any] = field(default_factory=dict)
    exit_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DagEdge:
    """One directed connection between two folded DAG nodes.

    ``source_id`` is the caller, ``target_id`` is the callee, and ``label`` is
    an optional display string such as ``"x2"``.
    """

    source_id: str
    target_id: str
    label: Optional[str] = None


@dataclass
class DagNode:
    """One unique structural subtree in a folded directed acyclic graph.

    ``dag_id`` is the DAG's stable identifier. ``call_count`` is the number of
    original call-tree nodes folded into this DAG node.
    """

    dag_id: str
    func_name: str
    args_sig: str
    call_count: int = 1
    incoming_edges: List[DagEdge] = field(default_factory=list)
    outgoing_edges: List[DagEdge] = field(default_factory=list)


@dataclass
class TraceAnalysis:
    """Counts and structural redundancy metrics for a recorded trace."""

    total_calls: int = 0
    unique_calls: int = 0
    max_depth: int = 0
    redundancy_ratio: float = 0.0


@dataclass
class TraceSession:
    """The complete container for one traced execution.

    It holds the original call tree, optional folded DAG, and optional
    post-hoc analysis. Rendering and layout operations do not replace the
    original call tree.
    """

    func_name: str
    nodes: Dict[str, CallNode] = field(default_factory=dict)
    root_id: Optional[str] = None
    dag_nodes: Dict[str, DagNode] = field(default_factory=dict)
    dag_edges: List[DagEdge] = field(default_factory=list)
    analysis: Optional[TraceAnalysis] = None
