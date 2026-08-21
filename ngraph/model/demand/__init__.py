"""Traffic demand specification and set containers.

Defines individual demands and the named sets that group them for analysis.

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
