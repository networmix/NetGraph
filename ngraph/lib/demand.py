from __future__ import annotations

from typing import Optional, Tuple

from ngraph.lib.graph import NodeID, StrictMultiDiGraph
from ngraph.lib.flow_policy import FlowPolicy


class Demand:
    """
    Represents a network demand between two nodes.

    A Demand can be realized through one or more flows.
    """

    def __init__(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        volume: float,
        demand_class: int = 0,
    ) -> None:
        """
        Initializes a Demand instance.

        Args:
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            volume: The total volume of the demand.
            demand_class: An integer representing the demand's class or priority.
        """
        self.src_node: NodeID = src_node
        self.dst_node: NodeID = dst_node
        self.volume: float = volume
        self.demand_class: int = demand_class
        self.placed_demand: float = 0.0

    def __lt__(self, other: Demand) -> bool:
        """Compares Demands based on their demand class."""
        return self.demand_class < other.demand_class

    def __str__(self) -> str:
        """Returns a string representation of the Demand."""
        return (
            f"Demand(src_node={self.src_node}, dst_node={self.dst_node}, "
            f"volume={self.volume}, demand_class={self.demand_class}, placed_demand={self.placed_demand})"
        )

    def place(
        self,
        flow_graph: StrictMultiDiGraph,
        flow_policy: FlowPolicy,
        max_fraction: float = 1.0,
        max_placement: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Places demand volume onto the network graph using the specified flow policy.

        The function computes the remaining volume to place, applies any maximum
        placement or fraction constraints, and delegates the flow placement to the
        provided flow policy. It then updates the placed demand.

        Args:
            flow_graph: The network graph on which flows are placed.
            flow_policy: The flow policy used to place the demand.
            max_fraction: Maximum fraction of the total demand volume to place in this call.
            max_placement: Optional absolute limit on the volume to place.

        Returns:
            A tuple (placed, remaining) where 'placed' is the volume successfully placed,
            and 'remaining' is the volume that could not be placed.
        """
        to_place = self.volume - self.placed_demand

        if max_placement is not None:
            to_place = min(to_place, max_placement)

        if max_fraction > 0:
            to_place = min(to_place, self.volume * max_fraction)
        else:
            # When max_fraction is non-positive, place the entire volume only if infinite;
            # otherwise, no placement is performed.
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
