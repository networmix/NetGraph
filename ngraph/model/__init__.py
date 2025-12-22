"""Network model package.

This package defines the core network data model used across NetGraph, including
nodes, links, risk groups, and the scenario-level `Network`. Temporary exclusions
for analysis are handled via node_mask and edge_mask parameters in Core algorithms.
"""

from ngraph.model.demand import TrafficDemand, TrafficMatrixSet
from ngraph.model.flow import FlowPolicyPreset
from ngraph.model.network import Link, Network, Node, RiskGroup
from ngraph.model.path import Path

__all__ = [
    # Network topology
    "Network",
    "Node",
    "Link",
    "RiskGroup",
    "Path",
    # Traffic demands
    "TrafficDemand",
    "TrafficMatrixSet",
    # Flow configuration
    "FlowPolicyPreset",
]
