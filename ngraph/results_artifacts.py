from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Any

from ngraph.traffic_demand import TrafficDemand
from ngraph.traffic_manager import TrafficResult


@dataclass(frozen=True)
class CapacityEnvelope:
    """Range of max-flow values measured between two node groups.

    This immutable dataclass stores capacity measurements and automatically
    computes statistical measures in __post_init__.

    Attributes:
        source_pattern: Regex pattern for selecting source nodes.
        sink_pattern: Regex pattern for selecting sink nodes.
        mode: Flow computation mode (e.g., "combine").
        capacity_values: List of measured capacity values.
        min_capacity: Minimum capacity value (computed).
        max_capacity: Maximum capacity value (computed).
        mean_capacity: Mean capacity value (computed).
        stdev_capacity: Standard deviation of capacity values (computed).
    """

    source_pattern: str
    sink_pattern: str
    mode: str = "combine"
    capacity_values: list[float] = field(default_factory=list)

    # Derived statistics - computed in __post_init__
    min_capacity: float = field(init=False)
    max_capacity: float = field(init=False)
    mean_capacity: float = field(init=False)
    stdev_capacity: float = field(init=False)

    def __post_init__(self) -> None:
        """Compute statistical measures from capacity values.

        Uses object.__setattr__ to modify frozen dataclass fields.
        Handles edge cases like empty lists and single values.
        """
        vals = self.capacity_values or [0.0]
        object.__setattr__(self, "min_capacity", min(vals))
        object.__setattr__(self, "max_capacity", max(vals))
        object.__setattr__(self, "mean_capacity", mean(vals))
        object.__setattr__(
            self, "stdev_capacity", 0.0 if len(vals) < 2 else stdev(vals)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation with all fields as primitives.
        """
        return {
            "source": self.source_pattern,
            "sink": self.sink_pattern,
            "mode": self.mode,
            "values": list(self.capacity_values),
            "min": self.min_capacity,
            "max": self.max_capacity,
            "mean": self.mean_capacity,
            "stdev": self.stdev_capacity,
        }


@dataclass
class TrafficMatrixSet:
    """Named collection of TrafficDemand lists.

    This mutable container maps scenario names to lists of TrafficDemand objects,
    allowing management of multiple traffic matrices for analysis.

    Attributes:
        matrices: Dictionary mapping scenario names to TrafficDemand lists.
    """

    matrices: dict[str, list[TrafficDemand]] = field(default_factory=dict)

    def add(self, name: str, demands: list[TrafficDemand]) -> None:
        """Add a traffic matrix to the collection.

        Args:
            name: Scenario name identifier.
            demands: List of TrafficDemand objects for this scenario.
        """
        self.matrices[name] = demands

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary mapping scenario names to lists of TrafficDemand dictionaries.
        """
        return {
            name: [demand.__dict__ for demand in demands]
            for name, demands in self.matrices.items()
        }


@dataclass(frozen=True)
class PlacementResultSet:
    """Aggregated traffic placement results from one or many runs.

    This immutable dataclass stores traffic placement results organized by case,
    with overall statistics and per-demand statistics.

    Attributes:
        results_by_case: Dictionary mapping case names to TrafficResult lists.
        overall_stats: Dictionary of overall statistics.
        demand_stats: Dictionary mapping demand keys to per-demand statistics.
    """

    results_by_case: dict[str, list[TrafficResult]] = field(default_factory=dict)
    overall_stats: dict[str, float] = field(default_factory=dict)
    demand_stats: dict[tuple[str, str, int], dict[str, float]] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Converts TrafficResult objects to dictionaries and formats demand
        statistics keys as strings for JSON compatibility.

        Returns:
            Dictionary representation with all fields as JSON-serializable primitives.
        """
        # Convert TrafficResult objects to dictionaries
        cases = {
            case: [result._asdict() for result in results]
            for case, results in self.results_by_case.items()
        }

        # Format demand statistics keys as strings
        demand_stats = {
            f"{src}->{dst}|prio={priority}": stats
            for (src, dst, priority), stats in self.demand_stats.items()
        }

        return {
            "overall_stats": self.overall_stats,
            "cases": cases,
            "demand_stats": demand_stats,
        }
