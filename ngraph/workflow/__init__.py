"""Typed workflow extension boundary; each built-in step loads on first use."""

from importlib import import_module
from typing import TYPE_CHECKING

from .base import BUILTIN_STEP_MODULES, WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from .build_graph import BuildGraph
    from .cost_power import CostPower
    from .max_flow_step import MaxFlow
    from .maximum_supported_demand_step import MaximumSupportedDemand
    from .network_stats import NetworkStats
    from .traffic_matrix_placement_step import TrafficMatrixPlacement


def __getattr__(name):
    module = BUILTIN_STEP_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


__all__ = [
    "WorkflowStep",
    "register_workflow_step",
    "BuildGraph",
    "CostPower",
    "MaxFlow",
    "MaximumSupportedDemand",
    "NetworkStats",
    "TrafficMatrixPlacement",
]
