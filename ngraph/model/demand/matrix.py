"""Demand set containers.

Provides `DemandSet`, a named collection of `TrafficDemand` lists
used as input to demand expansion and placement. This module contains input
containers, not analysis results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ngraph.model.demand.spec import TrafficDemand


@dataclass
class DemandSet:
    """Named collection of TrafficDemand lists.

    This mutable container maps set names to lists of TrafficDemand objects,
    allowing management of multiple demand sets for analysis.

    Attributes:
        sets: Dictionary mapping set names to TrafficDemand lists.
    """

    sets: dict[str, list[TrafficDemand]] = field(default_factory=dict)

    def add(self, name: str, demands: list[TrafficDemand]) -> None:
        """Add a demand list to the collection.

        Args:
            name: Set name identifier.
            demands: List of TrafficDemand objects for this set.
        """
        self.sets[name] = demands

    def get_set(self, name: str) -> list[TrafficDemand]:
        """Get a specific demand set by name.

        Args:
            name: Name of the demand set to retrieve.

        Returns:
            List of TrafficDemand objects for the named set.

        Raises:
            KeyError: If the set name doesn't exist.
        """
        return self.sets[name]

    def get_default_set(self) -> list[TrafficDemand]:
        """Get default demand set.

        Returns the set named 'default' if it exists. If there is exactly
        one set, returns that single set. If there are no sets,
        returns an empty list. If there are multiple sets and none is
        named 'default', raises an error.

        Returns:
            List of TrafficDemand objects for the default set.

        Raises:
            ValueError: If multiple sets exist without a 'default' set.
        """
        if not self.sets:
            return []

        if "default" in self.sets:
            return self.sets["default"]

        if len(self.sets) == 1:
            return next(iter(self.sets.values()))

        raise ValueError(
            f"Multiple demand sets exist ({list(self.sets.keys())}) but no 'default' set. "
            f"Please specify which set to use or add a 'default' set."
        )

    def get_all_demands(self) -> list[TrafficDemand]:
        """Get all traffic demands from all sets combined.

        Returns:
            Flattened list of all TrafficDemand objects across all sets.
        """
        all_demands: list[TrafficDemand] = []
        for demands in self.sets.values():
            all_demands.extend(demands)
        return all_demands

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary mapping set names to lists of TrafficDemand dictionaries.
        """
        return {
            name: [demand.__dict__ for demand in demands]
            for name, demands in self.sets.items()
        }
