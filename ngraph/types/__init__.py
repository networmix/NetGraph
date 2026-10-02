"""Shared typing constructs for NetGraph.

Public `Cost` and `EdgeDir` aliases, the `EdgeSelect`, `FlowPlacement`, and
`Mode` enums, and the DTOs `EdgeRef` and `MaxFlowResult`. Apart from enum
parsing helpers there is no runtime logic here.
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
