"""Registry mapping workflow step types to notebook analyzers.

Provides a simple mapping from workflow ``step_type`` identifiers to analyzer
configurations. The default registry wires common NetGraph analysis steps to
their notebook components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Type

from .base import NotebookAnalyzer


@dataclass
class AnalysisConfig:
    """Configuration for a single analyzer binding."""

    analyzer_class: Type[NotebookAnalyzer]
    method_name: str = "analyze_and_display"
    kwargs: dict[str, Any] = field(default_factory=dict)
    section_title: Optional[str] = None
    enabled: bool = True


@dataclass
class AnalysisRegistry:
    """Collection of analyzer bindings keyed by workflow step type."""

    _mappings: dict[str, list[AnalysisConfig]] = field(default_factory=dict)

    def register(
        self,
        step_type: str,
        analyzer_class: Type[NotebookAnalyzer],
        method_name: str = "analyze_and_display",
        section_title: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        cfg = AnalysisConfig(
            analyzer_class=analyzer_class,
            method_name=method_name,
            kwargs=kwargs,
            section_title=section_title or f"{analyzer_class.__name__} Analysis",
        )
        self._mappings.setdefault(step_type, []).append(cfg)

    def get_analyses(self, step_type: str) -> list[AnalysisConfig]:
        return [c for c in self._mappings.get(step_type, []) if c.enabled]

    def get_all_step_types(self) -> list[str]:
        return list(self._mappings.keys())


def get_default_registry() -> AnalysisRegistry:
    """Return standard analyzer mapping for common workflow steps.

    Includes bindings for ``NetworkStats``, ``MaximumSupportedDemand``,
    ``TrafficMatrixPlacement``, and ``MaxFlow``.
    """

    from .bac import BACAnalyzer
    from .capacity_matrix import CapacityMatrixAnalyzer
    from .latency import LatencyAnalyzer
    from .msd import MSDAnalyzer
    from .placement_matrix import PlacementMatrixAnalyzer
    from .summary import SummaryAnalyzer

    reg = AnalysisRegistry()

    # Network-wide overview
    reg.register(
        "NetworkStats",
        SummaryAnalyzer,
        method_name="analyze_network_stats",
        section_title="Network Statistics",
    )

    # MSD
    reg.register(
        "MaximumSupportedDemand", MSDAnalyzer, section_title="Maximum Supported Demand"
    )

    # Traffic placement
    reg.register(
        "TrafficMatrixPlacement",
        PlacementMatrixAnalyzer,
        method_name="analyze_and_display_step",
        section_title="Placement Matrix",
    )
    reg.register(
        "TrafficMatrixPlacement",
        BACAnalyzer,
        method_name="analyze_and_display",
        section_title="Bandwidth-Availability (Placement)",
        mode="placement",
        try_overlay=True,
    )
    reg.register(
        "TrafficMatrixPlacement",
        LatencyAnalyzer,
        method_name="analyze_and_display",
        section_title="Latency & Stretch (Placement)",
    )

    # MaxFlow capacity
    reg.register(
        "MaxFlow",
        CapacityMatrixAnalyzer,
        method_name="analyze_and_display_step",
        section_title="Capacity Matrix (MaxFlow)",
    )
    reg.register(
        "MaxFlow",
        BACAnalyzer,
        method_name="analyze_and_display",
        section_title="Bandwidth-Availability (MaxFlow)",
        mode="maxflow",
        try_overlay=True,
    )
    reg.register(
        "MaxFlow",
        LatencyAnalyzer,
        method_name="analyze_and_display",
        section_title="Latency & Stretch (MaxFlow)",
    )

    return reg
