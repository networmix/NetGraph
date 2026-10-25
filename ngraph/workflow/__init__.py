"""Typed workflow extension boundary; each built-in step loads on first use."""

from importlib import import_module
from typing import TYPE_CHECKING

from .base import BUILTIN_STEP_MODULES, WorkflowStep, register_workflow_step, step_name

if TYPE_CHECKING:
    from ngraph.analysis.preparation import StepNeeds

    from .build_graph import BuildGraph
    from .cost_power import CostPower
    from .max_flow_step import MaxFlow
    from .maximum_supported_demand_step import MaximumSupportedDemand
    from .network_stats import NetworkStats
    from .traffic_matrix_placement_step import TrafficMatrixPlacement
    from .tunnel_count_step import TunnelCountAnalysis


def __getattr__(name):
    if name == "StepNeeds":
        value = import_module("ngraph.analysis.preparation").StepNeeds
        globals()[name] = value
        return value
    module = BUILTIN_STEP_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


__all__ = [
    "WorkflowStep",
    "StepNeeds",
    "step_name",
    "register_workflow_step",
    "BuildGraph",
    "CostPower",
    "MaxFlow",
    "MaximumSupportedDemand",
    "NetworkStats",
    "TrafficMatrixPlacement",
    "TunnelCountAnalysis",
]
