"""Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. It can carry either a concrete `FlowPolicy` instance or a
`FlowPolicyPreset` enum to construct one.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.utils.ids import new_base64_uuid

if TYPE_CHECKING:
    import netgraph_core

    FlowPolicy = netgraph_core.FlowPolicy
else:
    FlowPolicy = None  # type: ignore


@dataclass
class TrafficDemand:
    """Traffic demand specification using unified selectors.

    Attributes:
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        volume: Total demand volume.
        volume_placed: Portion of this demand placed so far.
        priority: Priority class (lower = higher priority).
        mode: Node pairing mode ("combine" or "pairwise").
        group_mode: How grouped nodes produce demands
            ("flatten", "per_group", "group_pairwise").
        flow_policy: Policy preset for routing.
        flow_policy_obj: Concrete policy instance (overrides flow_policy).
        attrs: Arbitrary user metadata.
        id: Unique identifier. Auto-generated if empty.
    """

    source: Union[str, Dict[str, Any]] = ""
    target: Union[str, Dict[str, Any]] = ""
    volume: float = 0.0
    volume_placed: float = 0.0
    priority: int = 0
    mode: str = "combine"
    group_mode: str = "flatten"
    flow_policy: Optional[FlowPolicyPreset] = None
    flow_policy_obj: Optional["FlowPolicy"] = None  # type: ignore[valid-type]
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        """Generate id if not provided."""
        if not self.id:
            # Build a stable identifier from source/target
            src_key = self.source if isinstance(self.source, str) else str(self.source)
            tgt_key = self.target if isinstance(self.target, str) else str(self.target)
            self.id = f"{src_key}|{tgt_key}|{new_base64_uuid()}"
