"""Evaluated tunnel plans and graph validation survive empty traffic selections."""

from dataclasses import replace
from fractions import Fraction

import netgraph_core as core
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    DirectedLink,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    SensitivityQuery,
    TunnelCountQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    place,
    prepare,
    resolve_demands,
    run,
    tunnel_counts,
)
from ngraph.analysis.programs import dag_from_edges
from ngraph.results import SelfPair
from ngraph.workflow import MaxFlow, MaximumSupportedDemand, TrafficMatrixPlacement


def network(capacity_=100, sources=("a",)):
    n = Network(nodes={s: Node(s) for s in (*sources, "t")})
    for s in sources:
        n.add_link(Link(s, "t", capacity_))
    return n


def t2(limit, up_to=False):
    return core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(limit, up_to=up_to),
        ),
        admission=core.Admission.LOSSY,
    )


def constraint_value(c):
    return (
        c.kind,
        c.label,
        c.incoming_physical,
        c.basis,
        c.members,
        c.q_upper_bound,
        c.met,
    )


def constraints(answer):
    return [c for miss in answer.misses for c in miss.constraints]


@pytest.mark.parametrize(
    "limit,up_to,actual", [(1, False, 1), (2, True, 1), (2, False, 2), (4, True, 1)]
)
def test_tunnel_precision_reads_the_chosen_plan_in_every_observed_reader(
    limit, up_to, actual
):
    config = t2(limit, up_to)
    d = DemandSet("d", (DemandSpec(Selector("a"), Selector("t"), 10, config),))
    p = prepare(
        Scenario(network(), demand_sets={"d": d}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    expected = (
        []
        if actual == 1
        else [
            (
                "tunnel",
                "demand.d|0|0.head[0]",
                Fraction(10),
                "declared",
                2,
                Fraction(0.075) * 10,
                False,
            )
        ]
    )
    assert [constraint_value(c) for c in p.units_report.nominal_splits] == expected
    assert p.units_report.target_met is (actual == 1)
    asked = capacity(
        p,
        CapacityQuery(
            Selector("a"), Selector("t"), config, offer=10, design_demand=10, workers=1
        ),
    )
    placed = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    counted = tunnel_counts(
        p,
        TunnelCountQuery(
            p.demand_sets["d"],
            () if up_to else (limit,),
            10,
            10,
            up_to=limit if up_to else None,
            workers=1,
        ),
    )
    sensitive = edge_sensitivity(
        p,
        SensitivityQuery(
            Selector("a"), Selector("t"), config, offer=10, design_demand=10, workers=1
        ),
    )
    for answer, result, prefix in (
        (asked, asked.cases[0].states["converged"].rows[0].result, "capacity.pair[0]"),
        (placed, placed.cases[0].states["converged"].rows[0].result, "demand.d|0|0"),
        (
            counted,
            counted.rows[0].result,
            f"tunnel_counts.demand[d|0|0].{'up_to' if up_to else 'count'}[{limit}]",
        ),
        (sensitive, sensitive.result.baseline, "sensitivity.baseline"),
    ):
        assert result.plan.tunnels_per_head == actual
        assert result.plan.design_by_head == ((0, 10),)
        assert result.plan.heads_with_capacity == (0,)
        assert len(result.by_tunnel) == actual
        local = [c for c in constraints(answer) if c.label.startswith(prefix + ".")]
        assert [constraint_value(c) for c in local] == (
            []
            if actual == 1
            else [
                (
                    "tunnel",
                    prefix + ".head[0]",
                    Fraction(10),
                    "declared",
                    2,
                    Fraction(0.075) * 10,
                    False,
                )
            ]
        )
    automatic = prepare(
        Scenario(network(), demand_sets={"d": d}, units=UnitsSettings("auto", 0.075)),
        demand_sets=("d",),
    )
    assert automatic.topology.q == (1 if actual == 1 else 0.5)


@pytest.mark.parametrize(
    "cap,design,offer",
    [(0, 10, 10), (1, 10, 10), (100, 12, 10), (100, 10, 0), (100, 0, 10)],
)
def test_tunnel_design_bounds_omit_only_heads_without_capacity(cap, design, offer):
    p = prepare(Scenario(network(cap), units=UnitsSettings(1, 0.075)))
    config = t2(2)
    answer = capacity(
        p,
        CapacityQuery(
            Selector("a"),
            Selector("t"),
            config,
            offer=offer,
            design_demand=design,
            workers=1,
        ),
    )
    row = answer.cases[0].states["converged"].rows[0]
    assert row.result.plan.tunnels_per_head == 2
    assert len(row.result.by_tunnel) == (2 if cap == 100 else 0)
    local = [c for c in constraints(answer) if c.kind == "tunnel"]
    expected = []
    if cap > 0 and offer > 0:
        expected.append(
            (
                "tunnel",
                "capacity.pair[0].head[0]",
                Fraction(offer),
                "declared",
                2,
                Fraction(0.075) * offer,
                False,
            )
        )
    if cap > 0 and design > 0 and design != offer:
        expected.append(
            (
                "tunnel",
                "capacity.pair[0].design.head[0]",
                Fraction(design),
                "declared",
                2,
                Fraction(0.075) * design,
                False,
            )
        )
    assert [constraint_value(c) for c in local] == expected


def test_dead_t1_heads_keep_the_requested_split_count():
    p = prepare(Scenario(network(0), units=UnitsSettings(1, 0.075)))
    config = core.FlowPolicyConfig(
        routing=core.DistributedTE(core.TunnelCount(2)), admission=core.Admission.LOSSY
    )
    a = capacity(
        p,
        CapacityQuery(
            Selector("a"), Selector("t"), config, offer=10, design_demand=10, workers=1
        ),
    )
    assert [(c.kind, c.members, c.incoming_physical) for c in constraints(a)] == [
        ("tunnel", 2, Fraction(10))
    ]


def program(p):
    graph = p.topology.graph
    edge = p.topology._edge_id_by_ref[DirectedLink("a|t|0", "forward")]
    return core.ForwardingProgram.from_dag(
        graph,
        [p.topology.node_id_by_name["a"]],
        [p.topology.node_id_by_name["t"]],
        dag_from_edges(graph, [edge]),
    )


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
@pytest.mark.parametrize("foreign", [False, True])
def test_diagonal_pinned_questions_validate_the_program_graph(mode, foreign):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    origin = prepare(Scenario(network(), units=UnitsSettings(1))) if foreign else p
    config = core.FlowPolicyConfig(
        routing=core.Pinned(program(origin)), admission=core.Admission.LOSSY
    )
    query = CapacityQuery(
        Selector("a"), Selector("a"), config, mode=mode, offer=10, workers=1
    )
    if foreign:
        with pytest.raises(ValueError, match="program belongs to another graph"):
            capacity(p, query)
        with pytest.raises(ValueError, match="program belongs to another graph"):
            capacity(
                p,
                CapacityQuery(
                    Selector("a"), Selector("t"), config, offer=10, workers=1
                ),
            )
        with pytest.raises(ValueError, match="program belongs to another graph"):
            prepare(
                Scenario(
                    network(),
                    [
                        MaxFlow(
                            source=Selector("a"),
                            target=Selector("a"),
                            model=config,
                            mode=mode,
                            offer=10,
                        )
                    ],
                    units=UnitsSettings(1),
                )
            )
    else:
        rows = capacity(p, query).cases[0].states["converged"].rows
        assert len(rows) == 1 and isinstance(rows[0], SelfPair) and rows[0].node == "a"
        assert (
            capacity(
                p,
                CapacityQuery(
                    Selector("a"), Selector("t"), config, offer=10, workers=1
                ),
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 10
        )


@pytest.mark.parametrize(
    "source,target", [("a", "a"), ("missing", "t"), ("disabled", "t")]
)
@pytest.mark.parametrize(
    "model_kind", ["edge_weights", "source_weights", "support", "pinned", "valid"]
)
def test_discarded_demands_still_validate_materialized_models(
    source, target, model_kind
):
    n = network()
    n.add_node(Node("disabled", disabled=True))
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    other = prepare(Scenario(network(), units=UnitsSettings(1)))
    if model_kind == "edge_weights":
        model = core.ShortestPaths(
            allocation=core.RouteAllocation.WEIGHTED,
            weight_basis=core.WeightBasis.EXPLICIT,
            edge_weights=[1],
        )
        reason = "edge_weights: expected 2 entries"
    elif model_kind == "source_weights":
        model = core.CentralizedTE(
            source_allocation=core.SourceAllocation.WEIGHTED, source_weights=[1]
        )
        reason = "source_weights: expected 3 entries"
    elif model_kind == "support":
        model = core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            support=dag_from_edges(other.topology.graph, [0]),
        )
        reason = "support belongs to another graph"
    elif model_kind == "pinned":
        model = core.Pinned(program(other))
        reason = "program belongs to another graph"
    else:
        model = core.ShortestPaths()
        reason = None
    config = core.FlowPolicyConfig(routing=model)
    d = DemandSet("load", (DemandSpec(Selector(source), Selector(target), 7, config),))
    if reason is not None:
        with pytest.raises(ValueError, match=r"demands\.load\[0\].*" + reason):
            resolve_demands(p, d)
        for steps in (
            [],
            [TrafficMatrixPlacement(demand_set="load")],
            [MaximumSupportedDemand(demand_set="load")],
        ):
            with pytest.raises(ValueError, match=r"demands\.load\[0\].*" + reason):
                prepare(
                    Scenario(n, steps, demand_sets={"load": d}, units=UnitsSettings(1)),
                    demand_sets=("load",),
                )
    else:
        resolved = resolve_demands(p, d)
        assert resolved.demands == ()
        assert (
            resolved.accounting[0].declared_units
            == resolved.accounting[0].discarded_units
            == 7
        )
        assert resolved.accounting[0].resolved_units == 0


def test_shared_demand_model_is_validated_once_before_resolution(monkeypatch):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    config = core.FlowPolicyConfig(routing=core.ShortestPaths())
    d = DemandSet(
        "d",
        tuple(
            DemandSpec(Selector("a"), Selector(target), 1, config)
            for target in ("a", "t", "missing")
        ),
    )
    original = core.evaluate_pairs
    calls = []

    def evaluate(graph, pairs, options, **kwargs):
        calls.append((tuple(pairs), options.eligibility.node_allowed().tolist()))
        return original(graph, pairs, options, **kwargs)

    monkeypatch.setattr(core, "evaluate_pairs", evaluate)
    resolved = resolve_demands(p, d)
    assert calls == [((), [False, False])]
    assert len(resolved.demands) == 1
    assert [a.discarded_units for a in resolved.accounting] == [1, 0, 1]


def test_support_and_failure_mask_intersect_in_capacity_and_counts():
    p = prepare(Scenario(network(sources=("a", "b")), units=UnitsSettings(1, 0.075)))
    support = dag_from_edges(
        p.topology.graph,
        [
            p.topology._edge_id_by_ref[DirectedLink(f"{s}|t|0", "forward")]
            for s in ("a", "b")
        ],
    )
    config = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            support=support,
            tunnel_count=core.TunnelCount(1),
        ),
        admission=core.Admission.LOSSY,
    )
    failure = FailureRequest(
        FailurePolicy(modes=(FailureMode(1, (FailureRule("link", path=r"^b\|t$"),)),)),
        1,
        1,
    )
    a = capacity(
        p,
        CapacityQuery(
            Selector("a|b"),
            Selector("t"),
            config,
            offer=10,
            design_demand=10,
            failures=failure,
            workers=1,
        ),
    )
    assert [
        r.states["converged"].rows[0].result.plan.design_by_head for r in a.cases
    ] == [((0, 5), (1, 5)), ((0, 10),)]
    assert len(a.misses) == 1 and a.misses[0].location.case_id == "baseline"
    assert [constraint_value(c) for c in a.misses[0].constraints] == [
        (
            "source",
            "capacity.pair[0].sources",
            Fraction(10),
            "declared",
            2,
            Fraction(0.075) * 10,
            False,
        )
    ]
    ds = resolve_demands(
        p, DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, config),))
    )
    baseline = tunnel_counts(p, TunnelCountQuery(ds, (1,), 10, 10, workers=1))
    failed = tunnel_counts(
        p,
        TunnelCountQuery(
            ds,
            (1,),
            10,
            10,
            eligibility=p.topology.graph.eligibility(
                excluded_edges=[
                    p.topology._edge_id_by_ref[DirectedLink("b|t|0", "forward")]
                ]
            ),
            workers=1,
        ),
    )
    assert baseline.rows[0].result.plan.design_by_head == ((0, 5), (1, 5))
    assert failed.rows[0].result.plan.design_by_head == ((0, 10),)
    assert len(baseline.misses) == 1 and failed.misses == ()


def test_pinned_diagonal_preparation_and_step_accept_an_own_program():
    class OwnProgram(MaxFlow):
        def query(self, prepared, failures=None):
            config = core.FlowPolicyConfig(
                routing=core.Pinned(program(prepared)), admission=core.Admission.LOSSY
            )
            return CapacityQuery(
                Selector("a"), Selector("a"), config, offer=10, workers=1
            )

    p = prepare(Scenario(network(), [OwnProgram(name="own")], units=UnitsSettings(1)))
    value = run(p)
    rows = value.steps[0].result.cases[0].states["converged"].rows
    assert len(rows) == 1 and isinstance(rows[0], SelfPair) and rows[0].node == "a"


@pytest.mark.parametrize(
    "allocation", [core.SourceAllocation.EQUAL, core.SourceAllocation.WEIGHTED]
)
def test_controller_precision_reads_native_records_without_a_search(
    allocation, monkeypatch
):
    config = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=allocation,
            source_weights=[1, 1, 0]
            if allocation == core.SourceAllocation.WEIGHTED
            else None,
        )
    )
    d = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, config),))
    p = prepare(
        Scenario(
            network(sources=("a", "b")),
            demand_sets={"d": d},
            units=UnitsSettings(1, 0.075),
        ),
        demand_sets=("d",),
    )
    original = core.FlowPolicy.records
    records = []

    def read(owner):
        records.append(owner)
        return original(owner)

    def search(*args, **kwargs):
        raise AssertionError("placement precision must use native source records")

    monkeypatch.setattr(core.FlowPolicy, "records", read)
    monkeypatch.setattr(core, "spf", search)
    a = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert len(records) == 1
    assert [constraint_value(c) for c in constraints(a)] == [
        (
            "source",
            "demand.d|0|0.sources",
            Fraction(10),
            "declared",
            2,
            Fraction(0.075) * 10,
            False,
        )
    ]


def test_each_count_row_uses_its_own_demand_count_and_up_to_plan():
    p = prepare(Scenario(network(sources=("a", "b")), units=UnitsSettings(1, 0.075)))
    config = t2(2)
    ds = resolve_demands(
        p,
        DemandSet(
            "d",
            tuple(
                DemandSpec(Selector(s), Selector("t"), 10, config) for s in ("a", "b")
            ),
        ),
    )
    answer = tunnel_counts(p, TunnelCountQuery(ds, (2, 4), 10, 10, up_to=4, workers=1))
    expected = []
    for index in range(2):
        for count in (2, 4):
            expected.append(
                (
                    "tunnel",
                    f"tunnel_counts.demand[d|{index}|0].count[{count}].head[{index}]",
                    Fraction(10),
                    "declared",
                    count,
                    Fraction(0.075) * 10 / (count - 1),
                    False,
                )
            )
    assert [constraint_value(c) for c in constraints(answer)] == expected
    assert [row.result.plan.tunnels_per_head for row in answer.rows] == [
        2,
        4,
        1,
        2,
        4,
        1,
    ]
    assert [row.result.plan.design_by_head for row in answer.rows] == [
        ((0, 10),)
    ] * 3 + [((1, 10),)] * 3


def test_every_controller_leaf_model_is_checked_once(monkeypatch):
    import ngraph.analysis.demands as binding
    from ngraph import FlowPolicyPreset, RoutingDomain, WCMPController

    n = Network(nodes={s: Node(s) for s in ("S", "A", "T1", "T2")})
    for u, v in [("S", "A"), ("A", "T1"), ("A", "T2")]:
        n.add_link(Link(u, v, 100))
    d = DemandSet(
        "d",
        (
            DemandSpec(
                Selector("^S$"),
                Selector("^T"),
                10,
                FlowPolicyPreset.SHORTEST_PATHS_WCMP,
                mode="pairwise",
            ),
        ),
    )
    p = prepare(
        Scenario(
            n,
            demand_sets={"d": d},
            units=UnitsSettings(1),
            routing=RoutingDomain(Selector("^A$"), Selector("^(S|T1|T2)$")),
            wcmp_controller=WCMPController(),
        ),
        demand_sets=("d",),
    )
    original = binding.validate_model
    calls = []

    def check(topology, config):
        calls.append(config)
        return original(topology, config)

    monkeypatch.setattr(binding, "validate_model", check)
    resolved = resolve_demands(p, d)
    assert len(resolved.demands) == 2
    assert len({row.config for row in resolved.demands}) == 2
    assert calls == [row.config for row in resolved.demands]


@pytest.mark.parametrize("admission", [core.Admission.LOSSLESS, core.Admission.LOSSY])
@pytest.mark.parametrize(
    "routing",
    [
        core.DistributedTE(core.TunnelCount(2)),
        core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(2, up_to=True),
        ),
    ],
)
def test_valid_discarded_tunnel_models_need_no_offer_or_design_question(
    admission, routing
):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    d = DemandSet(
        "d",
        (
            DemandSpec(
                Selector("a"),
                Selector("a"),
                7,
                core.FlowPolicyConfig(routing=routing, admission=admission),
            ),
        ),
    )
    resolved = resolve_demands(p, d)
    assert resolved.demands == ()
    assert (
        resolved.accounting[0].declared_units
        == resolved.accounting[0].discarded_units
        == 7
    )


def test_model_validation_accepts_unhashable_configs():
    class Unhashable(core.FlowPolicyConfig):
        __hash__ = None

    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    valid = Unhashable(routing=core.ShortestPaths())
    d = DemandSet("d", (DemandSpec(Selector("a"), Selector("a"), 1, valid),))
    assert resolve_demands(p, d).accounting[0].discarded_units == 1


def test_pinned_diagonal_checks_the_original_question_options():
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    config = core.FlowPolicyConfig(
        routing=core.Pinned(program(p)), admission=core.Admission.LOSSY
    )
    query = CapacityQuery(Selector("a"), Selector("a"), config, offer=10, workers=1)
    assert isinstance(capacity(p, query).cases[0].states["converged"].rows[0], SelfPair)
    with pytest.raises(ValueError, match="Pinned does not accept design_demand"):
        capacity(p, replace(query, design_demand=10))
    with pytest.raises(
        ValueError, match="Pinned LOSSY evaluation requires a finite offer"
    ):
        capacity(p, replace(query, offer=None))


def test_discarded_own_pinned_model_is_validated_once_with_its_own_endpoints(
    monkeypatch,
):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    prog = program(p)
    config = core.FlowPolicyConfig(
        routing=core.Pinned(prog), admission=core.Admission.LOSSY
    )
    original = core.evaluate_demand
    calls = []

    def evaluate(graph, sources, destinations, options):
        calls.append(
            (
                tuple(sources),
                tuple(destinations),
                options.eligibility.node_allowed().tolist(),
                options.offer,
            )
        )
        return original(graph, sources, destinations, options)

    monkeypatch.setattr(core, "evaluate_demand", evaluate)
    d = DemandSet(
        "d",
        tuple(DemandSpec(Selector("a"), Selector("a"), 7, config) for _ in range(2)),
    )
    r = resolve_demands(p, d)
    assert calls == [((0,), (1,), [False, False], 0)]
    assert r.demands == () and sum(a.discarded_units for a in r.accounting) == 14


def test_only_the_live_t2_head_lays_out_tunnels_while_both_sources_split():
    n = network(sources=("a", "b"))
    n.replace_link("b|t|0", capacity=0)
    config = t2(2)
    d = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, config),))
    p = prepare(
        Scenario(n, demand_sets={"d": d}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    asked = capacity(
        p,
        CapacityQuery(
            Selector("a|b"),
            Selector("t"),
            config,
            offer=10,
            design_demand=10,
            workers=1,
        ),
    )
    placed = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    for answer, prefix in [(asked, "capacity.pair[0]"), (placed, "demand.d|0|0")]:
        row = answer.cases[0].states["converged"].rows[0]
        assert row.result.plan.design_by_head == ((0, 5), (1, 5))
        assert row.result.plan.heads_with_capacity == (0,)
        assert len(row.result.by_tunnel) == 2
        assert row.result.delivered == 5 and row.result.source_drops == 5
        assert [constraint_value(c) for c in constraints(answer)] == [
            (
                "source",
                prefix + ".sources",
                Fraction(10),
                "declared",
                2,
                Fraction(0.075) * 10,
                False,
            ),
            (
                "tunnel",
                prefix + ".head[0]",
                Fraction(5),
                "declared",
                2,
                Fraction(0.075) * 5,
                False,
            ),
        ]


@pytest.mark.parametrize("offer,design", [(0, 10), (10, 12), (12, 10)])
def test_up_to_chosen_one_adds_neither_offer_nor_design_split(offer, design):
    p = prepare(Scenario(network(), units=UnitsSettings(1, 0.075)))
    config = t2(2, True)
    answer = capacity(
        p,
        CapacityQuery(
            Selector("a"),
            Selector("t"),
            config,
            offer=offer,
            design_demand=design,
            workers=1,
        ),
    )
    assert answer.cases[0].states["converged"].rows[0].result.plan.tunnels_per_head == 1
    assert answer.misses == ()
    d = resolve_demands(
        p, DemandSet("d", (DemandSpec(Selector("a"), Selector("t"), 10, config),))
    )
    counted = tunnel_counts(
        p, TunnelCountQuery(d, (), design, offer, up_to=2, workers=1)
    )
    assert counted.rows[0].result.plan.tunnels_per_head == 1 and counted.misses == ()


@pytest.mark.parametrize("up_to,expected_q", [(False, 0.5), (True, 1)])
def test_capacity_preparation_uses_the_observed_plan_at_each_q(up_to, expected_q):
    step = MaxFlow(
        name="ask",
        source=Selector("a"),
        target=Selector("t"),
        model=t2(2, up_to),
        offer=10,
        design_demand=10,
        workers=1,
    )
    p = prepare(Scenario(network(), [step], units=UnitsSettings("auto", 0.075)))
    assert p.topology.q == expected_q
    assert p.units_report.target_met
    assert [
        (c.kind, c.members, c.q_upper_bound, c.met)
        for c in p.units_report.nominal_splits
    ] == ([] if up_to else [("tunnel", 2, Fraction(0.075) * 10, True)])


@pytest.mark.parametrize("precision,q", [(0.1, 1 / 16), (0.07, 1 / 32), (0.05, 1 / 32)])
def test_automatic_preset_resolution_keeps_live_heads_with_zero_tunnel_units(
    precision, q
):
    scenario = Scenario.from_yaml(
        f"""
network:
  nodes: {{a: {{}}, t: {{}}}}
  links: [{{source: a, target: t, capacity: 10}}]
demands:
  d: [{{source: "^a$", target: "^t$", volume: 10, preset: TE_ECMP_16_LSP}}]
units: {{resolution: auto, precision: {precision}}}
workflow:
  - {{type: TrafficMatrixPlacement, name: tm, demand_set: d}}
"""
    )
    p = prepare(scenario)
    assert p.topology.q == q
    assert p.units_report.target_met is True
    splits = [c for c in p.units_report.nominal_splits if c.kind == "tunnel"]
    assert len(splits) == 1
    split = splits[0]
    assert split.members == 16
    assert split.incoming_physical == 10
    assert split.q_upper_bound == Fraction(precision) * 10 / 15
    assert split.met is True
    result = run(p)
    state = result.steps[0].result.cases[0].states["converged"]
    assert state.totals.delivered_units == int(10 / q)
    assert result.units_report.target_met is True
    assert result.units_report.misses == ()
    plan = state.rows[0].result.plan
    assert plan.tunnels_per_head == 16
    assert plan.insufficient_resolution is False
    assert plan.max_bandwidth_per_tunnel > 0
    # The combined-demand pool head follows the two physical nodes.
    assert plan.heads_with_capacity == (2,)


def shared_link_up_to_scenario(heads, capacity_, volume, precision, resolution="auto"):
    nodes = ", ".join(f"s{i}: {{}}" for i in range(heads))
    links = "\n".join(
        f"    - {{source: s{i}, target: x, capacity: 1000}}" for i in range(heads)
    )
    return Scenario.from_yaml(
        f"""
network:
  nodes: {{{nodes}, x: {{}}, t: {{}}}}
  links:
{links}
    - {{source: x, target: t, capacity: {capacity_}}}
demands:
  d:
    - source: "^s"
      target: "^t$"
      volume: {volume}
      model:
        admission: lossy
        routing:
          type: centralized_te
          source_allocation: equal
          tunnel_count: {{per_head: 256, up_to: true}}
units: {{resolution: {resolution}, precision: {precision}}}
workflow:
  - {{type: TrafficMatrixPlacement, name: tm, demand_set: d}}
"""
    )


@pytest.mark.parametrize(
    "heads,cap,volume,precision", [(12, 10, 1000, 0.1), (3, 2, 100, 0.5)]
)
def test_automatic_up_to_resolution_outgrows_the_zero_unit_fallback(
    heads, cap, volume, precision
):
    p = prepare(shared_link_up_to_scenario(heads, cap, volume, precision))
    # q=1 cannot give every head one shared-link unit; q=.5 can.
    assert p.topology.q == 0.5
    assert p.units_report.target_met is True
    assert [
        (c.kind, c.incoming_physical, c.basis, c.members, c.q_upper_bound, c.met)
        for c in p.units_report.nominal_splits
    ] == [
        (
            "source",
            Fraction(volume),
            "declared",
            heads,
            Fraction(precision) * volume / (heads - 1),
            True,
        )
    ]
    result = run(p)
    state = result.steps[0].result.cases[0].states["converged"]
    assert state.totals.delivered_units == cap * 2
    assert result.units_report.target_met is True
    assert result.units_report.misses == ()
    (row,) = state.rows
    assert row.result.plan.tunnels_per_head == 1
    assert row.result.plan.max_bandwidth_per_tunnel == 1
    assert row.result.plan.insufficient_resolution is False
    assert len(row.result.plan.heads_with_capacity) == heads


@pytest.mark.parametrize("cap,expected_members", [(0, 0), (10, 256), (1000, 1)])
def test_live_up_to_head_uses_limit_only_without_a_whole_tunnel_unit(
    cap, expected_members
):
    p = prepare(shared_link_up_to_scenario(12, cap, 1000, 0.1, resolution=2))
    answer = capacity(
        p,
        CapacityQuery(
            Selector("^s"),
            Selector("^t$"),
            t2(256, True),
            offer=24,
            design_demand=48,
            workers=1,
        ),
    )
    row = answer.cases[0].states["converged"].rows[0]
    assert row.result.plan.tunnels_per_head == 1
    assert (row.result.plan.max_bandwidth_per_tunnel == 0) == (cap < 1000)
    heads = row.result.plan.heads_with_capacity
    assert len(heads) == (0 if cap == 0 else 12)
    tunnel = [c for c in constraints(answer) if c.kind == "tunnel"]
    expected = []
    if expected_members > 1:
        # Node insertion puts the twelve s nodes before x and t.
        for design, amount in [(False, 24), (True, 48)]:
            for head in range(12):
                expected.append(
                    (
                        "tunnel",
                        "capacity.pair[0]."
                        + ("design." if design else "")
                        + f"head[{head}]",
                        Fraction(amount, 12),
                        "declared",
                        256,
                        Fraction(0.1) * Fraction(amount, 12) / 255,
                        False,
                    )
                )
    assert [constraint_value(c) for c in tunnel] == expected
