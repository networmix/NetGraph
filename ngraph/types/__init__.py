"""Shared typing constructs for NetGraph.

This package defines public type aliases and protocols used across the codebase
to describe nodes, edges, demands, and workflow interfaces. It centralizes
typing to improve readability and static analysis and contains no runtime logic.
"""

from ngraph.types.base import MIN_CAP, MIN_FLOW, Cost, EdgeSelect, FlowPlacement, Mode
from ngraph.types.dto import EdgeDir, EdgeRef, MaxFlowResult

__all__ = [
    # Enums
    "Mode",
    "FlowPlacement",
    "EdgeSelect",
    # Type aliases and constants
    "Cost",
    "MIN_CAP",
    "MIN_FLOW",
    "EdgeDir",
    # DTOs
    "EdgeRef",
    "MaxFlowResult",
]
