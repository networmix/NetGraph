"""Traffic demand specification and set containers.

This package provides data structures for defining traffic demands
and organizing them into named demand sets.

Public API:
    TrafficDemand: Individual demand specification with source/target selectors
    DemandSet: Named collection of TrafficDemand lists
    build_demand_set: Construct DemandSet from parsed YAML
"""

from ngraph.model.demand.builder import build_demand_set
from ngraph.model.demand.matrix import DemandSet
from ngraph.model.demand.spec import TrafficDemand

__all__ = [
    "TrafficDemand",
    "DemandSet",
    "build_demand_set",
]
