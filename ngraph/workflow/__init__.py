"""Workflow automation for NetGraph scenarios."""

from .base import WorkflowStep, register_workflow_step
from .build_graph import BuildGraph
from .capacity_envelope_analysis import CapacityEnvelopeAnalysis
from .cost_power_efficiency import CostPowerEfficiency
from .maximum_supported_demand import MaximumSupportedDemandAnalysis
from .network_stats import NetworkStats
from .traffic_matrix_placement_analysis import TrafficMatrixPlacementAnalysis

__all__ = [
    "WorkflowStep",
    "register_workflow_step",
    "BuildGraph",
    "CapacityEnvelopeAnalysis",
    "NetworkStats",
    "TrafficMatrixPlacementAnalysis",
    "MaximumSupportedDemandAnalysis",
    "CostPowerEfficiency",
]
