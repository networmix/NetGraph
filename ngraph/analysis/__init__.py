"""Network analysis API.

This module provides the primary entry point for network analysis in NetGraph.

Usage:
    from ngraph import analyze

    # One-off analysis
    flow = analyze(network).max_flow("^A$", "^B$")

    # Efficient repeated analysis (bound context)
    ctx = analyze(network, source="^A$", sink="^B$")
    baseline = ctx.max_flow()
    degraded = ctx.max_flow(excluded_links=failed_links)
"""

from __future__ import annotations

from ngraph.analysis.context import LARGE_CAPACITY as LARGE_CAPACITY
from ngraph.analysis.context import (
    AnalysisContext,
    AugmentationEdge,
    analyze,
)
from ngraph.analysis.context import build_edge_mask as build_edge_mask
from ngraph.analysis.context import build_node_mask as build_node_mask
from ngraph.analysis.demand import (
    DemandExpansion,
    ExpandedDemand,
    expand_demands,
)
from ngraph.analysis.failure_manager import AnalysisFunction, FailureManager
from ngraph.analysis.functions import (
    build_demand_context,
    build_maxflow_context,
    demand_placement_analysis,
    max_flow_analysis,
    sensitivity_analysis,
)
from ngraph.analysis.placement import (
    CACHEABLE_PRESETS,
    PlacementEntry,
    PlacementResult,
    PlacementSummary,
    place_demands,
)

__all__ = [
    # Primary API
    "analyze",
    "AnalysisContext",
    "AugmentationEdge",
    # Placement
    "CACHEABLE_PRESETS",
    "PlacementEntry",
    "PlacementResult",
    "PlacementSummary",
    "place_demands",
    # Demand expansion
    "DemandExpansion",
    "ExpandedDemand",
    "expand_demands",
    # Analysis functions
    "build_demand_context",
    "build_maxflow_context",
    "demand_placement_analysis",
    "max_flow_analysis",
    "sensitivity_analysis",
    # Failure analysis
    "AnalysisFunction",
    "FailureManager",
]
