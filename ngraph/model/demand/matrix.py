"""Demand set containers.

`DemandSet` holds named `TrafficDemand` lists as input to demand expansion and
placement. These are input containers, not analysis results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ngraph.model.demand.spec import TrafficDemand


@dataclass
class DemandSet:
    """Named collection of TrafficDemand lists.

    Attributes:
        sets: Dictionary mapping set names to TrafficDemand lists.
    """

    sets: dict[str, list[TrafficDemand]] = field(default_factory=dict)

    def add(self, name: str, demands: list[TrafficDemand]) -> None:
        """Add a demand list, replacing any set already stored under `name`.

        Args:
            name: Set name identifier.
            demands: TrafficDemand objects for this set; stored by reference.
        """
        self.sets[name] = demands

    def get_set(self, name: str) -> list[TrafficDemand]:
        """Get a specific demand set by name.

        Args:
            name: Name of the demand set to retrieve.

        Returns:
            The stored list for that set, not a copy: mutating it mutates the
            DemandSet.

        Raises:
            KeyError: If the set name doesn't exist.
        """
        return self.sets[name]

    def get_default_set(self) -> list[TrafficDemand]:
        """Get default demand set.

        Prefers the set named 'default'. Falls back to the sole set when
        exactly one exists, and to an empty list when there are none.

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
            A new list of every TrafficDemand, concatenated in set insertion
            order.
        """
        all_demands: list[TrafficDemand] = []
        for demands in self.sets.values():
            all_demands.extend(demands)
        return all_demands
