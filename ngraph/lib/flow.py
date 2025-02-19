from __future__ import annotations
from typing import (
    Hashable,
    NamedTuple,
    Optional,
    Set,
    Tuple,
)
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
        src_node: The source node of the flow.
        dst_node: The destination node of the flow.
        flow_class: An integer representing the 'class' of this flow (e.g. a traffic class).
        flow_id: A unique integer ID for this flow.
    """

    src_node: NodeID
    dst_node: NodeID
    flow_class: int
    flow_id: int


class Flow:
    """
    Represents a fraction of demand routed along a given PathBundle.

    In traffic-engineering scenarios, a `Flow` object can model:
      - An MPLS LSP/tunnel,
      - IP forwarding behavior (with ECMP),
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
            path_bundle: A `PathBundle` representing the set of paths this flow will use.
            flow_index: A unique identifier (can be any hashable) that tags this flow
                in the network (e.g. an MPLS label, a tuple of (src, dst, class, id), etc.).
            excluded_edges: An optional set of edges to exclude from consideration.
            excluded_nodes: An optional set of nodes to exclude from consideration.
        """
        self.path_bundle: PathBundle = path_bundle
        self.flow_index: Hashable = flow_index
        self.excluded_edges: Set[EdgeID] = excluded_edges or set()
        self.excluded_nodes: Set[NodeID] = excluded_nodes or set()

        # Store convenience references for the Flow's endpoints
        self.src_node: NodeID = path_bundle.src_node
        self.dst_node: NodeID = path_bundle.dst_node

        # Track how much flow has been successfully placed so far
        self.placed_flow: float = 0.0

    def __str__(self) -> str:
        """String representation of the Flow."""
        return f"Flow(flow_index={self.flow_index}, placed_flow={self.placed_flow})"

    def place_flow(
        self,
        flow_graph: StrictMultiDiGraph,
        to_place: float,
        flow_placement: FlowPlacement,
    ) -> Tuple[float, float]:
        """
        Attempt to place (or update) this flow on `flow_graph`.

        Args:
            flow_graph: The network graph where flow capacities and usage are tracked.
            to_place: The amount of flow requested to be placed on this path bundle.
            flow_placement: Strategy determining how flow is distributed among parallel edges.

        Returns:
            A tuple `(placed_flow, remaining_flow)` where:
              - `placed_flow` is the amount of flow actually placed on `flow_graph`.
              - `remaining_flow` is how much of `to_place` could not be placed
                (due to capacity limits or other constraints).
        """
        placed_flow = 0.0

        # Only place flow if it's above the MIN_FLOW threshold
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
        Remove this flow's contribution from `flow_graph`.

        Args:
            flow_graph: The network graph from which this flow's usage should be removed.
        """
        remove_flow_from_graph(flow_graph, flow_index=self.flow_index)
        self.placed_flow = 0.0
