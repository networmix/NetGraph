"""Traffic matrix containers.

Provides `TrafficMatrixSet`, a named collection of `TrafficDemand` lists
used as input to demand expansion and placement. This module contains input
containers, not analysis results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ngraph.demand.spec import TrafficDemand


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
        """Get default traffic matrix.

        Returns the matrix named 'default' if it exists. If there is exactly
        one matrix, returns that single matrix. If there are no matrices,
        returns an empty list. If there are multiple matrices and none is
        named 'default', raises an error.

        Returns:
            List of TrafficDemand objects for the default matrix.

        Raises:
            ValueError: If multiple matrices exist without a 'default' matrix.
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
        all_demands: list[TrafficDemand] = []
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
