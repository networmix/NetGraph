"""Notebook analysis components for NetGraph workflow results.

This namespace exposes analyzers and helpers used by the notebook report
generator. It re-exports matplotlib and itables convenience objects so that
notebooks can import everything from a single place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import itables.options as itables_opt
import matplotlib.pyplot as plt
from itables import show  # pragma: no cover - display-only binding

from .bac import BACAnalyzer
from .base import AnalysisContext, NotebookAnalyzer
from .capacity_matrix import CapacityMatrixAnalyzer
from .data_loader import DataLoader
from .latency import LatencyAnalyzer
from .msd import MSDAnalyzer
from .package_manager import PackageManager
from .placement_matrix import PlacementMatrixAnalyzer
from .registry import AnalysisConfig, AnalysisRegistry, get_default_registry
from .summary import SummaryAnalyzer

if TYPE_CHECKING:
    pass

__all__ = [
    "NotebookAnalyzer",
    "AnalysisContext",
    "AnalysisConfig",
    "AnalysisRegistry",
    "get_default_registry",
    "CapacityMatrixAnalyzer",
    "PlacementMatrixAnalyzer",
    "BACAnalyzer",
    "LatencyAnalyzer",
    "MSDAnalyzer",
    "SummaryAnalyzer",
    "PackageManager",
    "DataLoader",
    "show",
    "itables_opt",
    "plt",
]
