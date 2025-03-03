from __future__ import annotations

from typing import Hashable, NamedTuple, Optional, Set, Tuple

from ngraph.lib.algorithms.base import MIN_FLOW
from ngraph.lib.algorithms.place_flow import (
    FlowPlacement,
    place_flow_on_graph,
    remove_flow_from_graph,
)
from ngraph.lib.graph import EdgeID, NodeID, StrictMultiDiGraph
from ngraph.lib.path_bundle import PathBundle


class FlowIndex(NamedTuple):
    """
    Describes a unique identifier for a Flow in the network.

    Attributes:
        src_node (NodeID): The source node of the flow.
        dst_node (NodeID): The destination node of the flow.
        flow_class (int): Integer representing the 'class' of this flow (e.g., traffic class).
        flow_id (str): A unique ID for this flow.
    """

    src_node: NodeID
    dst_node: NodeID
    flow_class: int
    flow_id: str


class Flow:
    """
    Represents a fraction of demand routed along a given PathBundle.

    In traffic-engineering scenarios, a `Flow` object can model:
      - MPLS LSPs/tunnels with explicit paths,
      - IP forwarding behavior (with ECMP or UCMP),
      - Or anything that follows a specific set of paths.
    """

    def __init__(
        self,
        path_bundle: PathBundle,
        flow_index: Hashable,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ) -> None:
        """
        Initialize a Flow object.

        Args:
            path_bundle (PathBundle): The set of paths this flow uses.
            flow_index (Hashable): A unique identifier for this flow (e.g., MPLS label, tuple, etc.).
            excluded_edges (Optional[Set[EdgeID]]): Edges to exclude from usage.
            excluded_nodes (Optional[Set[NodeID]]): Nodes to exclude from usage.
        """
        self.path_bundle: PathBundle = path_bundle
        self.flow_index: Hashable = flow_index
        self.excluded_edges: Set[EdgeID] = excluded_edges or set()
        self.excluded_nodes: Set[NodeID] = excluded_nodes or set()

        # Convenience references for flow endpoints
        self.src_node: NodeID = path_bundle.src_node
        self.dst_node: NodeID = path_bundle.dst_node

        # Track how much flow has been successfully placed
        self.placed_flow: float = 0.0

    def __str__(self) -> str:
        """
        Returns a string representation of the Flow.

        Returns:
            str: String representation including flow index and placed flow amount.
        """
        return f"Flow(flow_index={self.flow_index}, placed_flow={self.placed_flow})"

    def place_flow(
        self,
        flow_graph: StrictMultiDiGraph,
        to_place: float,
        flow_placement: FlowPlacement,
    ) -> Tuple[float, float]:
        """
        Attempt to place (or update) this flow on the given `flow_graph`.

        Args:
            flow_graph (StrictMultiDiGraph): The network graph tracking capacities and usage.
            to_place (float): The amount of flow requested to be placed.
            flow_placement (FlowPlacement): Strategy for distributing flow among equal-cost paths.

        Returns:
            Tuple[float, float]: A tuple of:
                placed_flow (float): The amount of flow actually placed.
                remaining_flow (float): The flow that could not be placed.
        """
        placed_flow = 0.0

        # Only place flow if above the minimum threshold
        if to_place >= MIN_FLOW:
            flow_placement_meta = place_flow_on_graph(
                flow_graph=flow_graph,
                src_node=self.src_node,
                dst_node=self.dst_node,
                pred=self.path_bundle.pred,
                flow=to_place,
                flow_index=self.flow_index,
                flow_placement=flow_placement,
            )
            placed_flow = flow_placement_meta.placed_flow
            to_place = flow_placement_meta.remaining_flow
            self.placed_flow += placed_flow

        return placed_flow, to_place

    def remove_flow(self, flow_graph: StrictMultiDiGraph) -> None:
        """
        Remove this flow's contribution from the provided `flow_graph`.

        Args:
            flow_graph (StrictMultiDiGraph): The network graph from which to remove this flow's usage.
        """
        remove_flow_from_graph(flow_graph, flow_index=self.flow_index)
        self.placed_flow = 0.0
