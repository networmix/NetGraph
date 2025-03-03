from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from ngraph.lib.flow_policy import FlowPolicyConfig
from ngraph.network import new_base64_uuid


@dataclass(slots=True)
class TrafficDemand:
    """
    Represents a single traffic demand in a network.

    This class provides:
      - Source and sink regex patterns to match sets of nodes in the network.
      - A total demand volume and a priority (lower number = higher priority).
      - A flow policy configuration to specify routing/placement logic (if
        not supplied, defaults to SHORTEST_PATHS_ECMP).
      - A 'mode' that determines how the demand expands into per-node-pair
        demands. Supported modes include:
          * "node_to_node": default behavior (each (src, dst) pair shares
            the demand).
          * "combine": combine all matched sources and all matched sinks,
            then distribute the demand among the cross-product of nodes.
          * "pairwise": for each (src_label, dst_label) pair, split up the
            total demand so each label cross-product receives an equal fraction.
          * "one_to_one": match src_labels[i] to dst_labels[i], then split
            demand among node pairs in those matched labels.

    Attributes:
        source_path (str): A regex pattern (string) for selecting source nodes.
        sink_path (str): A regex pattern (string) for selecting sink nodes.
        priority (int): A priority class for this demand (default=0).
        demand (float): The total demand volume (default=0.0).
        demand_placed (float): The portion of this demand that has been placed
            so far (default=0.0). This is updated when flows are placed.
        flow_policy_config (FlowPolicyConfig): The routing/placement policy.
        mode (str): Expansion mode for generating sub-demands (defaults to "node_to_node").
        attrs (Dict[str, Any]): Additional arbitrary attributes.
        id (str): Unique ID assigned at initialization.
    """

    source_path: str = ""
    sink_path: str = ""
    priority: int = 0
    demand: float = 0.0
    demand_placed: float = 0.0
    flow_policy_config: FlowPolicyConfig = FlowPolicyConfig.SHORTEST_PATHS_ECMP
    mode: str = "node_to_node"
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """
        Generate a unique ID by combining source, sink, and a random Base64 UUID.
        """
        self.id = f"{self.source_path}|{self.sink_path}|{new_base64_uuid()}"
