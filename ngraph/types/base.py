"""Base classes and enums for network analysis algorithms."""

from __future__ import annotations

from enum import IntEnum
from typing import Union

#: Represents numeric cost in the network (e.g. distance, latency, etc.).
Cost = Union[int, float]

#: Capacity threshold below which capacity values are treated as effectively zero.
MIN_CAP = 2**-12

#: Flow threshold below which flow values are treated as effectively zero.
MIN_FLOW = 2**-12


class EdgeSelect(IntEnum):
    """Edge selection criteria for shortest-path algorithms.

    Determines which edges are considered when finding paths between nodes.
    These map to NetGraph-Core's EdgeSelection configuration.
    """

    #: Return all edges matching the minimum cost (ECMP-style).
    ALL_MIN_COST = 1
    #: Return exactly one edge with the lowest cost (single-path).
    SINGLE_MIN_COST = 2


class FlowPlacement(IntEnum):
    """Strategies to distribute flow across parallel equal-cost paths."""

    PROPORTIONAL = 1  # Flow is split proportional to capacity (Dinic-like approach)
    EQUAL_BALANCED = 2  # Flow is equally divided among parallel paths of equal cost

    @classmethod
    def from_string(cls, value: str) -> "FlowPlacement":
        """Parse a string into a FlowPlacement enum value.

        Args:
            value: Case-insensitive string name (e.g., "proportional", "EQUAL_BALANCED").

        Returns:
            The corresponding FlowPlacement enum member.

        Raises:
            ValueError: If the string doesn't match any enum member.
        """
        try:
            return cls[value.upper()]
        except KeyError:
            valid = ", ".join(e.name for e in cls)
            raise ValueError(
                f"Invalid flow_placement '{value}'. Valid values are: {valid}"
            ) from None


class Mode(IntEnum):
    """Analysis mode for source/sink group handling.

    Determines how multiple source and sink nodes are combined for analysis.
    """

    #: Aggregate all sources into one super-source, all sinks into one super-sink.
    #: Returns single flow value representing total capacity between groups.
    COMBINE = 1

    #: Analyze each (source_group, sink_group) pair independently.
    #: Returns flow values for each pair separately.
    PAIRWISE = 2
