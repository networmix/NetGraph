from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ngraph.lib.flow_policy import FlowPolicyConfig, FlowPolicy
from ngraph.network import new_base64_uuid


@dataclass(slots=True)
class TrafficDemand:
    """
    Represents a single traffic demand in a network.

    Attributes:
        source_path (str): A regex pattern (string) for selecting source nodes.
        sink_path (str): A regex pattern (string) for selecting sink nodes.
        priority (int): A priority class for this demand (default=0).
        demand (float): The total demand volume (default=0.0).
        demand_placed (float): The portion of this demand that has been placed so far.
        flow_policy_config ((Optional[FlowPolicyConfig]): The routing/placement policy config.
        flow_policy (Optional[FlowPolicy]): A fully constructed FlowPolicy instance.
            If provided, it overrides flow_policy_config.
        mode (str): Expansion mode for generating sub-demands.
        attrs (Dict[str, Any]): Additional arbitrary attributes.
        id (str): Unique ID assigned at initialization.
    """

    source_path: str = ""
    sink_path: str = ""
    priority: int = 0
    demand: float = 0.0
    demand_placed: float = 0.0
    flow_policy_config: Optional[FlowPolicyConfig] = None
    flow_policy: Optional[FlowPolicy] = None
    mode: str = "combine"
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """
        Generate a unique ID by combining source, sink, and a random Base64 UUID.
        """
        self.id = f"{self.source_path}|{self.sink_path}|{new_base64_uuid()}"
