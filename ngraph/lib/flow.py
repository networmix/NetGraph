from __future__ import annotations
from enum import IntEnum
from collections import deque
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    NamedTuple,
)
from ngraph.lib.place_flow import (
    FlowPlacement,
    place_flow_on_graph,
    remove_flow_from_graph,
)
from ngraph.lib.graph import (
    AttrDict,
    NodeID,
    EdgeID,
    MultiDiGraph,
)
from ngraph.lib import spf, common
from ngraph.lib.path_bundle import PathBundle


class FlowIndex(NamedTuple):
    src_node: NodeID
    dst_node: NodeID
    flow_class: int
    flow_id: int


class Flow:
    """
    Flow is a fraction of a demand applied along a particular PathBundle in a graph.
    """

    def __init__(
        self,
        path_bundle: PathBundle,
        flow_index: Hashable,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ):
        self.path_bundle: PathBundle = path_bundle
        self.flow_index: Hashable = flow_index
        self.excluded_edges: Set[EdgeID] = excluded_edges or set()
        self.excluded_nodes: Set[NodeID] = excluded_nodes or set()
        self.src_node: NodeID = path_bundle.src_node
        self.dst_node: NodeID = path_bundle.dst_node
        self.placed_flow: float = 0

    def __str__(self) -> str:
        return f"Flow(flow_index={self.flow_index}, placed_flow={self.placed_flow})"

    def place_flow(
        self,
        flow_graph: MultiDiGraph,
        to_place: float,
        flow_placement: FlowPlacement,
    ) -> Tuple[float, float]:
        placed_flow = 0
        if to_place >= common.MIN_FLOW:
            flow_placement_meta = place_flow_on_graph(
                flow_graph,
                self.src_node,
                self.dst_node,
                self.path_bundle.pred,
                to_place,
                self.flow_index,
                flow_placement,
            )
            placed_flow += flow_placement_meta.placed_flow
            to_place = flow_placement_meta.remaining_flow
            self.placed_flow += placed_flow
        return placed_flow, to_place

    def remove_flow(self, flow_graph: MultiDiGraph) -> None:
        remove_flow_from_graph(flow_graph, self.flow_index)
        self.placed_flow = 0
