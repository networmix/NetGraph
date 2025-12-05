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
class MaxFlowResult:
    """Result of max-flow computation between a source/sink pair.

    Captures total flow, cost distribution, and optionally min-cut edges.

    Attributes:
        total_flow: Maximum flow value achieved.
        cost_distribution: Mapping of path cost to flow volume placed at that cost.
        min_cut: Saturated edges forming the min-cut (None if not computed).
    """

    total_flow: float
    cost_distribution: Dict[Cost, float]
    min_cut: Tuple[EdgeRef, ...] | None = None
