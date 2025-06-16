"""NetGraph: High-performance network modeling and analysis library.

Provides a convenient interface for network topology modeling, traffic analysis,
and capacity planning. Exports key modules and result classes for easy access
to the most commonly used NetGraph functionality.
"""

from __future__ import annotations

from . import cli, config, logging, transform
from .results_artifacts import CapacityEnvelope, PlacementResultSet, TrafficMatrixSet

__all__ = [
    "cli",
    "config",
    "logging",
    "transform",
    "CapacityEnvelope",
    "PlacementResultSet",
    "TrafficMatrixSet",
]
