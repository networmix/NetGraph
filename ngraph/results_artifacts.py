"""CapacityEnvelope, TrafficMatrixSet, PlacementResultSet, and FailurePolicySet classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

from ngraph.traffic_demand import TrafficDemand
from ngraph.traffic_manager import TrafficResult

if TYPE_CHECKING:
    from ngraph.failure_policy import FailurePolicy


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

    def get_matrix(self, name: str) -> list[TrafficDemand]:
        """Get a specific traffic matrix by name.

        Args:
            name: Name of the matrix to retrieve.

        Returns:
            List of TrafficDemand objects for the named matrix.

        Raises:
            KeyError: If the matrix name doesn't exist.
        """
        return self.matrices[name]

    def get_default_matrix(self) -> list[TrafficDemand]:
        """Get the default traffic matrix.

        Returns the matrix named 'default' if it exists, otherwise returns
        the first matrix if there's only one, otherwise raises an error.

        Returns:
            List of TrafficDemand objects for the default matrix.

        Raises:
            ValueError: If no matrices exist or multiple matrices exist
                         without a 'default' matrix.
        """
        if not self.matrices:
            return []

        if "default" in self.matrices:
            return self.matrices["default"]

        if len(self.matrices) == 1:
            return next(iter(self.matrices.values()))

        raise ValueError(
            f"Multiple matrices exist ({list(self.matrices.keys())}) but no 'default' matrix. "
            f"Please specify which matrix to use or add a 'default' matrix."
        )

    def get_all_demands(self) -> list[TrafficDemand]:
        """Get all traffic demands from all matrices combined.

        Returns:
            Flattened list of all TrafficDemand objects across all matrices.
        """
        all_demands = []
        for demands in self.matrices.values():
            all_demands.extend(demands)
        return all_demands

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


@dataclass
class FailurePolicySet:
    """Named collection of FailurePolicy objects.

    This mutable container maps failure policy names to FailurePolicy objects,
    allowing management of multiple failure policies for analysis.

    Attributes:
        policies: Dictionary mapping failure policy names to FailurePolicy objects.
    """

    policies: dict[str, "FailurePolicy"] = field(default_factory=dict)

    def add(self, name: str, policy: "FailurePolicy") -> None:
        """Add a failure policy to the collection.

        Args:
            name: Failure policy name identifier.
            policy: FailurePolicy object for this failure policy.
        """
        self.policies[name] = policy

    def get_policy(self, name: str) -> "FailurePolicy":
        """Get a specific failure policy by name.

        Args:
            name: Name of the policy to retrieve.

        Returns:
            FailurePolicy object for the named policy.

        Raises:
            KeyError: If the policy name doesn't exist.
        """
        return self.policies[name]

    def get_default_policy(self) -> "FailurePolicy | None":
        """Get the default failure policy.

        Returns the policy named 'default' if it exists, otherwise returns
        the first policy if there's only one, otherwise returns None.

        Returns:
            FailurePolicy object for the default policy, or None if no policies exist.

        Raises:
            ValueError: If multiple policies exist without a 'default' policy.
        """
        if not self.policies:
            return None

        if "default" in self.policies:
            return self.policies["default"]

        if len(self.policies) == 1:
            return next(iter(self.policies.values()))

        raise ValueError(
            f"Multiple failure policies exist ({list(self.policies.keys())}) but no 'default' policy. "
            f"Please specify which policy to use or add a 'default' policy."
        )

    def get_all_policies(self) -> list["FailurePolicy"]:
        """Get all failure policies from the collection.

        Returns:
            List of all FailurePolicy objects.
        """
        return list(self.policies.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary mapping failure policy names to FailurePolicy dictionaries.
        """
        return {name: policy.to_dict() for name, policy in self.policies.items()}


@dataclass
class CapacityEnvelope:
    """Frequency-based capacity envelope that stores capacity values as frequencies.

    This approach is more memory-efficient for Monte Carlo analysis where we care
    about statistical distributions rather than individual sample order.

    Attributes:
        source_pattern: Regex pattern used to select source nodes.
        sink_pattern: Regex pattern used to select sink nodes.
        mode: Flow analysis mode ("combine" or "pairwise").
        frequencies: Dictionary mapping capacity values to their occurrence counts.
        min_capacity: Minimum observed capacity.
        max_capacity: Maximum observed capacity.
        mean_capacity: Mean capacity across all samples.
        stdev_capacity: Standard deviation of capacity values.
        total_samples: Total number of samples represented.
    """

    source_pattern: str
    sink_pattern: str
    mode: str
    frequencies: Dict[float, int]
    min_capacity: float
    max_capacity: float
    mean_capacity: float
    stdev_capacity: float
    total_samples: int

    @classmethod
    def from_values(
        cls, source_pattern: str, sink_pattern: str, mode: str, values: List[float]
    ) -> "CapacityEnvelope":
        """Create frequency-based envelope from a list of capacity values.

        Args:
            source_pattern: Source node pattern.
            sink_pattern: Sink node pattern.
            mode: Flow analysis mode.
            values: List of capacity values from Monte Carlo iterations.

        Returns:
            CapacityEnvelope instance.
        """
        if not values:
            raise ValueError("Cannot create envelope from empty values list")

        # Build frequency map
        frequencies = {}
        for value in values:
            frequencies[value] = frequencies.get(value, 0) + 1

        # Calculate statistics
        min_capacity = min(values)
        max_capacity = max(values)
        mean_capacity = sum(values) / len(values)

        # Calculate standard deviation
        variance = sum((x - mean_capacity) ** 2 for x in values) / len(values)
        stdev_capacity = variance**0.5

        return cls(
            source_pattern=source_pattern,
            sink_pattern=sink_pattern,
            mode=mode,
            frequencies=frequencies,
            min_capacity=min_capacity,
            max_capacity=max_capacity,
            mean_capacity=mean_capacity,
            stdev_capacity=stdev_capacity,
            total_samples=len(values),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source_pattern,
            "sink": self.sink_pattern,
            "mode": self.mode,
            "frequencies": self.frequencies,
            "min": self.min_capacity,
            "max": self.max_capacity,
            "mean": self.mean_capacity,
            "stdev": self.stdev_capacity,
            "total_samples": self.total_samples,
        }

    def get_percentile(self, percentile: float) -> float:
        """Calculate percentile from frequency distribution.

        Args:
            percentile: Percentile to calculate (0-100).

        Returns:
            Capacity value at the specified percentile.
        """
        if not (0 <= percentile <= 100):
            raise ValueError("Percentile must be between 0 and 100")

        target_count = (percentile / 100.0) * self.total_samples

        # Sort capacities and accumulate counts
        sorted_capacities = sorted(self.frequencies.keys())
        cumulative_count = 0

        for capacity in sorted_capacities:
            cumulative_count += self.frequencies[capacity]
            if cumulative_count >= target_count:
                return capacity

        return sorted_capacities[-1]  # Return max if we somehow don't find it

    def expand_to_values(self) -> List[float]:
        """Expand frequency map back to individual values (for backward compatibility).

        Returns:
            List of capacity values reconstructed from frequencies.
        """
        values = []
        for capacity, count in self.frequencies.items():
            values.extend([capacity] * count)
        return values


@dataclass
class FailurePatternResult:
    """Result for a unique failure pattern with associated capacity matrix.

    Attributes:
        excluded_nodes: List of failed node IDs.
        excluded_links: List of failed link IDs.
        capacity_matrix: Dictionary mapping flow keys to capacity values.
        count: Number of times this pattern occurred.
        is_baseline: Whether this represents the baseline (no failures) case.
    """

    excluded_nodes: List[str]
    excluded_links: List[str]
    capacity_matrix: Dict[str, float]
    count: int
    is_baseline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "excluded_nodes": self.excluded_nodes,
            "excluded_links": self.excluded_links,
            "capacity_matrix": self.capacity_matrix,
            "count": self.count,
            "is_baseline": self.is_baseline,
        }

    @property
    def pattern_key(self) -> str:
        """Generate a unique key for this failure pattern."""
        if self.is_baseline:
            return "baseline"

        # Create deterministic key from excluded entities
        excluded_str = ",".join(sorted(self.excluded_nodes + self.excluded_links))
        return f"pattern_{hash(excluded_str) & 0x7FFFFFFF:08x}"
