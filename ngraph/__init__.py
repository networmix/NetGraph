"""Named network models and exact-unit analyses on NetGraph-Core.

Every public name loads its module on first use, so a run imports only the
modules it needs.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from ngraph import logging as _logging  # noqa: F401  (attaches the NullHandler)

if TYPE_CHECKING:
    __version__: str
    from ngraph.analysis.capacity import CapacityQuery, capacity
    from ngraph.analysis.demands import resolve_demands
    from ngraph.analysis.failures import FailureRequest, Workers, failure_cases
    from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
    from ngraph.analysis.paths import PathQuery, paths
    from ngraph.analysis.placement import PlacementQuery, place
    from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
    from ngraph.analysis.topology import PreparedTopology
    from ngraph.analysis.units import UnitsSettings
    from ngraph.explorer import NetworkExplorer
    from ngraph.export import register_result_exporter, write_json
    from ngraph.model.components import Component, ComponentsLibrary
    from ngraph.model.demand import (
        ControllerGroup,
        DemandSet,
        DemandSpec,
        EdgeWeight,
        FlowPolicyPreset,
        ForwardingGroup,
        GroupChild,
        PhysicalAmount,
        PinnedRoutes,
        RouteSpec,
        RoutingDomain,
        SupportSpec,
        WCMPController,
        WeightSpec,
    )
    from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
    from ngraph.model.network import DirectedLink, Link, Network, Node
    from ngraph.model.risk import RiskGroup
    from ngraph.model.selectors import Condition, MatchSpec, Selector
    from ngraph.results import (
        AnalysisMetadata,
        AnalysisResult,
        BuildGraphResult,
        CapacityAnalysis,
        CapacityRow,
        CaseResult,
        CaseState,
        CostPowerResult,
        CostReport,
        CostUnavailableReason,
        DeliveredByPathCost,
        DiscardedShare,
        DomainResult,
        Endpoints,
        ExactAlpha,
        ExpansionAccounting,
        ExpansionLeaf,
        ExpansionParent,
        ExpansionSplit,
        ExportContext,
        FailureCase,
        FailurePattern,
        FailureSelection,
        FailureTrace,
        HardwareRow,
        InputConstraint,
        InputQuantization,
        JSONValue,
        MarginalCostBin,
        MarginalCurve,
        MSDAnalysis,
        MSDProbe,
        MSDProof,
        MSDStatus,
        MSDStopReason,
        NetworkStatsResult,
        OutputSelection,
        PathAnalysis,
        PathCostBin,
        PathRow,
        PlacementAnalysis,
        PlacementRow,
        PlacementTotals,
        PoolHead,
        PoolMetadata,
        PrecisionMiss,
        PreparationScope,
        RangeConstraint,
        RangeRefusal,
        ReportLocation,
        ResolvedDemand,
        ResolvedDemandSet,
        RunMetadata,
        RunResult,
        SamplingMetadata,
        SelfPair,
        SensitivityAnalysis,
        SplitConstraint,
        StepContext,
        StepOutput,
        StepQuestion,
        StepResult,
        SyntheticIngress,
        UnitConstraint,
        UnitsReport,
        UnverifiedConstraint,
        UpperCertificate,
    )
    from ngraph.scenario import PreparedScenario, Scenario, prepare, run
    from ngraph.workflow.base import WorkflowStep, register_workflow_step

_MODULES = {
    "ngraph.analysis.capacity": "CapacityQuery capacity",
    "ngraph.analysis.demands": "resolve_demands",
    "ngraph.analysis.failures": "FailureRequest Workers failure_cases",
    "ngraph.analysis.msd": "MSDQuery maximum_supported_demand",
    "ngraph.analysis.placement": "PlacementQuery place",
    "ngraph.analysis.topology": "PreparedTopology",
    "ngraph.analysis.units": "UnitsSettings",
    "ngraph.explorer": "NetworkExplorer",
    "ngraph.export": "register_result_exporter write_json",
    "ngraph.model.components": "Component ComponentsLibrary",
    "ngraph.model.demand": (
        "ControllerGroup DemandSet DemandSpec EdgeWeight FlowPolicyPreset "
        "ForwardingGroup GroupChild PhysicalAmount PinnedRoutes RouteSpec "
        "RoutingDomain SupportSpec WCMPController WeightSpec"
    ),
    "ngraph.model.failure": "FailureMode FailurePolicy FailureRule",
    "ngraph.model.network": "DirectedLink Link Network Node",
    "ngraph.model.risk": "RiskGroup",
    "ngraph.model.selectors": "Condition MatchSpec Selector",
    "ngraph.results": (
        "AnalysisMetadata AnalysisResult "
        "BuildGraphResult CapacityAnalysis "
        "CapacityRow CaseResult CaseState "
        "CostPowerResult CostReport CostUnavailableReason "
        "DeliveredByPathCost DiscardedShare "
        "DomainResult Endpoints ExactAlpha ExpansionAccounting "
        "ExpansionLeaf ExpansionParent ExpansionSplit ExportContext FailureCase "
        "FailurePattern FailureSelection FailureTrace "
        "HardwareRow InputConstraint InputQuantization JSONValue "
        "MarginalCostBin MarginalCurve MSDAnalysis MSDProbe MSDProof "
        "MSDStatus MSDStopReason "
        "NetworkStatsResult OutputSelection PathAnalysis "
        "PathCostBin PathRow PlacementAnalysis "
        "PlacementRow PlacementTotals PoolHead PoolMetadata PrecisionMiss "
        "PreparationScope RangeConstraint RangeRefusal ReportLocation "
        "ResolvedDemand ResolvedDemandSet RunMetadata RunResult "
        "SamplingMetadata SelfPair SensitivityAnalysis "
        "SplitConstraint StepContext StepOutput StepQuestion "
        "StepResult SyntheticIngress UnitConstraint UnitsReport "
        "UnverifiedConstraint UpperCertificate"
    ),
    "ngraph.scenario": "PreparedScenario Scenario prepare run",
    "ngraph.workflow.base": "WorkflowStep register_workflow_step",
    "ngraph.analysis.paths": "PathQuery paths",
    "ngraph.analysis.sensitivity": "SensitivityQuery edge_sensitivity",
}
_EXPORTS = {
    name: module for module, names in _MODULES.items() for name in names.split()
}


def __getattr__(name):
    if name == "__version__":
        from importlib.metadata import version

        value = version("ngraph")
    else:
        module = _EXPORTS.get(name)
        if module is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS) | {"__version__"})


__all__ = [
    "AnalysisMetadata",
    "AnalysisResult",
    "BuildGraphResult",
    "CapacityAnalysis",
    "CapacityQuery",
    "CapacityRow",
    "CaseResult",
    "CaseState",
    "Component",
    "ComponentsLibrary",
    "Condition",
    "ControllerGroup",
    "CostPowerResult",
    "CostReport",
    "CostUnavailableReason",
    "DeliveredByPathCost",
    "DemandSet",
    "DemandSpec",
    "DirectedLink",
    "DiscardedShare",
    "DomainResult",
    "EdgeWeight",
    "Endpoints",
    "ExactAlpha",
    "ExpansionAccounting",
    "ExpansionLeaf",
    "ExpansionParent",
    "ExpansionSplit",
    "ExportContext",
    "FailureCase",
    "FailureMode",
    "FailurePattern",
    "FailurePolicy",
    "FailureRequest",
    "FailureRule",
    "FailureSelection",
    "FailureTrace",
    "FlowPolicyPreset",
    "ForwardingGroup",
    "GroupChild",
    "HardwareRow",
    "InputConstraint",
    "InputQuantization",
    "JSONValue",
    "Link",
    "MSDAnalysis",
    "MSDProbe",
    "MSDProof",
    "MSDQuery",
    "MSDStatus",
    "MSDStopReason",
    "MarginalCostBin",
    "MarginalCurve",
    "MatchSpec",
    "Network",
    "NetworkExplorer",
    "NetworkStatsResult",
    "Node",
    "OutputSelection",
    "PathAnalysis",
    "PathCostBin",
    "PathQuery",
    "PathRow",
    "PhysicalAmount",
    "PinnedRoutes",
    "PlacementAnalysis",
    "PlacementQuery",
    "PlacementRow",
    "PlacementTotals",
    "PoolHead",
    "PoolMetadata",
    "PrecisionMiss",
    "PreparationScope",
    "PreparedScenario",
    "PreparedTopology",
    "RangeConstraint",
    "RangeRefusal",
    "ReportLocation",
    "ResolvedDemand",
    "ResolvedDemandSet",
    "RiskGroup",
    "RouteSpec",
    "RoutingDomain",
    "RunMetadata",
    "RunResult",
    "SamplingMetadata",
    "Scenario",
    "Selector",
    "SelfPair",
    "SensitivityAnalysis",
    "SensitivityQuery",
    "SplitConstraint",
    "StepContext",
    "StepOutput",
    "StepQuestion",
    "StepResult",
    "SupportSpec",
    "SyntheticIngress",
    "UnitConstraint",
    "UnitsReport",
    "UnitsSettings",
    "UnverifiedConstraint",
    "UpperCertificate",
    "WCMPController",
    "WeightSpec",
    "Workers",
    "WorkflowStep",
    "__version__",
    "capacity",
    "edge_sensitivity",
    "failure_cases",
    "maximum_supported_demand",
    "paths",
    "place",
    "prepare",
    "register_result_exporter",
    "register_workflow_step",
    "resolve_demands",
    "run",
    "write_json",
]
