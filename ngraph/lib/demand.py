from __future__ import annotations
from enum import IntEnum
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
from ngraph.lib.algorithms import spf
from ngraph.lib.algorithms.place_flow import FlowPlacement, place_flow_on_graph
from ngraph.lib.graph import NodeID, EdgeID, StrictMultiDiGraph
from ngraph.lib.algorithms import base
from ngraph.lib.path_bundle import PathBundle
from ngraph.lib.flow_policy import FlowPolicy, FlowPolicyConfig, get_flow_policy


class DemandStatus(IntEnum):
    UNKNOWN = 0
    NOT_PLACED = 1
    PARTIAL = 2
    PLACED = 3


class Demand:
    """
    Demand class represents a demand between two nodes. It can be realized through one or more Flows.
    """

    def __init__(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        volume: float,
        demand_class: int = 0,
    ):
        self.src_node: NodeID = src_node
        self.dst_node: NodeID = dst_node
        self.volume: float = volume
        self.demand_class: int = demand_class
        self.placed_demand: float = 0

    def __lt__(self, other: Demand):
        return self.demand_class < other.demand_class

    def __str__(self) -> str:
        return f"Demand(src_node={self.src_node}, dst_node={self.dst_node}, volume={self.volume}, demand_class={self.demand_class}, placed_demand={self.placed_demand})"

    @property
    def status(self):
        if self.placed_demand < base.MIN_FLOW:
            return DemandStatus.NOT_PLACED
        elif self.volume - self.placed_demand < base.MIN_FLOW:
            return DemandStatus.PLACED
        return DemandStatus.PARTIAL

    def place(
        self,
        flow_graph: StrictMultiDiGraph,
        flow_policy: FlowPolicy,
        max_fraction: float = 1,
        max_placement: Optional[float] = None,
    ) -> Tuple[float, float]:
        to_place = self.volume - self.placed_demand

        if max_placement is not None:
            to_place = min(to_place, max_placement)

        if max_fraction > 0:
            to_place = min(to_place, self.volume * max_fraction)
        else:
            to_place = self.volume if self.volume == float("inf") else 0

        flow_policy.place_demand(
            flow_graph,
            self.src_node,
            self.dst_node,
            self.demand_class,
            to_place,
        )
        placed = flow_policy.placed_demand - self.placed_demand
        self.placed_demand = flow_policy.placed_demand
        remaining = to_place - placed
        return placed, remaining
