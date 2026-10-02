"""Serializable result artifacts for analysis workflows.

`CapacityEnvelope` captures a frequency-based capacity distribution in
JSON-serializable form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class CapacityEnvelope:
    """Capacity distribution stored as a value -> occurrence-count map.

    Monte Carlo runs repeat the same capacity values many times, so counting
    them keeps memory proportional to the number of distinct values. Individual
    sample order is not preserved.

    Attributes:
        source_pattern: Regex pattern used to select source nodes.
        sink_pattern: Regex pattern used to select sink nodes.
        mode: Flow analysis mode ("combine" or "pairwise").
        frequencies: Dictionary mapping capacity values to their occurrence counts.
        min_capacity: Minimum observed capacity.
        max_capacity: Maximum observed capacity.
        mean_capacity: Mean capacity across all samples.
        stdev_capacity: Population standard deviation of capacity values.
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
        cls,
        source_pattern: str,
        sink_pattern: str,
        mode: str,
        values: List[float],
    ) -> "CapacityEnvelope":
        """Create envelope from capacity values.

        Args:
            source_pattern: Source node pattern.
            sink_pattern: Sink node pattern.
            mode: Flow analysis mode.
            values: List of capacity values from Monte Carlo iterations.

        Returns:
            CapacityEnvelope instance with capacity statistics.

        Raises:
            ValueError: If ``values`` is empty.
        """
        if not values:
            raise ValueError("Cannot create envelope from empty values list")

        # First pass: build frequency map and compute mean
        frequencies = {}
        total_sum = 0.0
        min_capacity = float("inf")
        max_capacity = float("-inf")

        for value in values:
            frequencies[value] = frequencies.get(value, 0) + 1
            total_sum += value
            min_capacity = min(min_capacity, value)
            max_capacity = max(max_capacity, value)

        n = len(values)
        mean_capacity = total_sum / n

        # Second pass over unique values: compute variance using the
        # numerically stable formula sum((x - mean)^2) / n.
        # Iterating over the frequency map costs one step per distinct
        # value, which is small when Monte Carlo results repeat.
        variance_sum = 0.0
        for value, count in frequencies.items():
            diff = value - mean_capacity
            variance_sum += count * diff * diff
        stdev_capacity = (variance_sum / n) ** 0.5

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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapacityEnvelope":
        """Construct a CapacityEnvelope from a dictionary.

        Args:
            data: Dictionary as produced by to_dict().

        Returns:
            CapacityEnvelope with frequency keys converted to float.
        """
        # Frequencies keys may arrive as strings via JSON; normalize to float
        freqs_raw = data.get("frequencies", {}) or {}
        freqs: Dict[float, int] = {float(k): int(v) for k, v in freqs_raw.items()}

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
        )

    def get_percentile(self, percentile: float) -> float:
        """Calculate percentile from frequency distribution.

        Args:
            percentile: Percentile to calculate (0-100).

        Returns:
            Smallest capacity whose cumulative count reaches
            ``percentile / 100 * total_samples``.

        Raises:
            ValueError: If ``percentile`` is outside [0, 100].
        """
        if not (0 <= percentile <= 100):
            raise ValueError("Percentile must be between 0 and 100")

        target_count = (percentile / 100.0) * self.total_samples

        sorted_capacities = sorted(self.frequencies.keys())
        cumulative_count = 0

        for capacity in sorted_capacities:
            cumulative_count += self.frequencies[capacity]
            if cumulative_count >= target_count:
                return capacity

        # Reached only when frequency counts sum to less than total_samples.
        return sorted_capacities[-1]

    def expand_to_values(self) -> List[float]:
        """Expand frequency map back to individual values.

        Returns:
            List of capacity values reconstructed from frequencies.
        """
        values = []
        for capacity, count in self.frequencies.items():
            values.extend([capacity] * count)
        return values
