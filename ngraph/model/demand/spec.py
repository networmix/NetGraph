"""Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. It can carry either a concrete `FlowPolicy` instance or a
`FlowPolicyPreset` enum to construct one.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.utils.ids import new_base64_uuid

if TYPE_CHECKING:
    import netgraph_core

    FlowPolicy = netgraph_core.FlowPolicy
else:
    FlowPolicy = None  # type: ignore


@dataclass
class TrafficDemand:
    """Single traffic demand input.

    Attributes:
        source_path: Regex string selecting source nodes.
        sink_path: Regex string selecting sink nodes.
        priority: Priority class for this demand (lower value = higher priority).
        demand: Total demand volume.
        demand_placed: Portion of this demand placed so far.
        flow_policy_config: Policy preset (FlowPolicyPreset enum) used to build
            a `FlowPolicy` if ``flow_policy`` is not provided.
        flow_policy: Concrete policy instance. If set, it overrides
            ``flow_policy_config``.
        mode: Expansion mode, ``"combine"`` or ``"pairwise"``.
        attrs: Arbitrary user metadata.
        id: Unique identifier assigned at initialization.
    """

    source_path: str = ""
    sink_path: str = ""
    priority: int = 0
    demand: float = 0.0
    demand_placed: float = 0.0
    flow_policy_config: Optional[FlowPolicyPreset] = None
    flow_policy: Optional["FlowPolicy"] = None  # type: ignore[valid-type]
    mode: str = "combine"
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """Assign a unique id from source, sink, and a Base64 UUID."""
        self.id = f"{self.source_path}|{self.sink_path}|{new_base64_uuid()}"
