from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ngraph.lib.flow_policy import FlowPolicy
from ngraph.lib.graph import NodeID, StrictMultiDiGraph


@dataclass
class Demand:
    """
    Represents a network demand between two nodes. It is realized via one or more
    flows through a single FlowPolicy.
    """

    src_node: NodeID
    dst_node: NodeID
    volume: float
    demand_class: int = 0
    flow_policy: Optional[FlowPolicy] = None
    placed_demand: float = field(default=0.0, init=False)

    def __lt__(self, other: Demand) -> bool:
        """
        Compare Demands by their demand_class (priority). A lower demand_class
        indicates higher priority, so it should come first in sorting.

        Args:
            other (Demand): Demand to compare against.

        Returns:
            bool: True if self has higher priority (lower class value).
        """
        return self.demand_class < other.demand_class

    def __str__(self) -> str:
        """
        String representation showing src, dst, volume, priority, and placed_demand.
        """
        return (
            f"Demand(src_node={self.src_node}, dst_node={self.dst_node}, "
            f"volume={self.volume}, demand_class={self.demand_class}, "
            f"placed_demand={self.placed_demand})"
        )

    def place(
        self,
        flow_graph: StrictMultiDiGraph,
        max_fraction: float = 1.0,
        max_placement: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Places demand volume onto the network via self.flow_policy.

        Args:
            flow_graph (StrictMultiDiGraph): The graph to place flows onto.
            max_fraction (float): The fraction of the remaining demand to place now.
            max_placement (Optional[float]): An absolute upper bound on volume.

        Returns:
            Tuple[float, float]:
                placed_now: Volume placed in this call.
                remaining: Volume that could not be placed in this call.

        Raises:
            RuntimeError: If no FlowPolicy is set on this Demand.
            ValueError: If max_fraction is outside [0, 1].
        """
        if self.flow_policy is None:
            raise RuntimeError("No FlowPolicy set on this Demand.")

        if not (0 <= max_fraction <= 1):
            raise ValueError("max_fraction must be in the range [0, 1].")

        to_place = self.volume - self.placed_demand
        if max_placement is not None:
            to_place = min(to_place, max_placement)

        if max_fraction > 0:
            to_place = min(to_place, self.volume * max_fraction)
        else:
            # If max_fraction <= 0, do not place any new volume (unless volume is infinite).
            to_place = self.volume if self.volume == float("inf") else 0.0

        # Delegate flow placement
        self.flow_policy.place_demand(
            flow_graph,
            self.src_node,
            self.dst_node,
            self.demand_class,
            to_place,
        )

        # placed_now is the difference from the old placed_demand
        placed_now = self.flow_policy.placed_demand - self.placed_demand
        self.placed_demand = self.flow_policy.placed_demand
        remaining = to_place - placed_now

        return placed_now, remaining
