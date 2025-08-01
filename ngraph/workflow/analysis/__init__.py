"""Notebook analysis components for NetGraph workflow results.

This package provides specialized analyzers for processing and visualizing network analysis
results in Jupyter notebooks. Each component handles specific data types and provides
both programmatic analysis and interactive display capabilities.

Core Components:
    NotebookAnalyzer: Abstract base class defining the analysis interface.
    AnalysisContext: Immutable dataclass containing execution context.
    AnalysisRegistry: Registry mapping workflow steps to analysis modules.

Data Analyzers:
    CapacityMatrixAnalyzer: Processes capacity envelope data from network flow analysis.
        - Works with workflow step results (workflow mode)
        - Works directly with CapacityEnvelopeResults objects (direct mode)
    FlowAnalyzer: Processes maximum flow calculation results.
    SummaryAnalyzer: Aggregates results across all workflow steps.

Utility Components:
    PackageManager: Handles runtime dependency verification and installation.
    DataLoader: Provides JSON file loading with detailed error handling.

Convenience Functions:
    analyze_capacity_envelopes: Create analyzer for CapacityEnvelopeResults objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import itables.options as itables_opt
import matplotlib.pyplot as plt
from itables import show

from .base import AnalysisContext, NotebookAnalyzer
from .capacity_matrix import CapacityMatrixAnalyzer
from .data_loader import DataLoader
from .flow_analyzer import FlowAnalyzer
from .package_manager import PackageManager
from .registry import AnalysisConfig, AnalysisRegistry, get_default_registry
from .summary import SummaryAnalyzer

if TYPE_CHECKING:
    from ngraph.monte_carlo.results import CapacityEnvelopeResults


def analyze_capacity_envelopes(
    results: CapacityEnvelopeResults,
) -> CapacityMatrixAnalyzer:
    """Create CapacityMatrixAnalyzer configured for direct CapacityEnvelopeResults analysis.

    Args:
        results: CapacityEnvelopeResults object from FailureManager convenience methods

    Returns:
        CapacityMatrixAnalyzer instance ready for analysis and visualization

    Example:
        >>> from ngraph.workflow.analysis import analyze_capacity_envelopes
        >>> results = failure_manager.run_max_flow_monte_carlo(...)
        >>> analyzer = analyze_capacity_envelopes(results)
        >>> analyzer.analyze_and_display_envelope_results(results)
    """
    return CapacityMatrixAnalyzer()


__all__ = [
    "NotebookAnalyzer",
    "AnalysisContext",
    "AnalysisConfig",
    "AnalysisRegistry",
    "get_default_registry",
    "CapacityMatrixAnalyzer",
    "FlowAnalyzer",
    "SummaryAnalyzer",
    "PackageManager",
    "DataLoader",
    "analyze_capacity_envelopes",
    "show",
    "itables_opt",
    "plt",
]
