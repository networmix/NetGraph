"""Traffic demand specification and matrix containers.

This package provides data structures for defining traffic demands
and organizing them into named traffic matrix sets.

Public API:
    TrafficDemand: Individual demand specification with source/sink selectors
    TrafficMatrixSet: Named collection of TrafficDemand lists
    build_traffic_matrix_set: Construct TrafficMatrixSet from parsed YAML
"""

from ngraph.model.demand.builder import build_traffic_matrix_set
from ngraph.model.demand.matrix import TrafficMatrixSet
from ngraph.model.demand.spec import TrafficDemand

__all__ = [
    "TrafficDemand",
    "TrafficMatrixSet",
    "build_traffic_matrix_set",
]
