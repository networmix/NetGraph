from __future__ import annotations
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)
from ngraph.algorithms.place_flow import FlowPlacement, place_flow_on_graph
from ngraph.graph import DstNodeID, EdgeID, MultiDiGraph, NodeID, SrcNodeID
from ngraph.algorithms import spf, common
from ngraph.path_bundle import PathBundle
from ngraph.flow import FlowPolicy, FlowPolicyConfig, get_flow_policy


class Demand:
    """
    Demand class represents a demand between two nodes. It can be realized through one or more Flows.
    """

    def __init__(
        self,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        volume: float,
        flow_policy: FlowPolicy,
        label: Optional[Any] = None,
    ):
        self.src_node: SrcNodeID = src_node
        self.dst_node: DstNodeID = dst_node
        self.volume: float = volume
        self.flow_policy = flow_policy
        self.label: Optional[Any] = label

    @property
    def placed_demand(self) -> float:
        return self.flow_policy.placed_demand

    def __str__(self) -> str:
        return f"Demand(src_node={self.src_node}, dst_node={self.dst_node}, volume={self.volume}, label={self.label}, placed_demand={self.placed_demand})"

    @classmethod
    def create(
        cls,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        volume: float,
        flow_policy: Optional[FlowPolicy] = None,
        flow_policy_config: Optional[FlowPolicyConfig] = None,
        label: Optional[Any] = None,
    ) -> Demand:
        if flow_policy is None:
            if flow_policy_config is None:
                raise ValueError(
                    "Either flow_policy or flow_policy_config must be provided"
                )
            flow_policy = get_flow_policy(flow_policy_config)
        return cls(src_node, dst_node, volume, flow_policy, label)

    def place(
        self,
        flow_graph: MultiDiGraph,
        max_fraction: float = 1,
    ) -> Tuple[float, float]:
        if max_fraction > 0:
            to_place = min(self.volume - self.placed_demand, self.volume * max_fraction)
        else:
            to_place = self.volume if self.volume == float("inf") else 0
        placed, remaining = self.flow_policy.place_demand(
            flow_graph,
            self.src_node,
            self.dst_node,
            self.label,
            to_place,
        )
        return placed, remaining
