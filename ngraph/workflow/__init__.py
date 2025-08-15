"""Workflow automation for NetGraph scenarios."""

from .base import WorkflowStep, register_workflow_step
from .build_graph import BuildGraph
from .cost_power import CostPower
from .max_flow_step import MaxFlow
from .maximum_supported_demand_step import MaximumSupportedDemand
from .network_stats import NetworkStats
from .traffic_matrix_placement_step import TrafficMatrixPlacement

__all__ = [
    "WorkflowStep",
    "register_workflow_step",
    "BuildGraph",
    "MaxFlow",
    "NetworkStats",
    "TrafficMatrixPlacement",
    "MaximumSupportedDemand",
    "CostPower",
]
