"""Network model package.

Nodes, links, risk groups, and the scenario-level `Network`. Temporary
exclusions for analysis are handled via node_mask and edge_mask parameters in
Core algorithms, not by mutating this model.
"""

from ngraph.model.demand import TrafficDemand
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
    # Flow configuration
    "FlowPolicyPreset",
]
