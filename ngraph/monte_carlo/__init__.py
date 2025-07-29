"""Monte Carlo analysis functions for FailureManager simulations.

This module provides picklable analysis functions that can be used with FailureManager
for Monte Carlo failure analysis patterns. These functions are designed to be:
- Picklable for multiprocessing support
- Cache-friendly with hashable parameters
- Reusable across different failure scenarios

Monte Carlo Analysis Functions:
    max_flow_analysis: Maximum flow capacity analysis between node groups
    demand_placement_analysis: Traffic demand placement success analysis
    sensitivity_analysis: Component criticality analysis

Result Objects:
    CapacityEnvelopeResults: Structured results for capacity envelope analysis
    DemandPlacementResults: Structured results for demand placement analysis
    SensitivityResults: Structured results for sensitivity analysis
"""

from .functions import (
    demand_placement_analysis,
    max_flow_analysis,
    sensitivity_analysis,
)
from .results import (
    CapacityEnvelopeResults,
    DemandPlacementResults,
    SensitivityResults,
)

__all__ = [
    "max_flow_analysis",
    "demand_placement_analysis",
    "sensitivity_analysis",
    "CapacityEnvelopeResults",
    "DemandPlacementResults",
    "SensitivityResults",
]
