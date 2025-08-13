"""Serializable result artifacts for analysis workflows.

This module defines dataclasses that capture outputs from analyses and
simulations in a JSON-serializable form:

- `PlacementResultSet`: aggregated placement results and statistics
- `CapacityEnvelope`: frequency-based capacity distributions and optional
  aggregated flow statistics
- `FailurePatternResult`: capacity results for specific failure patterns
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ngraph.demand.manager.manager import TrafficResult


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
class CapacityEnvelope:
    """Frequency-based capacity envelope that stores capacity values as frequencies.

    This approach is memory-efficient for Monte Carlo analysis where we care
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
        flow_summary_stats: Optional dictionary with aggregated FlowSummary statistics.
                           Contains cost_distribution_stats and other flow analytics.
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
    flow_summary_stats: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_values(
        cls,
        source_pattern: str,
        sink_pattern: str,
        mode: str,
        values: List[float],
        flow_summaries: List[Any] | None = None,
    ) -> "CapacityEnvelope":
        """Create envelope from capacity values and optional flow summaries.

        Args:
            source_pattern: Source node pattern.
            sink_pattern: Sink node pattern.
            mode: Flow analysis mode.
            values: List of capacity values from Monte Carlo iterations.
            flow_summaries: Optional list of FlowSummary objects for detailed analytics.

        Returns:
            CapacityEnvelope instance with capacity statistics and optional flow analytics.

        Raises:
            ValueError: If ``values`` is empty.
        """
        if not values:
            raise ValueError("Cannot create envelope from empty values list")

        # Single pass to calculate everything efficiently
        frequencies = {}
        total_sum = 0.0
        sum_squares = 0.0
        min_capacity = float("inf")
        max_capacity = float("-inf")

        for value in values:
            # Update frequency map
            frequencies[value] = frequencies.get(value, 0) + 1

            # Update statistics
            total_sum += value
            sum_squares += value * value
            min_capacity = min(min_capacity, value)
            max_capacity = max(max_capacity, value)

        # Calculate derived statistics
        n = len(values)
        mean_capacity = total_sum / n

        # Use computational formula for variance: Var(X) = E[X²] - (E[X])²
        variance = (sum_squares / n) - (mean_capacity * mean_capacity)
        stdev_capacity = variance**0.5

        # Process flow summaries if provided
        flow_summary_stats = {}
        if flow_summaries:
            flow_summary_stats = cls._aggregate_flow_summaries(flow_summaries)

        return cls(
            source_pattern=source_pattern,
            sink_pattern=sink_pattern,
            mode=mode,
            frequencies=frequencies,
            min_capacity=min_capacity,
            max_capacity=max_capacity,
            mean_capacity=mean_capacity,
            stdev_capacity=stdev_capacity,
            total_samples=n,
            flow_summary_stats=flow_summary_stats,
        )

    @classmethod
    def _aggregate_flow_summaries(cls, flow_summaries: List[Any]) -> Dict[str, Any]:
        """Aggregate FlowSummary objects into statistical summaries.

        Args:
            flow_summaries: List of FlowSummary objects from Monte Carlo iterations.

        Returns:
            Dictionary with aggregated flow analytics including cost distribution statistics.
        """
        from collections import defaultdict

        # Aggregate cost distributions
        cost_data = defaultdict(list)  # cost -> list of flow volumes
        min_cut_frequencies = defaultdict(int)  # edge -> frequency count

        valid_summaries = [s for s in flow_summaries if s is not None]
        if not valid_summaries:
            return {}

        for summary in valid_summaries:
            # Support compact dict summaries coming from workers
            if isinstance(summary, dict):
                cd = summary.get("cost_distribution", {})
                mc = summary.get("min_cut", [])
                if isinstance(cd, dict):
                    for cost, flow_volume in cd.items():
                        cost_data[cost].append(flow_volume)
                if isinstance(mc, list):
                    for edge in mc:
                        edge_key = str(edge)
                        min_cut_frequencies[edge_key] += 1
                continue

            # Process object-like summaries with attributes
            if hasattr(summary, "cost_distribution"):
                for cost, flow_volume in getattr(
                    summary, "cost_distribution", {}
                ).items():
                    cost_data[cost].append(flow_volume)

            if hasattr(summary, "min_cut"):
                for edge in getattr(summary, "min_cut", []) or []:
                    edge_key = str(edge)
                    min_cut_frequencies[edge_key] += 1

        # Calculate cost distribution statistics
        cost_distribution_stats = {}
        for cost, volumes in cost_data.items():
            if volumes:
                cost_distribution_stats[float(cost)] = {
                    "mean": sum(volumes) / len(volumes),
                    "min": min(volumes),
                    "max": max(volumes),
                    "total_samples": len(volumes),
                    "frequencies": {vol: volumes.count(vol) for vol in set(volumes)},
                }

        return {
            "cost_distribution_stats": cost_distribution_stats,
            "min_cut_frequencies": dict(min_cut_frequencies),
            "total_flow_summaries": len(valid_summaries),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
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

        # Include flow summary stats if available
        if self.flow_summary_stats:
            result["flow_summary_stats"] = self.flow_summary_stats

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapacityEnvelope":
        """Construct a CapacityEnvelope from a dictionary.

        Args:
            data: Dictionary as produced by to_dict().

        Returns:
            CapacityEnvelope
        """
        # Frequencies keys may arrive as strings via JSON; normalize to float
        freqs_raw = data.get("frequencies", {}) or {}
        freqs: Dict[float, int] = {}
        for k, v in freqs_raw.items():
            try:
                key_f = float(k)
            except (TypeError, ValueError):
                key_f = float(k)  # Will raise again if irrecoverable
            freqs[key_f] = int(v)

        return cls(
            source_pattern=str(data.get("source", "")),
            sink_pattern=str(data.get("sink", "")),
            mode=str(data.get("mode", "combine")),
            frequencies=freqs,
            min_capacity=float(data.get("min", 0.0)),
            max_capacity=float(data.get("max", 0.0)),
            mean_capacity=float(data.get("mean", 0.0)),
            stdev_capacity=float(data.get("stdev", 0.0)),
            total_samples=int(data.get("total_samples", 0)),
            flow_summary_stats=dict(data.get("flow_summary_stats", {})),
        )

    def get_percentile(self, percentile: float) -> float:
        """Calculate percentile from frequency distribution.

        Args:
            percentile: Percentile to calculate (0-100).

        Returns:
            Capacity value at the specified percentile.

        Raises:
            ValueError: If ``percentile`` is outside [0, 100].
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
        """Expand frequency map back to individual values.

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
    _pattern_key_cache: str = field(default="", init=False, repr=False)

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
        """Generate a deterministic key for this failure pattern.

        Uses a stable SHA1 hash of the sorted excluded entity list to avoid
        Python's randomized hash() variability across processes.
        """
        if self.is_baseline:
            return "baseline"

        # Cache to avoid recomputation when accessed repeatedly
        if self._pattern_key_cache:
            return self._pattern_key_cache

        # Create deterministic key from excluded entities using fast BLAKE2s
        excluded_str = ",".join(sorted(self.excluded_nodes + self.excluded_links))
        digest = hashlib.blake2s(
            excluded_str.encode("utf-8"), digest_size=8
        ).hexdigest()
        self._pattern_key_cache = f"pattern_{digest}"
        return self._pattern_key_cache

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FailurePatternResult":
        """Construct FailurePatternResult from a dictionary."""
        return cls(
            excluded_nodes=list(data.get("excluded_nodes", [])),
            excluded_links=list(data.get("excluded_links", [])),
            capacity_matrix=dict(data.get("capacity_matrix", {})),
            count=int(data.get("count", 0)),
            is_baseline=bool(data.get("is_baseline", False)),
        )


@dataclass
class PlacementEnvelope:
    """Per-demand placement envelope keyed like capacity envelopes.

    Each envelope captures frequency distribution of placement ratio for a
    specific demand definition across Monte Carlo iterations.

    Attributes:
        source: Source selection regex or node label.
        sink: Sink selection regex or node label.
        mode: Demand expansion mode ("combine" or "pairwise").
        priority: Demand priority class.
        frequencies: Mapping of placement ratio to occurrence count.
        min: Minimum observed placement ratio.
        max: Maximum observed placement ratio.
        mean: Mean placement ratio.
        stdev: Standard deviation of placement ratio.
        total_samples: Number of iterations represented.
    """

    source: str
    sink: str
    mode: str
    priority: int
    frequencies: Dict[float, int]
    min: float
    max: float
    mean: float
    stdev: float
    total_samples: int

    @staticmethod
    def _compute_stats(values: List[float]) -> tuple[float, float, float, float]:
        n = len(values)
        total = sum(values)
        mean = total / n
        sum_squares = sum(v * v for v in values)
        variance = (sum_squares / n) - (mean * mean)
        stdev = variance**0.5
        return (min(values), max(values), mean, stdev)

    @classmethod
    def from_values(
        cls,
        source: str,
        sink: str,
        mode: str,
        priority: int,
        ratios: List[float],
        rounding_decimals: int = 4,
    ) -> "PlacementEnvelope":
        if not ratios:
            raise ValueError("Cannot create placement envelope from empty ratios list")
        freqs: Dict[float, int] = {}
        quantized: List[float] = []
        for r in ratios:
            q = round(float(r), rounding_decimals)
            quantized.append(q)
            freqs[q] = freqs.get(q, 0) + 1
        mn, mx, mean, stdev = cls._compute_stats(quantized)
        return cls(
            source=source,
            sink=sink,
            mode=mode,
            priority=int(priority),
            frequencies=freqs,
            min=mn,
            max=mx,
            mean=mean,
            stdev=stdev,
            total_samples=len(quantized),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "sink": self.sink,
            "mode": self.mode,
            "priority": self.priority,
            "frequencies": self.frequencies,
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "stdev": self.stdev,
            "total_samples": self.total_samples,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlacementEnvelope":
        """Construct a PlacementEnvelope from a dictionary."""
        freqs_raw = data.get("frequencies", {}) or {}
        freqs: Dict[float, int] = {}
        for k, v in freqs_raw.items():
            key_f = float(k)
            freqs[key_f] = int(v)

        return cls(
            source=str(data.get("source", "")),
            sink=str(data.get("sink", "")),
            mode=str(data.get("mode", "pairwise")),
            priority=int(data.get("priority", 0)),
            frequencies=freqs,
            min=float(data.get("min", 0.0)),
            max=float(data.get("max", 0.0)),
            mean=float(data.get("mean", 0.0)),
            stdev=float(data.get("stdev", 0.0)),
            total_samples=int(data.get("total_samples", 0)),
        )
