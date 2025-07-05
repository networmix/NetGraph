"""Notebook analysis components for NetGraph workflow results.

This package provides specialized analyzers for processing and visualizing network analysis
results in Jupyter notebooks. Each component handles specific data types and provides
both programmatic analysis and interactive display capabilities.

Core Components:
    NotebookAnalyzer: Abstract base class defining the analysis interface.
    AnalysisContext: Immutable dataclass containing execution context.

Data Analyzers:
    CapacityMatrixAnalyzer: Processes capacity envelope data from network flow analysis.
    FlowAnalyzer: Processes maximum flow calculation results.
    SummaryAnalyzer: Aggregates results across all workflow steps.

Utility Components:
    PackageManager: Handles runtime dependency verification and installation.
    DataLoader: Provides JSON file loading with detailed error handling.
"""

import itables.options as itables_opt
import matplotlib.pyplot as plt
from itables import show

from .base import AnalysisContext, NotebookAnalyzer
from .capacity_matrix import CapacityMatrixAnalyzer
from .data_loader import DataLoader
from .flow_analyzer import FlowAnalyzer
from .package_manager import PackageManager
from .summary import SummaryAnalyzer

__all__ = [
    "NotebookAnalyzer",
    "AnalysisContext",
    "CapacityMatrixAnalyzer",
    "FlowAnalyzer",
    "SummaryAnalyzer",
    "PackageManager",
    "DataLoader",
    "show",
    "itables_opt",
    "plt",
]
