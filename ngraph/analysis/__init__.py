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

from typing import TYPE_CHECKING, List, Optional

# Internal helpers - importable but not part of public API.
# Redundant aliases silence F401 while keeping them accessible.
from ngraph.analysis.context import LARGE_CAPACITY as LARGE_CAPACITY
from ngraph.analysis.context import (
    AnalysisContext,
    AugmentationEdge,
)
from ngraph.analysis.context import build_edge_mask as build_edge_mask
from ngraph.analysis.context import build_node_mask as build_node_mask
from ngraph.types.base import Mode

if TYPE_CHECKING:
    from ngraph.model.network import Network


def analyze(
    network: "Network",
    *,
    source: Optional[str] = None,
    sink: Optional[str] = None,
    mode: Mode = Mode.COMBINE,
    augmentations: Optional[List[AugmentationEdge]] = None,
) -> AnalysisContext:
    """Create an analysis context for the network.

    This is THE primary entry point for network analysis in NetGraph.

    Args:
        network: Network topology to analyze.
        source: Optional source group pattern. If provided with sink,
                creates bound context with pre-built pseudo-nodes for
                efficient repeated flow analysis.
        sink: Optional sink group pattern.
        mode: Group mode (COMBINE or PAIRWISE). Only used if bound.
        augmentations: Optional custom augmentation edges.

    Returns:
        AnalysisContext ready for analysis calls.

    Examples:
        One-off analysis (unbound context):

            flow = analyze(network).max_flow("^A$", "^B$")
            paths = analyze(network).shortest_paths("^A$", "^B$")

        Efficient repeated analysis (bound context):

            ctx = analyze(network, source="^dc/", sink="^edge/")
            baseline = ctx.max_flow()
            degraded = ctx.max_flow(excluded_links=failed_links)

        Multiple exclusion scenarios:

            ctx = analyze(network, source="^A$", sink="^B$")
            for scenario in failure_scenarios:
                result = ctx.max_flow(excluded_links=scenario)
    """
    return AnalysisContext.from_network(
        network,
        source=source,
        sink=sink,
        mode=mode,
        augmentations=augmentations,
    )


__all__ = [
    "analyze",
    "AnalysisContext",
    "AugmentationEdge",
]
