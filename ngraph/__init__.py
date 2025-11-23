"""NetGraph: Network modeling and analysis library.

Provides interfaces for network topology modeling, traffic analysis, and
capacity planning. Exposes selected modules and artifact types at the package
root for convenience.
"""

from __future__ import annotations

from . import cli, logging
from .model.demand.matrix import TrafficMatrixSet
from .results.artifacts import CapacityEnvelope

__all__ = [
    "cli",
    "logging",
    "CapacityEnvelope",
    "TrafficMatrixSet",
]
