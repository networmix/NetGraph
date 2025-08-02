"""Types and data structures for algorithm analytics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from ngraph.lib.algorithms.base import Cost

# Edge identifier tuple: (source_node, destination_node, edge_key)
Edge = Tuple[str, str, str]


@dataclass(frozen=True)
class FlowSummary:
    """Summary of max-flow computation results with detailed analytics.

    This immutable data structure provides information about
    the flow solution, including edge flows, residual capacities, and
    min-cut analysis.

    Attributes:
        total_flow: The maximum flow value achieved.
        edge_flow: Flow amount on each edge, indexed by (src, dst, key).
        residual_cap: Remaining capacity on each edge after flow placement.
        reachable: Set of nodes reachable from source in residual graph.
        min_cut: List of saturated edges that form the minimum cut.
        cost_distribution: Distribution of flow volume over path costs.
            Maps each cost value to the total volume of flow placed on
            paths with that cost during sequential augmentation.
    """

    total_flow: float
    edge_flow: Dict[Edge, float]
    residual_cap: Dict[Edge, float]
    reachable: Set[str]
    min_cut: List[Edge]
    cost_distribution: Dict[Cost, float]
