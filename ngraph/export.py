"""One exact-type result exporter registry and JSON output boundary.

A plain record is written as its declared class constants and fields, in
declaration order, by one walk over an explicit set of record types.
Native results, rows, failure cases, paths, sensitivity, the analysis
envelopes and the recorded questions have explicit encoders.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable, Mapping
from fractions import Fraction
from functools import cache
from operator import index as as_index
from types import MappingProxyType
from typing import IO, TYPE_CHECKING, Any, TypeVar, cast

import netgraph_core as ngc

from ngraph.analysis.demands import controlled, declared_split
from ngraph.analysis.metadata import run_metadata
from ngraph.model.demand import PinnedRoutes
from ngraph.model.network import DirectedLink
from ngraph.results import (
    AnalysisMetadata,
    AnalysisResult,
    BuildGraphResult,
    CapacityAnalysis,
    CapacityRow,
    CostPowerResult,
    DeadCap,
    DeliveredByPathCost,
    DiscardedShare,
    Endpoints,
    ExactAlpha,
    ExpansionAccounting,
    ExportContext,
    FailurePattern,
    FailureSelection,
    FailureTrace,
    ForwardingFailure,
    HardwareRow,
    InputConstraint,
    InputQuantization,
    MarginalCostBin,
    MarginalCurve,
    MemberWeight,
    MSDAnalysis,
    MSDProbe,
    NetworkStatsResult,
    OutputSelection,
    PathAnalysis,
    PathCostBin,
    PlacementAnalysis,
    PlacementRow,
    PlacementTotals,
    PoolHead,
    PoolMetadata,
    PrecisionMiss,
    PreparationScope,
    ProgrammedRouter,
    RangeConstraint,
    RangeRefusal,
    ReportLocation,
    RunMetadata,
    RunResult,
    SamplingMetadata,
    SelfPair,
    SensitivityAnalysis,
    SourceWeight,
    SplitConstraint,
    SyntheticIngress,
    TableReport,
    UnitsReport,
    UnverifiedConstraint,
    UpperCertificate,
    WeightApproximation,
    exact_alpha,
)
from ngraph.utils.values import (
    JSONValue,
    _FrozenDict,
    _FrozenList,
    frozen_json,
    json_copy,
)

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario

ExportT = TypeVar("ExportT")
_EXPORTERS: dict[type, Callable[[object, ExportContext], JSONValue]] = {}
_BUILTIN_TYPES: set[type] = set()

# Records whose JSON is exactly their declared constants and fields.
_PLAIN = frozenset(
    (
        AnalysisMetadata,
        BuildGraphResult,
        DeliveredByPathCost,
        DirectedLink,
        DeadCap,
        DiscardedShare,
        Endpoints,
        ExactAlpha,
        ExpansionAccounting,
        FailurePattern,
        FailureSelection,
        FailureTrace,
        ForwardingFailure,
        HardwareRow,
        InputConstraint,
        InputQuantization,
        MarginalCostBin,
        MarginalCurve,
        MemberWeight,
        MSDProbe,
        NetworkStatsResult,
        OutputSelection,
        PathCostBin,
        PlacementTotals,
        PoolHead,
        PoolMetadata,
        PrecisionMiss,
        PreparationScope,
        ProgrammedRouter,
        RangeConstraint,
        RangeRefusal,
        ReportLocation,
        RunMetadata,
        SamplingMetadata,
        SelfPair,
        SourceWeight,
        SplitConstraint,
        SyntheticIngress,
        TableReport,
        UnitsReport,
        UnverifiedConstraint,
        UpperCertificate,
        WeightApproximation,
    )
)


@cache
def layout(kind: type) -> tuple[str, ...]:
    """A plain record's JSON keys: its class constants and fields, as declared."""
    return tuple(vars(kind)["__annotations__"])


def _output_options(value: ngc.OutputOptions) -> dict[str, JSONValue]:
    return {
        "edge_flows": value.edge_flows,
        "residual": value.residual,
        "edge_reservations": value.edge_reservations,
        "saturated_boundary_edges": value.saturated_boundary_edges,
        "min_cut": value.min_cut,
    }


def project(value: object) -> JSONValue:
    """Write a plain record, its exact field values and finite JSON data."""
    kind = type(value)
    if value is None or kind in (bool, int, float, str):
        return cast(JSONValue, value)
    if kind is Fraction:
        fraction = cast(Fraction, value)
        return {"numerator": fraction.numerator, "denominator": fraction.denominator}
    if kind in (tuple, list, _FrozenList):
        return [project(item) for item in cast(tuple, value)]
    if kind in _PLAIN:
        return {name: project(getattr(value, name)) for name in layout(kind)}
    if kind in (dict, _FrozenDict, MappingProxyType):
        return json_copy(value)
    if kind is ngc.OutputOptions:
        return _output_options(cast(ngc.OutputOptions, value))
    raise TypeError(f"export: no encoder for {kind.__name__}")


def register_result_exporter(
    result_type: type[ExportT], encoder: Callable[[ExportT, ExportContext], JSONValue]
) -> None:
    """Register one explicit encoder for exactly this result type."""
    if not isinstance(result_type, type) or not callable(encoder):
        raise TypeError("result exporter: expected a type and callable encoder")
    if result_type in _EXPORTERS:
        raise ValueError(
            f"result exporter already registered for {result_type.__name__}"
        )

    def custom(value: object, context: ExportContext) -> JSONValue:
        projected = encoder(cast(ExportT, value), context)
        try:
            return json_copy(
                projected, f"exporter {result_type.__name__}", strict_objects=True
            )
        except ValueError as exc:
            raise TypeError(str(exc)) from exc

    _EXPORTERS[result_type] = custom


def owned_step_result(value: object) -> object:
    """Publish a step result without running its encoder.

    NetGraph's records are immutable and finite JSON is frozen. A registered
    result type is published as it is, with any native values it holds; its
    own type decides whether a later step can change it.
    """
    if type(value) in _BUILTIN_TYPES or type(value) in _EXPORTERS:
        return value
    try:
        return frozen_json(value, "step result", strict_objects=True)
    except ValueError as exc:
        raise TypeError(f"unregistered result type {type(value).__name__}") from exc


def _export_registered(value: object, context: ExportContext) -> JSONValue:
    encoder = _EXPORTERS.get(type(value))
    if encoder is not None:
        return encoder(value, context)
    try:
        return json_copy(value, "step result", strict_objects=True)
    except ValueError as exc:
        raise TypeError(f"unregistered result type {type(value).__name__}") from exc


def _cost_power(value, context):
    return {
        "kind": value.kind,
        "include_disabled": value.include_disabled,
        "aggregation_level": value.aggregation_level,
        "levels": [
            {"level": level, "rows": project(rows)}
            for level, rows in value.levels.items()
        ],
    }


def _plain(value, context):
    return project(value)


_EXPORTERS.update(
    {
        BuildGraphResult: _plain,
        NetworkStatsResult: _plain,
        CostPowerResult: _cost_power,
    }
)
_BUILTIN_TYPES.update(_EXPORTERS)


# Recorded questions: each analysis's own query, a built-in domain step, or
# a custom step's JSON parameters.


def _edge(value):
    if type(value) in (DirectedLink, SyntheticIngress):
        return project(value)
    raise TypeError(f"unsupported edge reference {type(value).__name__}")


def _selector(value):
    match = value.match
    return {
        "path": value.path,
        "group_by": value.group_by,
        "match": None
        if match is None
        else {
            "logic": match.logic,
            "conditions": [
                {"attr": condition.attr, "op": condition.op, "value": condition.value}
                for condition in match.conditions
            ],
        },
        "active_only": value.active_only,
    }


def _ceiling(value):
    if value is None:
        return None
    if isinstance(value, ngc.AbsoluteCost):
        return {"kind": "absolute", "absolute": value.cost, "stretch": None}
    return {"kind": "stretch", "absolute": None, "stretch": project(value.factor)}


def _edge_weights(topology, vector) -> JSONValue:
    return [
        {"edge": _edge(ref), "value": int(value)}
        for ref, value in zip(topology.edge_refs, vector, strict=True)
    ]


def _model(prepared: PreparedScenario, config, declaration=None):
    """The effective native model, with inapplicable fields explicitly null."""
    topology = prepared.topology
    if config is None:
        if not isinstance(declaration, PinnedRoutes):
            raise TypeError(
                "model export requires a native config or named pinned declaration"
            )
        admission = declaration.admission
    else:
        admission = config.admission
    model = config.routing if config is not None else None
    data: dict[str, JSONValue] = dict.fromkeys(
        (
            "routing",
            "admission",
            "allocation",
            "source_allocation",
            "weight_basis",
            "edge_weights",
            "tie_break",
            "multipath",
            "parallel_edges",
            "tunnel_count",
            "prefer_headroom",
            "cost_ceiling",
            "min_unreserved_bandwidth_units",
            "route_names",
            "controller",
        )
    )
    data.update(supplied_support=False, supplied_program=False)
    data["admission"] = "lossless" if admission == ngc.Admission.LOSSLESS else "lossy"
    controller = prepared.scenario.wcmp_controller
    if controlled(controller, declaration):
        # The controller's weights live in the analysis's controller key.
        assert controller is not None
        data.update(
            routing="shortest_paths",
            allocation="weighted",
            source_allocation="equal",
            controller=controller.scope,
        )
        return data
    allocation, basis = declared_split(prepared._named, config, declaration)
    if allocation is not None:
        data["allocation"] = allocation.name.lower()
    if basis is not None:
        data["weight_basis"] = basis.name.lower()
    if isinstance(model, ngc.ShortestPaths):
        data["routing"] = "shortest_paths"
        source = model.source_allocation or (
            ngc.SourceAllocation.OPTIMIZED
            if model.allocation == ngc.RouteAllocation.OPTIMIZED
            else ngc.SourceAllocation.EQUAL
        )
        data["source_allocation"] = source.name.lower()
        if model.edge_weights is not None:
            data["edge_weights"] = _edge_weights(topology, model.edge_weights)
        data["tie_break"] = model.tie_break.name.lower()
        data["multipath"] = model.multipath
        data["parallel_edges"] = model.parallel_edges
    elif isinstance(model, ngc.DistributedTE):
        data["routing"] = "distributed_te"
        count = model.tunnel_count
        data["tunnel_count"] = {"per_head": count.per_head, "up_to": count.up_to}
        data["cost_ceiling"] = _ceiling(model.cost_ceiling)
        data["min_unreserved_bandwidth_units"] = model.min_unreserved_bandwidth
        data["tie_break"] = model.tie_break.name.lower()
        data["parallel_edges"] = model.parallel_edges
    elif isinstance(model, ngc.CentralizedTE):
        data["routing"] = "centralized_te"
        data["source_allocation"] = model.source_allocation.name.lower()
        count = model.tunnel_count
        if count is not None:
            data["tunnel_count"] = {"per_head": count.per_head, "up_to": count.up_to}
        data["prefer_headroom"] = model.prefer_headroom
        data["supplied_support"] = model.support is not None
    elif isinstance(model, ngc.Pinned) or isinstance(declaration, PinnedRoutes):
        data["routing"] = "pinned"
        if not isinstance(declaration, PinnedRoutes):
            data["supplied_program"] = True
        else:
            data["route_names"] = list(declaration.routes)
            if declaration.edge_weights is not None:
                data["edge_weights"] = _edge_weights(
                    topology, prepared._named.vector(declaration.edge_weights)
                )
    else:
        raise TypeError("model export: unknown native routing model")
    return data


def _failures(value):
    if value is None:
        return None
    policy = value.policy
    inline = None
    if policy is not None and value.policy_name is None:
        inline = {
            "attrs": dict(policy.attrs),
            "expand_groups": policy.expand_groups,
            "seed": policy.seed,
            "modes": [
                {
                    "weight": mode.weight,
                    "attrs": dict(mode.attrs),
                    "rules": [
                        {
                            "scope": rule.scope,
                            "mode": rule.mode,
                            "match": {
                                "logic": rule.logic,
                                "conditions": [
                                    {
                                        "attr": condition.attr,
                                        "op": condition.op,
                                        "value": condition.value,
                                    }
                                    for condition in rule.conditions
                                ],
                            },
                            "probability": rule.probability,
                            "count": rule.count,
                            "weight_by": rule.weight_by,
                            "path": rule.path,
                        }
                        for rule in mode.rules
                    ],
                }
                for mode in policy.modes
            ],
        }
    return {
        "policy_name": value.policy_name,
        "inline_policy": inline,
        "iterations": value.iterations,
        "seed": value.seed,
        "failure_trace": value.failure_trace,
    }


def _demands(value, prepared):
    return [
        {
            "source": _selector(parent.source),
            "target": _selector(parent.target),
            "priority": parent.priority,
            "id": parent.base_id,
            "model": _model(prepared, parent.config, parent.policy),
            "physical_volume": parent.physical_volume,
            "mode": parent.mode,
            "group_mode": parent.group_mode,
        }
        for parent in value.expansion_template
    ]


def _excluded(topology, mask):
    nodes, edges = mask.node_allowed(), mask.edge_allowed()
    return (
        [name for i, name in enumerate(topology.node_names) if not nodes[i]],
        [_edge(ref) for i, ref in enumerate(topology.edge_refs) if not edges[i]],
    )


def _mask(topology, eligibility):
    if eligibility is None:
        return topology.disabled
    return ngc.Eligibility.intersect(topology.disabled, eligibility)


def _capacity_query(value, prepared):
    return {
        "kind": "capacity",
        "source": _selector(value.source),
        "target": _selector(value.target),
        "mode": value.mode,
        "model": _model(prepared, value.config, value.declaration),
        "offer": value.offer,
        "design_demand": value.design_demand,
        "failures": _failures(value.failures),
    }


def _placement_query(value, prepared):
    return {
        "kind": "placement",
        "demand_set": value.demands.name,
        "demands": _demands(value.demands, prepared),
        "alpha": project(exact_alpha(value.alpha)),
        "alpha_source": {
            "kind": "query" if value.alpha_from_step is None else "msd_step",
            "step": value.alpha_from_step,
        },
        "failures": _failures(value.failures),
        "states": list(value.states),
        "interaction": value.interaction,
    }


def _sensitivity_query(value, prepared):
    topology = prepared.topology
    nodes, edges = _excluded(topology, _mask(topology, value.eligibility))
    return {
        "kind": "sensitivity",
        "source": _selector(value.source),
        "target": _selector(value.target),
        "model": _model(prepared, value.config),
        "offer": value.offer,
        "design_demand": value.design_demand,
        "excluded_nodes": nodes,
        "excluded_edges": edges,
    }


def _path_query(value, prepared):
    topology = prepared.topology
    native = value.options
    spf = isinstance(native, ngc.SpfOptions)
    nodes, edges = _excluded(topology, _mask(topology, native.eligibility))
    residual = native.residual
    return {
        "kind": "paths",
        "source": _selector(value.source),
        "target": _selector(value.target),
        "mode": value.mode,
        "algorithm": "spf" if spf else "ksp",
        "costs_only": value.costs_only,
        "max_paths": value.max_paths,
        "split_parallel_edges": bool(value.split_parallel_edges) if spf else None,
        "k": None if spf else as_index(native.k),
        "cost_ceiling": None if spf else _ceiling(native.cost_ceiling),
        "tie_break": native.tie_break.name.lower(),
        "multipath": native.multipath if spf else None,
        "parallel_edges": native.parallel_edges,
        "excluded_nodes": nodes,
        "excluded_edges": edges,
        "residual_units": None
        if residual is None
        else [as_index(units) for units in residual],
        "min_residual": as_index(native.min_residual) if spf else None,
    }


def _msd_query(value, prepared):
    return {
        "kind": "msd",
        "demand_set": value.demands.name,
        "demands": _demands(value.demands, prepared),
        "alpha_start": value.alpha_start,
        "growth_factor": value.growth_factor,
        "alpha_min": value.alpha_min,
        "alpha_max": value.alpha_max,
        "alpha_tolerance": value.alpha_tolerance,
        "max_bracket_iters": value.max_bracket_iters,
        "max_bisect_iters": value.max_bisect_iters,
        "export_probe_rows": value.export_probe_rows,
    }


# Each analysis query, named by module and class so that checking a question
# imports no analysis module the run did not load.
_QUERIES = {
    ("ngraph.analysis.capacity", "CapacityQuery"): _capacity_query,
    ("ngraph.analysis.placement", "PlacementQuery"): _placement_query,
    ("ngraph.analysis.sensitivity", "SensitivityQuery"): _sensitivity_query,
    ("ngraph.analysis.paths", "PathQuery"): _path_query,
    ("ngraph.analysis.msd", "MSDQuery"): _msd_query,
}


def _query_encoder(value):
    kind = type(value)
    encoder = _QUERIES.get((kind.__module__, kind.__qualname__))
    module = sys.modules.get(kind.__module__)
    if encoder is not None and getattr(module, kind.__qualname__, None) is kind:
        return encoder
    return None


def _domain_step(value: object) -> bool:
    # A built-in domain step declares its question kind on its own class.
    return dataclasses.is_dataclass(value) and "question_kind" in vars(type(value))


def is_question(value: object) -> bool:
    """Whether a step may record this value as its question."""
    return (
        _query_encoder(value) is not None
        or _domain_step(value)
        or isinstance(value, Mapping)
    )


def question(value, prepared: PreparedScenario):
    """Write a recorded question."""
    encoder = _query_encoder(value)
    if encoder is not None:
        return encoder(value, prepared)
    if _domain_step(value):
        # Its parameters are the fields its own class declares.
        own = type(value).__annotations__
        return {
            "kind": vars(type(value))["question_kind"],
            "parameters": {
                field.name: project(getattr(value, field.name))
                for field in dataclasses.fields(cast(Any, value))
                if field.name in own
            },
        }
    if isinstance(value, Mapping):
        return {"kind": "custom", "parameters": dict(value)}
    raise TypeError(f"unsupported step question {type(value).__name__}")


def _run(value, context):
    return {
        "metadata": project(value.metadata),
        "units_report": project(value.units_report),
        "steps": [
            {
                "name": step.name,
                "step_type": step.step_type,
                "execution_order": step.execution_order,
                "scenario_seed": step.scenario_seed,
                "step_seed": step.step_seed,
                "seed_source": step.seed_source,
                "question": question(step.question, context.prepared),
                "result": _export_registered(step.result, context),
            }
            for step in value.steps
        ],
    }


def _encode_json(result: RunResult | AnalysisResult) -> str:
    """Project and encode once, before any destination is written."""
    if type(result) is not RunResult and type(result) not in _ANALYSIS_TYPES:
        raise TypeError(f"unsupported export root {type(result).__name__}")
    context = ExportContext(result.prepared, result.units_report)
    projected = _export_registered(result, context)
    assert isinstance(projected, dict)
    if not isinstance(result, RunResult):
        projected["query"] = question(result.query, result.prepared)
        projected = {
            "metadata": project(run_metadata()),
            "analysis": projected,
            "units_report": project(result.units_report),
        }
    return json.dumps(
        projected, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def write_json(result: RunResult | AnalysisResult, file: IO[str]) -> None:
    """Project once and encode before writing, so encoder errors write nothing."""
    file.write(_encode_json(result))
    file.write("\n")


_EXPORTERS[RunResult] = _run
_BUILTIN_TYPES.add(RunResult)


def _source(topology, node, pool):
    if 0 <= node < len(topology.node_names):
        return topology.node_names[node]
    if pool is not None and topology.pool_heads[pool.head.pool_id] == node:
        return project(pool.head)
    raise ValueError(f"result source {node}: no physical or pool identity")


def _amounts(topology, values):
    physical, synthetic = [], []
    for edge, units in values:
        ref = topology.edge_refs[edge]
        row = {"edge": _edge(ref), "units": int(units)}
        (physical if type(ref) is DirectedLink else synthetic).append(row)
    return physical, synthetic


def _edge_ids(topology, values):
    if values is None:
        return None, None
    physical, synthetic = [], []
    for edge in values:
        ref = topology.edge_refs[edge]
        (physical if type(ref) is DirectedLink else synthetic).append(_edge(ref))
    return physical, synthetic


def _tunnel_plan(value, topology, pool):
    if value is None:
        return None
    design = value.design_demand
    by_head = value.design_by_head
    live = value.heads_with_capacity
    fractional = value.max_fractional_bandwidth_per_tunnel
    unlimited = isinstance(design, float) and design == float("inf")
    return {
        "tunnels_per_head": value.tunnels_per_head,
        "design_kind": "unlimited" if unlimited else "finite",
        "design_demand_units": None if unlimited else design,
        "design_by_head": [
            {"head": _source(topology, head, pool), "units": units}
            for head, units in by_head
        ],
        "total_reserved_bandwidth_units": value.total_reserved_bandwidth,
        "heads_with_capacity": None
        if live is None
        else [_source(topology, head, pool) for head in live],
        "insufficient_resolution": value.insufficient_resolution,
        "max_fractional_bandwidth_per_tunnel": None
        if fractional is None
        else project(fractional),
        "max_bandwidth_per_tunnel_units": value.max_bandwidth_per_tunnel,
        "planned_bandwidth_per_tunnel_units": value.planned_bandwidth_per_tunnel,
        "total_planned_bandwidth_units": value.total_planned_bandwidth,
        "total_tunnel_cost": value.total_tunnel_cost,
        "headroom_penalty": value.headroom_penalty,
        "max_lossless_offer_units": value.max_lossless_offer,
    }


def _native(value, topology, outputs, pool=None):
    requested = value.requested
    unlimited = isinstance(requested, float) and requested == float("inf")
    edge_drops = value.edge_drops
    data = {
        "request_kind": "unlimited" if unlimited else "finite",
        "requested_units": None if unlimited else requested,
        "offered_units": value.offered,
        "delivered_units": value.delivered,
        "unadmitted_units": value.unadmitted,
        "source_drop_units": value.source_drops,
        "edge_drop_units": sum(units for _, units in edge_drops),
        "termination": value.termination.name.lower(),
        "total_cost": value.total_cost,
    }
    synthetic: dict[str, object] = {}
    if outputs.details:
        undelivered = value.call_undelivered
        call_drops = value.call_edge_drops
        sources = value.by_source
        tunnels = value.by_tunnel
        plan = value.plan
        call_physical, call_synthetic = _amounts(topology, call_drops)
        physical_drops, synthetic_drops = _amounts(topology, edge_drops)
        data.update(
            {
                "call_delivered_units": value.call_delivered,
                "call_undelivered_units": None
                if isinstance(undelivered, float) and undelivered == float("inf")
                else undelivered,
                "delivery_delta_units": value.delivery_delta,
                "call_edge_drops": call_physical,
                "call_source_drop_units": value.call_source_drops,
                "admitted_units": value.admitted,
                "edge_drops": physical_drops,
                "by_source": [
                    {
                        "source": _source(topology, row.source, pool),
                        "offered_units": row.offered,
                        "admitted_units": row.admitted,
                        "delivered_units": row.delivered,
                        "source_drop_units": row.source_drops,
                        "total_edge_drop_units": row.total_edge_drops,
                    }
                    for row in sources
                ],
                "by_tunnel": [
                    {
                        "entry_id": row.entry_id,
                        "head": _source(topology, row.head, pool),
                        "status": row.status.name.lower(),
                        "assigned_units": row.assigned,
                        "delivered_units": row.delivered,
                        "total_edge_drop_units": row.total_edge_drops,
                    }
                    for row in tunnels
                ],
                "plan": _tunnel_plan(plan, topology, pool),
            }
        )
        synthetic.update(call_edge_drops=call_synthetic, edge_drops=synthetic_drops)
    native = outputs.native
    selected = False
    for name, enabled in (
        ("edge_flows", native.edge_flows),
        ("residual", native.residual),
        ("edge_reservations", native.edge_reservations),
    ):
        if enabled:
            selected = True
            array = getattr(value, name)
            if array is None:
                data[name] = None
            else:
                data[name], synthetic[name] = _amounts(topology, enumerate(array))
    for name, enabled in (
        ("saturated_boundary_edges", native.saturated_boundary_edges),
        ("min_cut", native.min_cut),
    ):
        if enabled:
            selected = True
            ids = getattr(value, name)
            data[name], synthetic[name] = _edge_ids(topology, ids)
    if pool is not None and (selected or any(synthetic.values())):
        data["synthetic_ingress"] = synthetic
    return data


def _row(value, topology, outputs):
    if type(value) is SelfPair:
        return project(value)
    if type(value) not in (PlacementRow, CapacityRow):
        raise TypeError(f"unsupported flow row {type(value).__name__}")
    data = {
        "kind": "placement" if type(value) is PlacementRow else "capacity",
        "id": value.id,
        "endpoints": project(value.endpoints),
        "pool": project(value.pool),
        "result": _native(value.result, topology, outputs, value.pool),
    }
    if type(value) is PlacementRow:
        data.update(
            base_id=value.base_id,
            reference_request_units=value.reference_request_units,
            reference_shortfall_units=value.reference_request_units
            - value.result.delivered,
        )
    if value.cost_distribution is not None:
        data["cost_distribution"] = project(value.cost_distribution)
    if value.unavailable_outputs:
        data["unavailable_outputs"] = dict(value.unavailable_outputs)
    return data


def _failure_case(value):
    data = {
        "id": value.id,
        "kind": value.kind,
        "pattern": project(value.pattern),
        "occurrences": value.occurrences,
    }
    if value.trace is not None:
        data["trace"] = project(value.trace)
    return data


def _state(value, topology, outputs):
    data = {
        "rows": [_row(row, topology, outputs) for row in value.rows],
        "totals": project(value.totals),
    }
    if value.failure is not None:
        data["failure"] = project(value.failure)
    if value.dead_caps is not None:
        data["dead_caps"] = project(value.dead_caps)
    return data


def _cases(values, topology, outputs):
    return [
        {
            "case": _failure_case(value.case),
            "states": {
                name: _state(state, topology, outputs)
                for name, state in value.states.items()
            },
        }
        for value in values
    ]


def _capacity(value, context):
    return {
        "kind": value.kind,
        "metadata": project(value.metadata),
        "outputs": project(value.outputs),
        "question": value.question,
        "offer_source": value.offer_source,
        "cases": _cases(value.cases, context.topology, value.outputs),
    }


def _placement(value, context):
    return {
        "kind": value.kind,
        "metadata": project(value.metadata),
        "outputs": project(value.outputs),
        "alpha": project(value.alpha),
        "accounting": project(value.accounting),
        "cases": _cases(value.cases, context.topology, value.outputs),
        **_controller(value.query.demands),
    }


def _controller(demands):
    """The controller's tables of a programmed demand set; nothing for another set."""
    if demands.controller is None:
        return {}
    return {"controller": project(demands.controller)}


def _sensitivity(value, context):
    entries = value.result.entries
    baseline = value.result.baseline
    return {
        "kind": value.kind,
        "metadata": project(value.metadata),
        "outputs": project(value.outputs),
        "endpoints": project(value.endpoints),
        "question": value.question,
        "offer_source": value.offer_source,
        "baseline": _native(baseline, context.topology, value.outputs),
        "entries": [
            {
                "edge": _edge(context.topology.edge_refs[row.edge]),
                "delivery_reduction_units": row.delivery_reduction,
            }
            for row in entries
            if row.delivery_reduction != 0
        ],
    }


def _named_path(path, topology):
    if path.graph_uid() != topology.graph.uid():
        raise ValueError("path export: path belongs to another graph")
    hops = path.hops()
    return {
        "source": topology.node_names[path.source()],
        "destination": topology.node_names[path.destination()],
        "cost": path.cost(),
        "hops": [[_edge(topology.edge_refs[edge]) for edge in hop] for hop in hops],
    }


def _paths(value, context):
    rows = []
    for row in value.rows:
        data = {
            "id": row.id,
            "endpoints": project(row.endpoints),
            "kind": row.kind,
            "cost": row.cost,
        }
        if row.paths is not None:
            data["paths"] = [_named_path(path, context.topology) for path in row.paths]
        rows.append(data)
    return {
        "kind": value.kind,
        "metadata": project(value.metadata),
        "algorithm": value.algorithm,
        "mode": value.mode,
        "costs_only": value.costs_only,
        "rows": rows,
    }


def _msd(value, context):
    outputs = value.outputs
    data = {
        "kind": value.kind,
        "metadata": project(value.metadata),
        "outputs": project(value.outputs),
        "alpha_feasible": project(value.alpha_feasible),
        "best_probe_index": value.best_probe_index,
        "monotone_proven": value.monotone_proven,
        "proof": value.proof,
        "upper_certificate": project(value.upper_certificate),
        "search_status": value.search_status,
        "stop_reason": value.stop_reason,
        "history": project(value.history),
        "best_rows": None
        if value.best_rows is None
        else [_row(row, context.topology, outputs) for row in value.best_rows],
        "best_accounting": project(value.best_accounting),
        **_controller(value.query.demands),
    }
    if value.probe_rows is not None:
        data["probe_rows"] = [
            {
                "index": index,
                "rows": [_row(row, context.topology, outputs) for row in rows],
            }
            for index, rows in sorted(value.probe_rows.items())
        ]
    return data


_ANALYSIS_TYPES = (
    CapacityAnalysis,
    PlacementAnalysis,
    SensitivityAnalysis,
    PathAnalysis,
    MSDAnalysis,
)
_EXPORTERS.update(
    {
        CapacityAnalysis: _capacity,
        PlacementAnalysis: _placement,
        SensitivityAnalysis: _sensitivity,
        PathAnalysis: _paths,
        MSDAnalysis: _msd,
    }
)
_BUILTIN_TYPES.update(_ANALYSIS_TYPES)
