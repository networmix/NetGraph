from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class TrafficDemand:
    """
    Represents a single traffic demand in a network.

    Attributes:
        source (str): The name of the source node.
        target (str): The name of the target node.
        priority (int): The priority of this traffic demand. Lower values indicate higher priority (default=0).
        demand (float): The total demand volume (default=0.0).
        demand_placed (float): The placed portion of the demand (default=0.0).
        demand_unplaced (float): The unplaced portion of the demand (default=0.0).
        attrs (dict[str, Any]): A dictionary for any additional attributes (default={}).
    """

    source: str
    target: str
    priority: int = 0
    demand: float = 0.0
    demand_placed: float = 0.0
    demand_unplaced: float = 0.0
    attrs: Dict[str, Any] = field(default_factory=dict)
