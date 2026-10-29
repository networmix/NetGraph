"""Typed API client covering compact and requested native result projection."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from io import StringIO
from typing import Literal

import netgraph_core as ngc

from ngraph import (
    BuildGraphResult,
    CapacityAnalysis,
    CapacityQuery,
    CapacityRow,
    CaseResult,
    CaseState,
    ControllerGroup,
    CostPowerResult,
    CostReport,
    DeliveredByPathCost,
    DemandSet,
    DemandSpec,
    DirectedLink,
    DomainResult,
    EdgeWeight,
    ExportContext,
    FailureCase,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    FlowPolicyPreset,
    ForwardingGroup,
    GroupChild,
    InputConstraint,
    JSONValue,
    MarginalCurve,
    MSDAnalysis,
    MSDProof,
    MSDQuery,
    MSDStatus,
    MSDStopReason,
    NetworkStatsResult,
    OutputSelection,
    PathAnalysis,
    PathQuery,
    PinnedRoutes,
    PlacementAnalysis,
    PlacementQuery,
    PlacementRow,
    RangeConstraint,
    ResolvedDemandSet,
    RouteSpec,
    RoutingDomain,
    RunResult,
    Scenario,
    Selector,
    SelfPair,
    SensitivityAnalysis,
    SensitivityQuery,
    SplitCountConstraint,
    StepContext,
    StepOutput,
    SupportSpec,
    TunnelCountAnalysis,
    TunnelCountQuery,
    UnitsReport,
    UnitsSettings,
    WCMPController,
    WeightSpec,
    WorkflowStep,
    capacity,
    edge_sensitivity,
    failure_cases,
    maximum_supported_demand,
    paths,
    place,
    prepare,
    register_result_exporter,
    register_workflow_step,
    resolve_demands,
    run,
    tunnel_counts,
    write_json,
)
from ngraph.model.components import ComponentsLibrary
from ngraph.model.network import Link, Network, Node
from ngraph.results import DeadCap, ForwardingFailure, PoolMetadata
from ngraph.workflow import TunnelCountAnalysis as TunnelCountStep


def minimal(network: Network, workflow: Sequence[WorkflowStep]) -> RunResult:
    return run(prepare(Scenario(network=network, workflow=workflow)))


def populated(
    network: Network,
    workflow: Sequence[WorkflowStep],
    demand_sets: Mapping[str, DemandSet],
    failure_policies: Mapping[str, FailurePolicy],
    components_library: ComponentsLibrary,
    routes: Mapping[str, RouteSpec],
    supports: Mapping[str, SupportSpec],
    weights: Mapping[str, WeightSpec],
    forwarding_groups: Mapping[str, ForwardingGroup],
    routing: RoutingDomain | None = None,
    wcmp_controller: WCMPController | None = None,
) -> RunResult:
    return run(
        prepare(
            Scenario(
                network,
                workflow,
                demand_sets=demand_sets,
                failure_policies=failure_policies,
                components_library=components_library,
                seed=42,
                units=UnitsSettings(),
                routes=routes,
                supports=supports,
                weights=weights,
                forwarding_groups=forwarding_groups,
                routing=routing,
                wcmp_controller=wcmp_controller,
            ),
            demand_sets=tuple(demand_sets),
        )
    )


def populated_example() -> list[tuple[str, float]]:
    """``populated`` with every constructor field given: each step's baseline delivery
    in physical units (the automatic resolution chooses q)."""
    from ngraph.model.components import Component
    from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement

    network = Network()
    for name in ("S", "X1", "X2", "T"):
        network.add_node(Node(name))
    for target in ("X1", "X2"):
        network.add_link(Link("S", target, capacity=10, cost=1))
        network.add_link(Link(target, "T", capacity=10, cost=1))
    via_x2 = (DirectedLink("S|X2|0", "forward"), DirectedLink("X2|T|0", "forward"))
    tree = ForwardingGroup(
        "S",
        (
            ControllerGroup((GroupChild(edge=DirectedLink("S|X1|0", "forward")),)),
            ControllerGroup(
                (GroupChild(edge=DirectedLink("S|X2|0", "forward")),), share="1/2"
            ),
        ),
    )
    controlled = DemandSpec(
        Selector("^S$"),
        Selector("^T$"),
        9,
        policy=FlowPolicyPreset.SHORTEST_PATHS_WCMP,
        id="dc",
    )
    pinned = DemandSpec(
        Selector("^S$"),
        Selector("^T$"),
        2,
        policy=PinnedRoutes(("via_x1", "via_x2")),
        id="lsp",
    )
    result = populated(
        network,
        (
            TrafficMatrixPlacement(
                name="controlled",
                demand_set="wcmp",
                failure_policy="any_link",
                iterations=4,
                workers=1,
            ),
            TrafficMatrixPlacement(name="pinned", demand_set="lsp", workers=1),
        ),
        {
            "wcmp": DemandSet("wcmp", (controlled,)),
            "lsp": DemandSet("lsp", (pinned,)),
        },
        {
            "any_link": FailurePolicy(
                modes=[FailureMode(1, [FailureRule("link", mode="choice", count=1)])]
            )
        },
        ComponentsLibrary(components={"chassis": Component("chassis", capex=1)}),
        {
            "via_x1": RouteSpec("S", nodes=("S", "X1", "T")),
            "via_x2": RouteSpec("S", support="x2"),
        },
        {"x2": SupportSpec(via_x2)},
        {"unit": WeightSpec(tuple(EdgeWeight(edge, 1) for edge in via_x2))},
        {"ingress": tree},
        RoutingDomain(Selector("^X[12]$"), Selector("^(S|T)$")),
        WCMPController("group"),
    )
    delivered: list[tuple[str, float]] = []
    for step in result.steps:
        analysis = step.result
        assert isinstance(analysis, PlacementAnalysis)
        totals = analysis.cases[0].states["converged"].totals
        assert totals is not None
        delivered.append((step.name, totals.delivered_units * result.topology.q))
    return delivered


def read_units(report: UnitsReport) -> float:
    q: float = report.q
    exponent: int = report.exponent
    target: bool = report.target_met
    precision: float = report.precision
    assert q == 2.0**exponent and precision > 0
    assert isinstance(target, bool)
    sets: tuple[str, ...] = report.scope.library_demand_sets
    for name in sets:
        assert isinstance(name, str)
    achieved: Fraction | None = report.achieved_precision
    assert achieved is None or achieved >= 0
    input_bound: InputConstraint | None = report.input_bound
    split_bound: SplitCountConstraint | None = report.split_bound
    range_limit: RangeConstraint | None = report.range_limit
    if input_bound is not None:
        label: str = input_bound.label
        bound: Fraction = input_bound.q_upper_bound
        assert label and bound > 0
    if split_bound is not None:
        count: Fraction = split_bound.count
        group: str | None = split_bound.group
        assert count > 0 and (group is None or isinstance(group, str))
        assert split_bound.nodes >= 0 and split_bound.directed_links >= 0
        assert (
            split_bound.capacity > 0
            and split_bound.demands >= 0
            and split_bound.tunnels >= 0
        )
    if range_limit is not None:
        integer: int = range_limit.units_value
        assert integer >= 0 and report.limited_by == "range"
    for approximation in report.weight_approximations:
        kind: Literal["weight_approximation"] = approximation.kind
        relative_error: Fraction = approximation.max_relative_error
        assert approximation.label and kind and relative_error >= 0
    return q


def controlled_example() -> tuple[int, list[tuple[str, int]]]:
    """A WCMP controller with forwarding groups: delivered units and the reported row."""
    network = Network()
    for name in ("S", "X1", "X2", "T"):
        network.add_node(Node(name))
    for target in ("X1", "X2"):
        network.add_link(Link("S", target, capacity=10, cost=1))
        network.add_link(Link(target, "T", capacity=10, cost=1))
    tree = ForwardingGroup(
        "S",
        (
            ControllerGroup((GroupChild(edge=DirectedLink("S|X1|0", "forward")),)),
            ControllerGroup(
                (GroupChild(edge=DirectedLink("S|X2|0", "forward")),), share="1/2"
            ),
        ),
    )
    # Stored shares are exact Fractions, whatever form declared them.
    caps: Fraction = sum((group.share for group in tree.groups), Fraction(0))
    child: Fraction = tree.groups[0].children[0].share
    assert (caps, child) == (Fraction(3, 2), Fraction(1))
    demands = DemandSet(
        "wcmp",
        (
            DemandSpec(
                Selector("^S$"),
                Selector("^T$"),
                9,
                policy=FlowPolicyPreset.SHORTEST_PATHS_WCMP,
                id="dc",
            ),
        ),
    )
    prepared = prepare(
        Scenario(
            network,
            demand_sets={"wcmp": demands},
            units=UnitsSettings(resolution=1),
            forwarding_groups={"ingress": tree},
            routing=RoutingDomain(Selector("^X[12]$"), Selector("^(S|T)$")),
            wcmp_controller=WCMPController("group"),
        ),
        demand_sets=("wcmp",),
    )
    resolved: ResolvedDemandSet = prepared.demand_sets["wcmp"]
    tables = resolved.controller
    assert tables is not None
    members = [
        (member.edge.link, member.weight)
        for router in tables[0].programmed
        for member in router.members
    ]
    analysis = place(prepared, PlacementQuery(resolved, workers=1))
    read_units(analysis.units_report)
    row = analysis.cases[0].states["converged"].rows[0]
    return row.result.delivered, members


def read_cost(row: CostReport) -> int:
    # The two exported forms have different numerical meanings.
    if isinstance(row, DeliveredByPathCost):
        return sum(bin.delivered_units for bin in row.bins)
    curve: MarginalCurve = row
    return sum(bin.units for bin in curve.bins)


_COMPACT_NATIVE_KEYS = frozenset(
    (
        "request_kind",
        "requested_units",
        "offered_units",
        "delivered_units",
        "unadmitted_units",
        "source_drop_units",
        "edge_drop_units",
        "termination",
        "total_cost",
    )
)
_DETAIL_NATIVE_KEYS = frozenset(
    (
        "call_delivered_units",
        "call_undelivered_units",
        "delivery_delta_units",
        "call_edge_drops",
        "call_source_drop_units",
        "admitted_units",
        "edge_drops",
        "by_source",
        "by_tunnel",
        "plan",
    )
)


def read_native_details(value: ngc.PlacementResult) -> None:
    # Direct native access is available even when its wire projection is compact.
    sources: tuple[ngc.SourceFlow, ...] = value.by_source
    tunnels: tuple[ngc.TunnelFlow, ...] = value.by_tunnel
    plan: ngc.TunnelPlan | None = value.plan
    assert all(isinstance(row.delivered, int) for row in sources)
    assert all(isinstance(row.delivered, int) for row in tunnels)
    assert plan is None or isinstance(plan.tunnels_per_head, int)


def _object(value: JSONValue) -> dict[str, JSONValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JSONValue) -> list[JSONValue]:
    assert isinstance(value, list)
    return value


def check_wire_rows(
    value: CapacityAnalysis | PlacementAnalysis | SensitivityAnalysis | MSDAnalysis,
    *,
    details: bool,
) -> None:
    selection: OutputSelection = value.outputs
    selected_details: bool = selection.details
    assert selected_details is details
    output = StringIO()
    write_json(value, output)
    parsed: JSONValue = json.loads(output.getvalue())
    analysis = _object(_object(parsed)["analysis"])
    selected = _object(analysis["outputs"])
    assert selected["details"] is details
    rows: list[dict[str, JSONValue]] = []
    if analysis["kind"] == "sensitivity":
        native_rows = [_object(analysis["baseline"])]
    else:
        if analysis["kind"] == "msd":
            if analysis["best_rows"] is not None:
                rows.extend(_object(row) for row in _array(analysis["best_rows"]))
            if "probe_rows" in analysis:
                for probe in _array(analysis["probe_rows"]):
                    rows.extend(_object(row) for row in _array(_object(probe)["rows"]))
        else:
            for case in _array(analysis["cases"]):
                state = _object(_object(_object(case)["states"])["converged"])
                rows.extend(_object(row) for row in _array(state["rows"]))
        for row in rows:
            if row["kind"] == "self":
                assert set(row) == {"kind", "id", "node", "capacity_units"}
            else:
                assert "pool" in row
        native_rows = [_object(row["result"]) for row in rows if row["kind"] != "self"]
    flags = (
        ("edge_flows", selection.native.edge_flows),
        ("residual", selection.native.residual),
        ("edge_reservations", selection.native.edge_reservations),
        ("saturated_boundary_edges", selection.native.saturated_boundary_edges),
        ("min_cut", selection.native.min_cut),
    )
    for native in native_rows:
        assert _COMPACT_NATIVE_KEYS <= native.keys()
        for name in ("delivered_units", "source_drop_units", "edge_drop_units"):
            amount = native[name]
            assert (
                isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0
            )
        assert native["request_kind"] in ("finite", "unlimited")
        for name in (
            "requested_units",
            "offered_units",
            "unadmitted_units",
            "total_cost",
        ):
            amount = native[name]
            assert amount is None or (
                isinstance(amount, int) and not isinstance(amount, bool)
            )
        assert (_DETAIL_NATIVE_KEYS & native.keys()) == (
            _DETAIL_NATIVE_KEYS if details else set()
        )
        for name, enabled in flags:
            assert (name in native) is enabled
        if details:
            _array(native["by_source"])
            _array(native["by_tunnel"])
            plan = native["plan"]
            assert plan is None or isinstance(plan, dict)
            delta = native["delivery_delta_units"]
            assert isinstance(delta, int) and not isinstance(delta, bool)
        if not selection.cost_distribution:
            assert all(
                "cost_distribution" not in row and "unavailable_outputs" not in row
                for row in rows
            )


def read_capacity(value: CapacityAnalysis) -> int:
    details: bool = value.outputs.details
    assert isinstance(details, bool)
    total = 0
    for case in value.cases:
        typed_case: CaseResult[CapacityRow | SelfPair] = case
        state = typed_case.states["converged"]
        assert state.totals is None
        for row in state.rows:
            if isinstance(row, SelfPair):
                assert row.capacity_units == 0
            else:
                units: int = row.result.delivered
                total += units
                if row.cost_distribution is not None:
                    assert read_cost(row.cost_distribution) == units
    config: ngc.FlowPolicyConfig = value.query.config
    mode: str = value.query.mode
    assert config.routing is not None and mode
    return total


def read_sensitivity(value: SensitivityAnalysis) -> int:
    details: bool = value.outputs.details
    assert isinstance(details, bool)
    baseline: ngc.PlacementResult = value.result.baseline
    deltas: list[int] = [entry.delivery_reduction for entry in value.result.entries]
    assert all(
        isinstance(delta, int) and not isinstance(delta, bool) for delta in deltas
    )
    source_path: str | None = value.query.source.path
    assert source_path is None or isinstance(source_path, str)
    return baseline.delivered


def read_paths(value: PathAnalysis) -> list[int | None]:
    costs: list[int | None] = []
    for row in value.rows:
        costs.append(row.cost)
        if row.paths is not None:
            for path in row.paths:
                native_cost: int = path.cost()
                assert native_cost >= 0
    options = value.query.options
    if isinstance(options, ngc.KspOptions):
        assert value.algorithm == "ksp"
    else:
        assert value.algorithm == "spf" and int(options.min_residual) >= 1
    return costs


def read_placement(value: PlacementAnalysis) -> None:
    details: bool = value.outputs.details
    assert isinstance(details, bool)
    set_name: str = value.query.demands.name
    assert set_name
    for case in value.cases:
        state: CaseState[PlacementRow] = case.states["converged"]
        assert state.totals is not None
        reference: int = state.totals.reference_request_units
        assert reference >= 0
        for row in state.rows:
            if row.pool is not None:
                # An ordered workflow prepares no lossy pool budget.
                budget: int = row.pool.offer_limit_units
                assert budget == 0
            if row.cost_distribution is not None:
                read_cost(row.cost_distribution)


def read_msd(value: MSDAnalysis) -> MSDStatus:
    details: bool = value.outputs.details
    assert isinstance(details, bool)
    status: MSDStatus = value.search_status
    known_status: Literal[
        "feasible", "none_feasible", "range", "stagnation", "limit", "trivial"
    ] = status
    legal_statuses: tuple[MSDStatus, ...] = (
        "feasible",
        "none_feasible",
        "range",
        "stagnation",
        "limit",
        "trivial",
    )
    assert known_status in legal_statuses
    reason: MSDStopReason = value.stop_reason
    proof: MSDProof = value.proof
    assert reason and proof
    for probe in value.history:
        outcome: str = probe.outcome
        assert outcome in ("feasible", "infeasible", "range")
        if probe.totals is not None:
            delivered: int = probe.totals.delivered_units
            ratio: Fraction = probe.totals.delivery_ratio
            assert delivered >= 0 and ratio >= 0
        if probe.range_refusal is not None:
            why: str = probe.range_refusal.reason
            assert why in ("scaled_nonfinite", "native_units_range")
    if value.alpha_feasible is not None:
        alpha: float = value.alpha_feasible.value
        assert alpha > 0 and value.best_rows is not None
    if value.upper_certificate is not None:
        upper: float = value.upper_certificate.upper.value
        lower: float = value.upper_certificate.lower.value
        index: int = value.upper_certificate.upper_probe_index
        assert lower < upper and value.history[index].outcome == "infeasible"
    if value.best_rows is not None:
        for best_row in value.best_rows:
            best_delivered: int = best_row.result.delivered
            assert best_delivered >= 0
    if value.probe_rows is not None:
        for index, rows in value.probe_rows.items():
            assert value.history[index].outcome != "range"
            assert all(
                row.result.requested == row.reference_request_units for row in rows
            )
    bounds: float = value.query.alpha_max
    assert bounds > 0
    return status


def read_counts(value: TunnelCountAnalysis) -> list[tuple[int, bool, int]]:
    """Each row's requested count or limit, whether it is an up-to row, and the chosen count."""
    out: list[tuple[int, bool, int]] = []
    for row in value.rows:
        count: int = row.count
        up_to: bool = row.up_to
        plan: ngc.TunnelPlan | None = row.result.plan
        assert plan is not None
        chosen: int = plan.tunnels_per_head
        lossless: int = row.lossless_at_design_units
        cost: int = row.physical_tunnel_cost
        pool: PoolMetadata | None = row.pool
        assert lossless >= 0 and cost >= 0
        assert pool is None or pool.offer_limit_units >= 0
        out.append((count, up_to, chosen))
    query: TunnelCountQuery = value.query
    assert query.offer >= 0 and query.design_demand >= 0
    return out


def counts_example() -> list[tuple[int, bool, int]]:
    """Two heads behind links of 2 and 10, two tunnels per head, design and offer 12."""
    network = Network()
    for name in ("A", "B", "T"):
        network.add_node(Node(name))
    network.add_link(Link("A", "T", capacity=2, cost=1))
    network.add_link(Link("B", "T", capacity=10, cost=1))
    model = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(2),
        )
    )
    demands = DemandSet(
        "te", (DemandSpec(Selector("^(A|B)$"), Selector("^T$"), 0, model),)
    )
    step = TunnelCountStep(
        "counts", demand_set="te", counts=(2,), up_to=2, design_demand=12, offer=12
    )
    prepared = prepare(
        Scenario(network, (step,), demand_sets={"te": demands}, units=UnitsSettings(1))
    )
    result = run(prepared)
    analysis = result.steps[0].result
    assert isinstance(analysis, TunnelCountAnalysis)
    library = tunnel_counts(
        prepared, TunnelCountQuery(prepared.demand_sets["te"], (2,), 12, 12, up_to=2)
    )
    assert read_counts(library) == read_counts(analysis)
    return read_counts(analysis)


def read_domain(value: DomainResult) -> float:
    if isinstance(value, NetworkStatsResult):
        capacity_total: float = value.total_capacity
        return capacity_total
    if isinstance(value, CostPowerResult):
        power: float = sum(
            row.power_total_watts for rows in value.levels.values() for row in rows
        )
        return power
    graph: BuildGraphResult = value
    count: int = graph.node_count
    assert graph.graph and count >= 0
    return float(count)


def read_run(value: RunResult) -> None:
    assert read_units(value.units_report) == value.topology.q
    version: str = value.metadata.core_version
    digest: str = value.metadata.core_extension_sha256
    assert version and len(digest) == 64
    for step in value.steps:
        name: str = step.name
        order: int = step.execution_order
        assert name and order >= 0
        assert step.question is not None
        if isinstance(step.result, PlacementAnalysis):
            for case in step.result.cases:
                state: CaseState[PlacementRow] = case.states["converged"]
                assert state.totals is not None
                assert tuple(case.states) == ("converged", "stale")
                stale: CaseState[PlacementRow] = case.states["stale"]
                failure: ForwardingFailure | None = stale.failure
                caps: tuple[DeadCap, ...] | None = stale.dead_caps
                assert failure is None and caps is None
        elif isinstance(step.result, MSDAnalysis):
            read_msd(step.result)
        elif isinstance(
            step.result, (BuildGraphResult, NetworkStatsResult, CostPowerResult)
        ):
            read_domain(step.result)


@dataclass(frozen=True)
class CustomNodeCount:
    nodes: int


def export_node_count(value: CustomNodeCount, context: ExportContext) -> JSONValue:
    assert context.units_report.q == context.topology.q
    payload: JSONValue = {"nodes": value.nodes}
    return payload


register_result_exporter(CustomNodeCount, export_node_count)


@register_workflow_step("CountNodes")
class CountNodes(WorkflowStep):
    def run(self, context: StepContext) -> StepOutput:
        for previous in context.prior_results.values():
            # alpha_from_step must narrow the actual typed earlier result.
            if isinstance(previous.result, MSDAnalysis):
                assert previous.result.alpha_feasible is not None
                step_name: str = previous.name
                assert step_name
        return StepOutput(
            {"metric": "nodes"},
            CustomNodeCount(len(context.prepared.topology.node_names)),
        )


def read_template(value: ResolvedDemandSet) -> None:
    for parent in value.expansion_template:
        physical: float = parent.physical_volume
        ordinal: int = parent.declaration_ordinal
        source: str | None = parent.source.path
        priority: int = parent.priority
        assert source is None or isinstance(source, str)
        assert isinstance(priority, int) and parent.policy is not None
        assert physical >= 0 and ordinal >= 0


def workflow_details_example() -> RunResult:
    result = run(
        prepare(
            Scenario.from_yaml("""
units: {resolution: 1}
network:
  nodes: {A: {}, T: {}}
  links: [{source: A, target: T, capacity: 10, cost: 1}]
demands:
  demo: [{source: '^A$', target: '^T$', volume: 2, preset: TE_MAXFLOW_UNLIM}]
workflow:
  - {type: MaxFlow, name: compact_capacity, source: '^A$', target: '^T$', workers: 1}
  - type: MaxFlow
    name: detail_capacity
    source: '^A$'
    target: '^T$'
    workers: 1
    outputs: {details: true}
  - {type: TrafficMatrixPlacement, name: compact_placement, demand_set: demo, workers: 1}
  - type: TrafficMatrixPlacement
    name: detail_placement
    demand_set: demo
    workers: 1
    outputs: {details: true}
  - {type: MaximumSupportedDemand, name: compact_msd, demand_set: demo}
  - type: MaximumSupportedDemand
    name: detail_msd
    demand_set: demo
    outputs: {details: true}
""")
        )
    )
    for step in result.steps:
        analysis = step.result
        assert isinstance(analysis, (CapacityAnalysis, PlacementAnalysis, MSDAnalysis))
        check_wire_rows(analysis, details=step.name.startswith("detail_"))
    return result


def example() -> tuple[RunResult, PlacementAnalysis, MSDAnalysis, str]:
    workflow_details_example()
    network = Network()
    for name in ("A", "B", "T"):
        network.add_node(Node(name))
    network.add_link(Link("A", "B", capacity=10, cost=1))
    network.add_link(Link("A", "B", capacity=10, cost=2))
    network.add_link(Link("B", "T", capacity=20, cost=1))
    ab, bt = DirectedLink("A|B|0", "forward"), DirectedLink("B|T|0", "forward")
    demands = DemandSet(
        "example",
        (
            DemandSpec(
                Selector("^A$"),
                Selector("^T$"),
                8,
                policy=PinnedRoutes(("cheap",)),
                id="pinned",
            ),
            DemandSpec(
                Selector("^A$"),
                Selector("^T$"),
                2,
                policy=PinnedRoutes(
                    ("dag_entry",),
                    allocation=ngc.RouteAllocation.WEIGHTED,
                    weight_basis=ngc.WeightBasis.EXPLICIT,
                    edge_weights="cheap_weights",
                ),
                id="dag",
            ),
        ),
    )
    policy = FailurePolicy(modes=(FailureMode(1.0, (FailureRule("link"),)),))
    scenario = Scenario(
        network,
        (CountNodes(name="count"),),
        demand_sets={"example": demands},
        failure_policies={"one_link": policy},
        components_library=ComponentsLibrary(),
        routes={
            "cheap": RouteSpec(head="A", nodes=("A", "B", "T")),
            "dag_entry": RouteSpec(head="A", support="cheap_dag"),
        },
        supports={"cheap_dag": SupportSpec((ab, bt))},
        weights={"cheap_weights": WeightSpec((EdgeWeight(ab, 1), EdgeWeight(bt, 1)))},
        units=UnitsSettings(resolution=1),
        seed=42,
    )
    prepared = prepare(scenario, demand_sets=("example",))
    resolved: ResolvedDemandSet = resolve_demands(prepared, demands)
    read_template(resolved)
    request = FailureRequest(policy, iterations=2, seed=42, failure_trace=True)
    cases: tuple[FailureCase, ...] = failure_cases(prepared, request)
    assert sum(case.occurrences for case in cases) == 2
    result: RunResult = run(prepared)
    read_run(result)
    placement = place(
        prepared,
        PlacementQuery(
            resolved,
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=True),
            export_cost_distribution=True,
        ),
    )
    state = placement.cases[0].states["converged"]
    assert tuple(row.result.delivered for row in state.rows) == (8, 2)
    read_placement(placement)
    check_wire_rows(placement, details=False)  # cost/edge outputs do not imply details
    for row in state.rows:
        read_native_details(row.result)
    detailed_placement = place(
        prepared, PlacementQuery(resolved, workers=1, export_details=True)
    )
    check_wire_rows(
        detailed_placement, details=True
    )  # details do not imply costs/arrays
    supported = maximum_supported_demand(prepared, MSDQuery(resolved))
    read_msd(supported)
    check_wire_rows(supported, details=False)
    detailed_msd = maximum_supported_demand(
        prepared, MSDQuery(resolved, export_details=True, export_probe_rows=True)
    )
    check_wire_rows(detailed_msd, details=True)
    assert detailed_msd.probe_rows is not None
    cap = capacity(prepared, CapacityQuery(Selector("^A$"), Selector("^T$"), workers=1))
    assert read_capacity(cap) == 20
    check_wire_rows(cap, details=False)
    detailed_cap = capacity(
        prepared,
        CapacityQuery(Selector("^A$"), Selector("^T$"), workers=1, export_details=True),
    )
    check_wire_rows(detailed_cap, details=True)
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    sensitivity = edge_sensitivity(
        prepared,
        SensitivityQuery(Selector("^A$"), Selector("^T$"), config, workers=1),
    )
    assert read_sensitivity(sensitivity) == 20
    check_wire_rows(sensitivity, details=False)
    read_native_details(sensitivity.result.baseline)
    detailed_sensitivity = edge_sensitivity(
        prepared,
        SensitivityQuery(
            Selector("^A$"), Selector("^T$"), config, workers=1, export_details=True
        ),
    )
    check_wire_rows(detailed_sensitivity, details=True)
    routes = paths(prepared, PathQuery(Selector("^A$"), Selector("^T$")))
    assert read_paths(routes) == [2]
    output = StringIO()
    write_json(placement, output)
    return result, placement, supported, output.getvalue()


def public_submodule_boundaries(network: Network) -> None:
    from ngraph.hardware import hardware_inventory, resolve_link_end
    from ngraph.logging import get_logger, set_global_log_level, setup_root_logger
    from ngraph.workflow import StepNeeds, step_name

    needs: StepNeeds = StepNeeds(numerical=False)
    assert not needs.numerical
    assert callable(step_name) and callable(resolve_link_end)
    assert callable(hardware_inventory) and callable(get_logger)
    assert callable(set_global_log_level) and callable(setup_root_logger)
