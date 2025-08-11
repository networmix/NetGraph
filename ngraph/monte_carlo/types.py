"""Typed protocols for Monte Carlo analysis IPC payloads.

Defines lightweight, serializable structures used across worker boundaries.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict


class FlowStats(TypedDict, total=False):
    """Compact per-flow statistics for aggregation.

    Keys:
        cost_distribution: Mapping of path cost to flow volume.
        edges: List of edge identifiers (string form).
        edges_kind: Meaning of edges list: 'min_cut' for capacity analysis,
            'used' for demand placement edge usage.
    """

    cost_distribution: dict[float, float]
    edges: list[str]
    edges_kind: Literal["min_cut", "used"]


class FlowResult(TypedDict, total=False):
    """Normalized result record for a flow pair in one iteration.

    Keys:
        src: Source label
        dst: Destination label
        metric: Name of metric ('capacity' or 'placement_ratio')
        value: Numeric value for the metric
        stats: Optional FlowStats with compact details
        priority: Optional demand priority (only for placement results)
    """

    src: str
    dst: str
    metric: str
    value: float
    stats: Optional[FlowStats]
    priority: int
