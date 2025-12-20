"""Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. It can carry either a concrete `FlowPolicy` instance or a
`FlowPolicyPreset` enum to construct one.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

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
        sink: Sink node selector (string path or selector dict).
        demand: Total demand volume.
        demand_placed: Portion of this demand placed so far.
        priority: Priority class (lower = higher priority).
        mode: Node pairing mode ("combine" or "pairwise").
        group_mode: How grouped nodes produce demands
            ("flatten", "per_group", "group_pairwise").
        expand_vars: Variable substitutions using $var syntax.
        expansion_mode: How to combine expand_vars ("cartesian" or "zip").
        flow_policy_config: Policy preset for routing.
        flow_policy: Concrete policy instance (overrides flow_policy_config).
        attrs: Arbitrary user metadata.
        id: Unique identifier. Auto-generated if empty.
    """

    source: Union[str, Dict[str, Any]] = ""
    sink: Union[str, Dict[str, Any]] = ""
    demand: float = 0.0
    demand_placed: float = 0.0
    priority: int = 0
    mode: str = "combine"
    group_mode: str = "flatten"
    expand_vars: Dict[str, List[Any]] = field(default_factory=dict)
    expansion_mode: str = "cartesian"
    flow_policy_config: Optional[FlowPolicyPreset] = None
    flow_policy: Optional["FlowPolicy"] = None  # type: ignore[valid-type]
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        """Generate id if not provided."""
        if not self.id:
            # Build a stable identifier from source/sink
            src_key = self.source if isinstance(self.source, str) else str(self.source)
            sink_key = self.sink if isinstance(self.sink, str) else str(self.sink)
            self.id = f"{src_key}|{sink_key}|{new_base64_uuid()}"
