"""Shared typing constructs for NetGraph.

This package defines the public `Cost` and `EdgeDir` aliases, the `EdgeSelect`,
`FlowPlacement`, and `Mode` enums, and the edge-reference DTOs `EdgeRef` and
`MaxFlowResult`. Apart from enum parsing helpers it holds no runtime logic.
"""

from ngraph.types.base import Cost, EdgeSelect, FlowPlacement, Mode
from ngraph.types.dto import EdgeDir, EdgeRef, MaxFlowResult

__all__ = [
    # Enums
    "Mode",
    "FlowPlacement",
    "EdgeSelect",
    # Type aliases and constants
    "Cost",
    "EdgeDir",
    # DTOs
    "EdgeRef",
    "MaxFlowResult",
]
