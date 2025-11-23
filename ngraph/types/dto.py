"""Types and data structures for algorithm analytics.

Defines immutable summary containers and aliases for algorithm outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Tuple

from ngraph.types.base import Cost

# Edge direction: 'fwd' for forward (source→target as in Link), 'rev' for reverse
EdgeDir = Literal["fwd", "rev"]


@dataclass(frozen=True)
class EdgeRef:
    """Reference to a directed edge via scenario link_id and direction.

    Replaces the old Edge = Tuple[str, str, Hashable] to provide stable,
    scenario-native edge identification across Core reorderings.

    Attributes:
        link_id: Scenario link identifier (matches Network.links keys)
        direction: 'fwd' for source→target as defined in Link; 'rev' for reverse
    """

    link_id: str
    direction: EdgeDir


@dataclass(frozen=True)
class FlowSummary:
    """Summary of max-flow computation results.

    Captures edge flows, residual capacities, reachable set, and min-cut.

    Breaking change from v1.x: Fields now use EdgeRef instead of (src, dst, key) tuples
    for stable scenario-level edge identification.

    Attributes:
        total_flow: Maximum flow value achieved.
        cost_distribution: Mapping of path cost to flow volume placed at that cost.
        min_cut: Saturated edges crossing the s-t cut.
        reachable_nodes: Nodes reachable from source in residual graph (optional).
        edge_flow: Flow amount per edge (optional, only populated when requested).
        residual_cap: Remaining capacity per edge after placement (optional).
    """

    total_flow: float
    cost_distribution: Dict[Cost, float]
    min_cut: Tuple[EdgeRef, ...]
    reachable_nodes: Tuple[str, ...] | None = None
    edge_flow: Dict[EdgeRef, float] | None = None
    residual_cap: Dict[EdgeRef, float] | None = None
