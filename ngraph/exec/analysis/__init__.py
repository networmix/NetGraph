"""Analysis functions for network evaluation.

Provides domain-specific analysis functions designed for use with FailureManager.
Functions follow the AnalysisFunction protocol: they accept a network with exclusion
sets and return structured results. All functions use only hashable parameters to
support multiprocessing and caching.
"""

from .flow import (
    demand_placement_analysis,
    max_flow_analysis,
    sensitivity_analysis,
)

__all__ = [
    "max_flow_analysis",
    "demand_placement_analysis",
    "sensitivity_analysis",
]
