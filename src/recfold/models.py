from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CallNode:
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
