"""Static input/count bounds, final validation and fixed prepared reports."""

from dataclasses import dataclass
from fractions import Fraction as F
from pathlib import Path

import netgraph_core as core
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    place,
    prepare,
)
from ngraph.analysis.preparation import StepNeeds
from ngraph.export import project
from ngraph.model.demand import _ParsedModel, _ShortestPathsInput
from ngraph.workflow import MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis


def line(capacity=1):
    net = Network(nodes={n: Node(n) for n in ("s", "t")})
    net.add_link(Link("s", "t", capacity, 1))
    return net


def load(*policies, volume=1, name="d"):
    return DemandSet(
        name,
        tuple(
            DemandSpec(Selector("^s$"), Selector("^t$"), volume, policy)
            for policy in policies
        ),
    )


def bound(*policies, capacity=1, volume=1, precision=0.25, resolution="auto"):
    ds = load(*policies, volume=volume)
    return prepare(
        Scenario(
            line(capacity),
            demand_sets={"d": ds},
            units=UnitsSettings(resolution, precision),
        ),
        demand_sets=("d",),
    )


@pytest.mark.parametrize("requested,q,count", [((), 1 / 16, 3), (("d",), 1 / 32, 6)])
def test_simultaneous_only_and_explicit_library_use(requested, q, count):
    ds = load(
        FlowPolicyPreset.SHORTEST_PATHS_ECMP, FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    step = TrafficMatrixPlacement(demand_set="d", interaction="simultaneous", workers=1)
    p = prepare(
        Scenario(
            line(), [step], demand_sets={"d": ds}, units=UnitsSettings(precision=0.25)
        ),
        demand_sets=requested,
    )
    assert p.topology.q == q
    assert p.units_report.split_bound.count == F(count)
    assert p.units_report.split_bound.group == ("d" if requested else None)
    assert p.units_report.split_bound.demands == (2 if requested else 0)


def test_ordered_and_simultaneous_uses_count_the_set_once():
    ds = load(
        FlowPolicyPreset.SHORTEST_PATHS_ECMP, FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    steps = [
        TrafficMatrixPlacement(
            name=n, demand_set="d", interaction=interaction, workers=1
        )
        for n, interaction in [("lossy", "simultaneous"), ("ordered", "ordered")]
    ]
    p = prepare(
        Scenario(
            line(), steps, demand_sets={"d": ds}, units=UnitsSettings(precision=0.25)
        ),
        demand_sets=("d",),
    )
    assert p.topology.q == 1 / 32
    assert (
        p.units_report.split_bound.group,
        p.units_report.split_bound.demands,
        p.units_report.split_bound.count,
    ) == ("d", 2, F(6))


@pytest.mark.parametrize(
    "policy",
    [
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        _ParsedModel(_ShortestPathsInput()),
        core.FlowPolicyConfig(routing=core.ShortestPaths()),
    ],
)
def test_equal_lossless_declarations_count_expanded_leaves(policy):
    p = bound(policy, policy)
    assert p.topology.q == 1 / 32
    assert p.units_report.split_bound.demands == 2
    assert p.units_report.split_bound.count == F(6)


@pytest.mark.parametrize(
    "policy",
    [
        FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
        FlowPolicyPreset.SHORTEST_PATHS_MAXFLOW,
        FlowPolicyPreset.TE_MAXFLOW_UNLIM,
        core.FlowPolicyConfig(
            routing=core.ShortestPaths(allocation=core.RouteAllocation.WEIGHTED)
        ),
    ],
)
def test_out_of_scope_models_add_no_equal_split_leaves(policy):
    p = bound(policy, policy)
    r = p.units_report
    assert p.topology.q == 1 / 16
    assert (
        r.split_bound.group,
        r.split_bound.demands,
        r.split_bound.tunnels,
        r.split_bound.count,
    ) == (None, 0, 0, F(3))


@pytest.mark.parametrize(
    "resolution,limited,q,target",
    [("auto", "input", 2**-9, True), (1, "declared", 1, False)],
)
def test_input_bound_uses_original_binary64_and_manual_reports_both(
    resolution, limited, q, target
):
    p = bound(
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        capacity=100,
        volume=1.0156,
        precision=0.001,
        resolution=resolution,
    )
    r = p.units_report
    assert (r.q, r.exponent, r.mode, r.precision, r.limited_by, r.target_met) == (
        q,
        -9 if resolution == "auto" else 0,
        "auto" if resolution == "auto" else "manual",
        0.001,
        limited,
        target,
    )
    assert (
        r.input_bound.kind,
        r.input_bound.label,
        r.input_bound.q_upper_bound,
        r.input_bound.met,
    ) == ("input", "demand.d|0.volume", 2 * F(0.001) * F(1.0156), resolution == "auto")
    assert r.achieved_precision == max(F(q) / (2 * F(1.0156)), F(q) * 3 / 100)
    assert r.split_bound.q_upper_bound == F(0.001) * 100 / 3
    assert r.split_bound.met == (resolution == "auto")
    assert r.range_limit is None
    assert p.demand_sets["d"].demands[0].nominal_units == (
        520 if resolution == "auto" else 1
    )


def test_equal_bounds_name_input_and_floor_wins_group_tie():
    net = Network(nodes={n: Node(n) for n in ("s", "t", "u", "v")})
    net.add_link(Link("s", "t", 1, 1))
    net.add_link(Link("u", "v", 1, 1))
    ds = load(FlowPolicyPreset.SHORTEST_PATHS_ECMP, volume=1 / 8)
    p = prepare(
        Scenario(net, demand_sets={"d": ds}, units=UnitsSettings(precision=0.5)),
        demand_sets=("d",),
    )
    r = p.units_report
    assert r.q == 1 / 8 and r.limited_by == "input"
    assert r.input_bound.q_upper_bound == r.split_bound.q_upper_bound == F(1, 8)
    assert (r.split_bound.group, r.split_bound.demands, r.split_bound.tunnels) == (
        None,
        0,
        0,
    )
    assert r.achieved_precision == F(1, 2) and r.target_met
    assert r.input_bound.met is True and r.split_bound.met is True


def test_input_and_group_ties_keep_preparation_order():
    first = load(
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        name="z",
    )
    second = load(
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        name="a",
    )
    steps = [
        MaxFlow(
            name="z",
            model=core.FlowPolicyConfig(
                routing=core.DistributedTE(tunnel_count=core.TunnelCount(1))
            ),
            source=Selector("s"),
            target=Selector("t"),
            offer=1,
            design_demand=1,
            workers=1,
        ),
        TrafficMatrixPlacement(name="active", demand_set="z", workers=1),
    ]
    p = prepare(
        Scenario(line(), steps, demand_sets={"a": second, "z": first}),
        demand_sets=("a", "z"),
    )
    r = p.units_report
    assert r.input_bound.label == "workflow.z.offer"
    assert r.split_bound.capacity_label == "link.s|t|0.capacity"
    assert (r.split_bound.group, r.split_bound.count) == ("z", F(6))
    assert r.scope.workflow_demand_sets == ("z",) and r.scope.library_demand_sets == (
        "a",
        "z",
    )


def test_range_coarsens_after_static_choice_and_records_next_finer_failure():
    net = line(2**41)
    net.add_link(Link("s", "t", 2**41, 1))
    ds = load(FlowPolicyPreset.SHORTEST_PATHS_ECMP, volume=0.001)
    p = prepare(Scenario(net, demand_sets={"d": ds}), demand_sets=("d",))
    r = p.units_report
    assert (r.q, r.limited_by, r.target_met) == (2**-18, "range", False)
    assert (
        r.range_limit.kind,
        r.range_limit.label,
        r.range_limit.tested_q,
        r.range_limit.units_value,
        r.range_limit.exclusive_limit,
        r.range_limit.met,
    ) == (
        "capacity_sum",
        "topology.augmented_capacity_sum",
        2**-19,
        2**62,
        2**62,
        False,
    )
    assert r.augmented_capacity_sum_units == 2**61
    assert r.achieved_precision == F(2**-18) / (2 * F(0.001))
    assert r.input_bound.met is False and r.split_bound.met is True
    assert p.demand_sets["d"].demands[0].nominal_units == 262


def test_resolution_floor_reports_unmet_input_bound():
    p = bound(FlowPolicyPreset.SHORTEST_PATHS_ECMP, volume=2**-40, precision=0.5)
    r = p.units_report
    assert (r.q, r.limited_by, r.achieved_precision, r.target_met) == (
        2**-32,
        "resolution_floor",
        F(128),
        False,
    )
    assert not r.input_bound.met and r.split_bound.met
    assert p.demand_sets["d"].demands[0].nominal_units == 0


@pytest.mark.parametrize("net", [Network(), line(0)])
def test_no_positive_denominators_are_unbounded(net):
    r = prepare(Scenario(net)).units_report
    assert (r.q, r.exponent, r.mode, r.limited_by, r.target_met) == (
        2**32,
        32,
        "auto",
        "unbounded",
        True,
    )
    assert (
        r.input_bound is r.split_bound is r.range_limit is r.achieved_precision is None
    )
    assert r.augmented_capacity_sum_units == 0 and r.weight_approximations == ()


def test_disabled_capacity_still_sets_the_bound_and_count():
    net = line(100)
    net.add_link(Link("s", "t", 1, 1, disabled=True))
    r = prepare(Scenario(net)).units_report
    assert (
        r.q,
        r.split_bound.capacity,
        r.split_bound.nodes,
        r.split_bound.directed_links,
        r.split_bound.count,
    ) == (2**-12, 1.0, 2, 4, F(7, 2))
    assert r.split_bound.capacity_label == "link.s|t|1.capacity"


@pytest.mark.parametrize("q", [2**-32, 2**32])
def test_manual_endpoints_keep_declared_reason(q):
    r = prepare(Scenario(Network(), units=UnitsSettings(q))).units_report
    assert r.q == q and r.limited_by == "declared" and r.mode == "manual"
    assert r.target_met and r.achieved_precision is None


def test_manual_and_exhausted_range_refusals_have_legal_controls():
    with pytest.raises(
        ValueError,
        match="topology.augmented_capacity_sum: no legal resolution represents the complete prepared input/augmented graph",
    ):
        prepare(Scenario(line(2**61), units=UnitsSettings(1)))
    assert (
        prepare(
            Scenario(line(2**61), units=UnitsSettings(2))
        ).units_report.augmented_capacity_sum_units
        == 2**61
    )
    with pytest.raises(
        ValueError,
        match="no legal resolution represents the complete prepared input/augmented graph",
    ):
        prepare(Scenario(line(2**95)))
    assert prepare(Scenario(line())).topology.q == 2**-12


@pytest.mark.parametrize(
    "value", [True, False, 0, -1, 0.50001, float("inf"), float("nan"), "0.1"]
)
def test_precision_refusal_is_complete_and_has_endpoint_control(value):
    with pytest.raises(ValueError) as error:
        UnitsSettings(precision=value)
    assert (
        str(error.value)
        == f"units.precision: expected a number greater than 0 and at most 0.5, got {value!r}"
    )
    assert UnitsSettings(precision=0.5).precision == 0.5


def test_one_final_compile_and_masked_capacity_validation(monkeypatch):
    import ngraph.analysis.preparation as module

    compiled = []
    evaluated = []
    original_compile = module.compile_topology
    original_evaluate = module.evaluate

    def compile(*args, **kwargs):
        compiled.append(args[1])
        return original_compile(*args, **kwargs)

    def evaluate(topology, query, pairs, options, workers):
        evaluated.append(
            (tuple(pairs), options.eligibility.node_allowed().tolist(), workers)
        )
        return original_evaluate(topology, query, pairs, options, workers)

    monkeypatch.setattr(module, "compile_topology", compile)
    monkeypatch.setattr(module, "evaluate", evaluate)
    step = MaxFlow(
        name="cap",
        source=Selector("s"),
        target=Selector("t"),
        model=core.FlowPolicyConfig(routing=core.ShortestPaths()),
        workers=1,
    )
    p = prepare(Scenario(line(100), [step]))
    assert compiled == [p.topology.q] and len(evaluated) == 1
    assert evaluated[0][1:] == ([False, False], 1)
    assert (
        capacity(p, step.query(p)).cases[0].states["converged"].rows[0].result.delivered
        * p.topology.q
        == 100
    )


def test_capacity_validation_retains_full_workflow_refusal_and_cause():
    def scenario(weights):
        config = core.FlowPolicyConfig(
            routing=core.ShortestPaths(
                allocation=core.RouteAllocation.WEIGHTED,
                weight_basis=core.WeightBasis.EXPLICIT,
                edge_weights=weights,
            )
        )
        return Scenario(
            line(100),
            [
                MaxFlow(
                    name="cap",
                    source=Selector("s"),
                    target=Selector("t"),
                    model=config,
                    workers=1,
                )
            ],
        )

    with pytest.raises(ValueError) as error:
        prepare(scenario([1]))
    assert (
        str(error.value) == "workflow[0] (name 'cap'): edge_weights: expected 2 entries"
    )
    assert type(error.value.__cause__) is ValueError
    p = prepare(scenario([1, 1]))
    result = capacity(p, p.scenario.workflow[0].query(p))
    assert (
        result.cases[0].states["converged"].rows[0].result.delivered * p.topology.q
        == 100
    )


def test_custom_capacity_callback_runs_only_after_final_compile(monkeypatch):
    calls = []

    @dataclass
    class Opaque(MaxFlow):
        def needs(self):
            def query(p):
                calls.append(p.topology.q)
                return CapacityQuery(Selector("s"), Selector("t"), workers=1)

            return StepNeeds(numerical=True, capacity=query)

    p = prepare(Scenario(line(), [Opaque(name="opaque")]))
    assert calls == [p.topology.q]
    assert p.units_report.split_bound.group is None


def test_builtin_subclass_does_not_publish_its_unknown_tunnel_count():
    class CustomMaxFlow(MaxFlow):
        pass

    fields = dict(
        name="cap",
        source=Selector("s"),
        target=Selector("t"),
        preset=FlowPolicyPreset.TE_ECMP_16_LSP,
        workers=1,
    )
    builtin = prepare(
        Scenario(line(), [MaxFlow(**fields)], units=UnitsSettings(precision=0.5))
    )
    custom = prepare(
        Scenario(line(), [CustomMaxFlow(**fields)], units=UnitsSettings(precision=0.5))
    )
    assert (builtin.units_report.split_bound.tunnels, builtin.topology.q) == (
        16,
        1 / 64,
    )
    assert (custom.units_report.split_bound.tunnels, custom.topology.q) == (0, 1 / 8)


@pytest.mark.parametrize(
    "pooled,tunnels,count,q",
    [(False, 32, F(143, 4), 1 / 128), (True, 16, F(79, 4), 1 / 64)],
)
def test_capacity_tunnels_count_heads_from_the_selected_sources(
    pooled, tunnels, count, q
):
    net = Network(nodes={n: Node(n) for n in ("s1", "s2", "t")})
    for source in ("s1", "s2"):
        net.add_link(Link(source, "t", 1, 1))
    policy = (
        {"preset": FlowPolicyPreset.TE_ECMP_16_LSP}
        if pooled
        else {
            "model": core.FlowPolicyConfig(
                routing=core.CentralizedTE(
                    source_allocation=core.SourceAllocation.EQUAL,
                    tunnel_count=core.TunnelCount(16),
                )
            )
        }
    )
    p = prepare(
        Scenario(
            net,
            [
                MaxFlow(
                    name="cap",
                    source=Selector("^s"),
                    target=Selector("^t$"),
                    mode="combine",
                    workers=1,
                    **policy,
                )
            ],
            units=UnitsSettings(precision=0.5),
        )
    )
    b = p.units_report.split_bound
    # Three nodes and four directed physical edges: floor = 7/4 + 2.
    assert (b.nodes, b.directed_links, b.group, b.demands, b.tunnels, b.count) == (
        3,
        4,
        "workflow.cap",
        0,
        tunnels,
        count,
    )
    assert p.topology.q == q


def test_count_question_validates_late_graph_support_during_preparation():
    from dataclasses import replace

    from ngraph import run
    from ngraph.analysis.programs import dag_from_edges

    other = prepare(Scenario(line(), units=UnitsSettings(1)))

    def scenario(foreign):
        class LateCount(TunnelCountAnalysis):
            def query(self, prepared):
                graph = other.topology.graph if foreign else prepared.topology.graph
                config = core.FlowPolicyConfig(
                    routing=core.CentralizedTE(
                        source_allocation=core.SourceAllocation.EQUAL,
                        tunnel_count=core.TunnelCount(1),
                        support=dag_from_edges(graph, [0]),
                    )
                )
                ds = prepared.demand_sets[self.demand_set]
                return self.query_for(
                    replace(
                        ds, demands=tuple(replace(d, config=config) for d in ds.demands)
                    )
                )

        return Scenario(
            line(),
            [
                LateCount(
                    name="counts",
                    demand_set="d",
                    counts=(1,),
                    design_demand=1,
                    offer=1,
                    workers=1,
                )
            ],
            demand_sets={
                "d": load(
                    core.FlowPolicyConfig(
                        routing=core.CentralizedTE(
                            source_allocation=core.SourceAllocation.EQUAL,
                            tunnel_count=core.TunnelCount(1),
                        )
                    )
                )
            },
            units=UnitsSettings(1),
        )

    valid = prepare(scenario(False))
    assert run(valid).steps[0].result.rows[0].result.delivered == 1
    with pytest.raises(ValueError) as error:
        prepare(scenario(True))
    assert (
        str(error.value)
        == "workflow[0] (name 'counts'): support belongs to another graph"
    )
    assert type(error.value.__cause__) is ValueError


def test_count_rows_use_declared_maximum_and_masked_native_validation(monkeypatch):
    # The declared set contributes one tunnel; the count question contributes 16.
    config = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(1),
        )
    )
    ds = load(config)
    step = TunnelCountAnalysis(
        name="counts",
        demand_set="d",
        counts=(2, 4),
        up_to=16,
        design_demand=1,
        offer=1,
        workers=1,
    )
    validations = []
    original = core.evaluate_pairs

    def evaluated(graph, pairs, options, **kwargs):
        if options.eligibility is not None and not any(
            options.eligibility.node_allowed()
        ):
            count = getattr(options.config.routing, "tunnel_count", None)
            validations.append(
                (
                    count.per_head if count is not None else None,
                    tuple(pairs),
                    kwargs.get("workers"),
                )
            )
        return original(graph, pairs, options, **kwargs)

    monkeypatch.setattr(core, "evaluate_pairs", evaluated)
    p = prepare(
        Scenario(
            line(), [step], demand_sets={"d": ds}, units=UnitsSettings(precision=0.5)
        )
    )
    assert p.topology.q == 1 / 64
    assert (
        p.units_report.split_bound.group,
        p.units_report.split_bound.count,
        p.units_report.split_bound.tunnels,
    ) == ("workflow.counts", F(19), 16)
    assert [n for n, _, _ in validations if n in (2, 4, 16)] == [2, 4, 16]
    assert all(workers == 1 for _, _, workers in validations)


def test_later_small_offer_keeps_prepared_report():
    p = prepare(Scenario(line(100)))
    assert p.topology.q == 1 / 32
    r = capacity(
        p, CapacityQuery(Selector("s"), Selector("t"), offer=1 / 128, workers=1)
    )
    assert r.cases[0].states["converged"].rows[0].result.delivered == 0
    assert r.units_report is p.units_report


def test_readme_and_square_mesh_hand_values():
    cases = [
        ("readme_example.yml", -9, F(14), F(7, 12800), 48),
        ("square_mesh.yaml", -17, F(72), F(9, 16384), 16),
    ]
    for name, exponent, count, achieved, L in cases:
        p = prepare(Scenario.from_yaml((Path("scenarios") / name).read_text()))
        r = p.units_report
        assert (r.exponent, r.limited_by, r.achieved_precision, r.target_met) == (
            exponent,
            "split_count",
            achieved,
            True,
        )
        assert r.split_bound.count == count
        assert r.split_bound.nodes + r.split_bound.directed_links == L
        assert p.topology.graph.num_nodes() + p.topology.graph.num_edges() == L
        assert project(r)["split_bound"]["count"] == {
            "numerator": count.numerator,
            "denominator": count.denominator,
        }


def test_fifty_source_merge_delivery_and_msd():
    from ngraph import MSDQuery, maximum_supported_demand

    names = [f"S{i:02d}" for i in range(50)]
    net = Network(nodes={name: Node(name) for name in [*names, "X1", "X2", "X3", "T"]})
    for source in names:
        for spine in ("X1", "X2", "X3"):
            net.add_link(Link(source, spine, 1000, 1))
    for spine in ("X1", "X2", "X3"):
        net.add_link(Link(spine, "T", 1, 1))
    ds = DemandSet("d", (DemandSpec(Selector("^S"), Selector("^T$"), 100),))
    p = prepare(Scenario(net, demand_sets={"d": ds}), demand_sets=("d",))
    r = p.units_report
    assert (
        r.q,
        r.split_bound.nodes,
        r.split_bound.directed_links,
        r.split_bound.count,
        r.achieved_precision,
    ) == (2**-17, 54, 306, F(92), F(23, 32768))
    result = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    delivered = result.cases[0].states["converged"].rows[0].result.delivered
    # 22 sources at 7864 and 28 at 7863 place exactly 131072 units on each
    # first spine; a 23rd larger share would overflow. This is one direct
    # lossless shared equal-DAG demand on positive original capacities.
    assert delivered == 50 * 7863 + 22 == 393172
    assert abs(F(delivered) * F(r.q) - 3) <= F(r.precision) * 3
    msd = maximum_supported_demand(
        p, MSDQuery(p.demand_sets["d"], alpha_tolerance=0.0001)
    )
    assert F(msd.alpha_feasible.value) == F(491, 16384)


@pytest.mark.parametrize(
    "q,expected,achieved", [("auto", 32769, F(7, 8192)), (1, 9, F(7, 2))]
)
def test_shared_route_delivery_and_declared_coarse_unit(q, expected, achieved):
    net = Network(nodes={n: Node(n) for n in ("A", "B", "C", "X", "Y", "D")})
    for source, target, amount, cost in (
        ("A", "B", 100, 1),
        ("B", "D", 100, 2),
        ("A", "C", 100, 1),
        ("C", "X", 2, 1),
        ("C", "Y", 100, 1),
        ("X", "D", 100, 1),
        ("Y", "D", 100, 1),
    ):
        net.add_link(Link(source, target, amount, cost))
    ds = DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^D$"), 12),))
    p = prepare(
        Scenario(net, demand_sets={"d": ds}, units=UnitsSettings(q)), demand_sets=("d",)
    )
    r = p.units_report
    assert (r.q, r.limited_by, r.achieved_precision, r.target_met) == (
        2**-12 if q == "auto" else 1,
        "split_count" if q == "auto" else "declared",
        achieved,
        q == "auto",
    )
    result = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert result.cases[0].states["converged"].rows[0].result.delivered == expected
    if q == "auto":
        # I=32769 gives C floor(I/2)=16384 and X ceil(C/2)=8192, exactly
        # the rounded capacity. I+1 would give X 8193. All theorem premises hold.
        assert abs(F(expected) * F(r.q) - 8) <= F(r.precision) * 8


def test_tunnel_setup_is_a_discrete_observed_answer():
    net = line(6)
    net.add_link(Link("s", "t", 4, 1))
    config = core.FlowPolicyConfig(routing=core.DistributedTE(core.TunnelCount(2)))
    ds = load(config, volume=8 + 2**-12)
    p = prepare(Scenario(net, demand_sets={"d": ds}), demand_sets=("d",))
    assert (p.topology.q, p.units_report.split_bound.count) == (2**-11, F(11, 2))
    result = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert result.cases[0].states["converged"].rows[0].result.delivered == 16385
    # Exact setup asks each tunnel for 4+2^-13 and retains only the capacity-6
    # path. The whole-unit result is an observation, outside the delivery theorem.


def test_declared_heads_times_tunnels_avoid_zero_delivery_at_small_target():
    sources = [f"S{i:02d}" for i in range(12)]
    net = Network(nodes={name: Node(name) for name in ("H", "T", *sources)})
    for source in sources:
        net.add_link(Link(source, "H", 1000, 1))
    net.add_link(Link("H", "T", 10, 1))
    config = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(16),
        )
    )
    ds = DemandSet("d", (DemandSpec(Selector("^S"), Selector("^T$"), 1000, config),))
    p = prepare(
        Scenario(net, demand_sets={"d": ds}, units=UnitsSettings(precision=0.1)),
        demand_sets=("d",),
    )
    r = p.units_report
    assert (
        r.q,
        r.split_bound.nodes,
        r.split_bound.directed_links,
        r.split_bound.tunnels,
        r.split_bound.count,
    ) == (2**-8, 14, 26, 192, F(204))
    result = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert result.cases[0].states["converged"].rows[0].result.delivered == 2560


def test_zero_capacity_member_has_no_relative_delivery_promise():
    net = line(5)
    net.add_link(Link("s", "t", 0, 1))
    ds = load(FlowPolicyPreset.SHORTEST_PATHS_ECMP, volume=5)
    p = prepare(Scenario(net, demand_sets={"d": ds}), demand_sets=("d",))
    assert p.topology.q == 2**-10 and p.units_report.target_met
    result = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert result.cases[0].states["converged"].rows[0].result.delivered == 1


def test_ordered_residual_is_an_observation_outside_single_demand_theorem():
    ds = DemandSet(
        "d",
        tuple(
            DemandSpec(Selector("^s$"), Selector("^t$"), amount)
            for amount in (9.9999, 10)
        ),
    )
    p = prepare(Scenario(line(10), demand_sets={"d": ds}), demand_sets=("d",))
    assert p.topology.q == 2**-10 and p.units_report.split_bound.count == F(6)
    result = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert [
        row.result.delivered for row in result.cases[0].states["converged"].rows
    ] == [10240, 0]


def test_uncapped_optimized_flow_is_exact_on_rounded_capacities():
    step = MaxFlow(name="flow", source=Selector("s"), target=Selector("t"), workers=1)
    p = prepare(Scenario(line(1.00015), [step]))
    assert p.topology.q == 2**-12
    result = capacity(p, step.query(p))
    assert result.cases[0].states["converged"].rows[0].result.delivered == 4097


def test_power_selection_keeps_the_exact_binary64_ratio_bound():
    # binary64(1/3) * 3 is exactly 1 - 2^-54; rounding the bound to float
    # would admit q=1. The exact comparison requires q=1/2 and three units.
    p = bound(
        FlowPolicyPreset.SHORTEST_PATHS_ECMP, capacity=100, volume=1.5, precision=1 / 3
    )
    r = p.units_report
    assert r.input_bound.q_upper_bound == F(2**54 - 1, 2**54)
    assert (r.q, r.limited_by, r.target_met, r.input_bound.met, r.split_bound.met) == (
        0.5,
        "input",
        True,
        True,
        True,
    )
    assert r.achieved_precision == F(1, 6)
    rows = (
        place(p, PlacementQuery(p.demand_sets["d"], workers=1))
        .cases[0]
        .states["converged"]
        .rows
    )
    assert rows[0].result.delivered == 3
    assert rows[0].result.delivered * r.q == 1.5


def two_sources():
    net = Network(nodes={n: Node(n) for n in "abc"})
    for source in "ab":
        net.add_link(Link(source, "c", 1, 1))
    return net


def test_pooled_set_and_count_rows_have_one_tunnel_head():
    # L=7, floor=15/4. A pooled set has t=16, Gamma=79/4; the count
    # question has t=20, Gamma=95/4. Both select q=1/64 at p=1/2.
    ds = DemandSet(
        "d",
        (
            DemandSpec(
                Selector("^[ab]$"), Selector("^c$"), 1, FlowPolicyPreset.TE_ECMP_16_LSP
            ),
        ),
    )
    for steps, requested, group, count, tunnels in [
        ([], ("d",), "d", F(79, 4), 16),
        (
            [
                TunnelCountAnalysis(
                    name="tc",
                    demand_set="d",
                    counts=(1,),
                    up_to=20,
                    design_demand=1,
                    offer=1,
                    workers=1,
                )
            ],
            (),
            "workflow.tc",
            F(95, 4),
            20,
        ),
    ]:
        p = prepare(
            Scenario(
                two_sources(),
                steps,
                demand_sets={"d": ds},
                units=UnitsSettings(precision=0.5),
            ),
            demand_sets=requested,
        )
        b = p.units_report.split_bound
        assert (
            p.topology.q,
            b.nodes,
            b.directed_links,
            b.group,
            b.count,
            b.tunnels,
            b.demands,
        ) == (1 / 64, 3, 4, group, count, tunnels, 0)


def test_each_capacity_pair_forms_its_own_count_group():
    # Two singleton pairs each have t=16, not a combined t=32.
    step = MaxFlow(
        name="mf",
        source=Selector("^(a|b)$"),
        target=Selector("^c$"),
        mode="pairwise",
        preset=FlowPolicyPreset.TE_ECMP_16_LSP,
        workers=1,
    )
    p = prepare(Scenario(two_sources(), [step], units=UnitsSettings(precision=0.5)))
    b = p.units_report.split_bound
    assert (p.topology.q, b.group, b.count, b.demands, b.tunnels) == (
        1 / 64,
        "workflow.mf",
        F(79, 4),
        0,
        16,
    )


def test_explicit_equal_source_allocation_counts_like_the_default():
    # Pairwise expansion makes two ECMP leaves: Gamma=2*(15/4), q=1/16.
    policy = _ParsedModel(
        _ShortestPathsInput(source_allocation=core.SourceAllocation.EQUAL)
    )
    ds = DemandSet(
        "e",
        (DemandSpec(Selector("^[ab]$"), Selector("^c$"), 1, policy, mode="pairwise"),),
    )
    p = prepare(
        Scenario(
            two_sources(), demand_sets={"e": ds}, units=UnitsSettings(precision=0.5)
        ),
        demand_sets=("e",),
    )
    b = p.units_report.split_bound
    assert (p.topology.q, b.group, b.count, b.demands, b.tunnels) == (
        1 / 16,
        "e",
        F(15, 2),
        2,
        0,
    )


def test_a_declaration_selecting_no_source_adds_no_leaf():
    ds = DemandSet(
        "f",
        (
            DemandSpec(Selector("^a$"), Selector("^c$"), 1),
            DemandSpec(Selector("^nothing$"), Selector("^c$"), 1),
        ),
    )
    p = prepare(
        Scenario(
            two_sources(), demand_sets={"f": ds}, units=UnitsSettings(precision=0.5)
        ),
        demand_sets=("f",),
    )
    b = p.units_report.split_bound
    assert (p.topology.q, b.group, b.count, b.demands, b.tunnels) == (
        1 / 8,
        None,
        F(15, 4),
        0,
        0,
    )


def test_resolution_floor_when_the_input_bound_is_just_below_it():
    # 2*p*v = 3*2^-34 lies strictly between half the minimum q and q.
    p = bound(FlowPolicyPreset.SHORTEST_PATHS_ECMP, volume=3 * 2.0**-34, precision=0.5)
    r = p.units_report
    assert (
        r.q,
        r.limited_by,
        r.input_bound.q_upper_bound,
        r.input_bound.met,
        r.target_met,
    ) == (2.0**-32, "resolution_floor", F(3, 2**34), False, False)


def boundary_document(q, volume=1, capacity=100, routing=None):
    demand = dict(source="^S$", target="^T$", volume=volume)
    if routing:
        demand["model"] = dict(routing=routing)
    else:
        demand["preset"] = "SHORTEST_PATHS_ECMP"
    return dict(
        units=dict(resolution=q),
        network=dict(
            nodes={"S": {}, "T": {}},
            links=[dict(source="S", target="T", capacity=capacity)],
        ),
        demands={"d": [demand]},
        workflow=[
            dict(type="TrafficMatrixPlacement", name="p", demand_set="d", workers=1)
        ],
    )


def boundary_run(doc):
    import yaml

    from ngraph import run

    p = prepare(Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False)))
    assert p.topology.q == doc["units"]["resolution"]
    return p, run(p)


def boundary_rows(result):
    return result.steps[0].result.cases[0].states["converged"].rows


def test_expanded_parent_rounding_is_distinct_from_direct_leaf_conversion():
    doc = boundary_document(1 / 8)
    doc["units"]["precision"] = 0.1
    doc["network"] = dict(
        nodes={n: {} for n in [*(f"S{i}" for i in range(6)), "T"]},
        links=[dict(source=f"S{i}", target="T", capacity=1000) for i in range(6)],
    )
    doc["demands"]["d"][0].update(source="^S", mode="pairwise")
    _, result = boundary_run(doc)
    units = tuple(r.result.delivered for r in boundary_rows(result))
    # Eight rounded parent units are apportioned over six independent pairs.
    assert units == (2, 2, 1, 1, 1, 1)
    assert F(units[0], 8) - F(1, 6) == F(1, 12) > F(1, 16)


def test_scaled_product_conversion_does_not_cover_binary64_multiplication():
    alpha = float(1 - F(1, 2**28) + F(1, 2**53))
    doc = boundary_document(2**-31, 2**28 + 1, 2**28 + 1)
    doc["units"]["precision"] = 2**-57
    doc["workflow"][0]["alpha"] = alpha
    p, result = boundary_run(doc)
    physical = F(boundary_rows(result)[0].result.delivered) * F(p.topology.q)
    assert physical == 2**28
    assert abs(F(alpha * float(2**28 + 1)) - physical) == 0
    exact = F(alpha) * (2**28 + 1)
    assert exact - physical == F(234881025, 2**53)
    assert exact - physical > F(2**-57) * exact + F(p.topology.q) / 2


def test_many_rounded_requests_change_the_later_residual():
    doc = boundary_document(2**-16, capacity=10)
    doc["network"]["nodes"].update(U={}, V={})
    doc["network"]["links"].append(dict(source="U", target="V", capacity=1))
    prior = dict(
        source="^S$", target="^T$", volume=1051 / 131072, preset="TE_MAXFLOW_UNLIM"
    )
    doc["demands"]["d"] = [dict(prior) for _ in range(1000)] + [
        dict(source="^S$", target="^T$", volume=10, preset="SHORTEST_PATHS_ECMP")
    ]
    p, result = boundary_run(doc)
    units = [r.result.delivered for r in boundary_rows(result)]
    assert units[:-1] == [526] * 1000
    assert units[-1] == 129360
    proportional_units = (F(10) - 1000 * F(1051, 131072)) / F(p.topology.q)
    assert proportional_units == 129860
    assert proportional_units - units[-1] == 500


def test_declared_finite_maxflow_offer_is_not_the_uncapped_maximum():
    doc = boundary_document(2**-9)
    del doc["demands"]
    doc["workflow"] = [
        dict(type="MaxFlow", name="cap", source="^S$", target="^T$", offer=1, workers=1)
    ]
    p, result = boundary_run(doc)
    assert boundary_rows(result)[0].result.delivered == 512
    uncapped = capacity(p, CapacityQuery(Selector("^S$"), Selector("^T$"), workers=1))
    assert uncapped.cases[0].states["converged"].rows[0].result.delivered == 51200


def test_a_later_count_can_exceed_the_prepared_tunnel_size():
    from ngraph import TunnelCountQuery, tunnel_counts

    doc = boundary_document(
        1 / 8,
        capacity=1,
        routing=dict(
            type="centralized_te",
            source_allocation="equal",
            tunnel_count=dict(per_head=1),
        ),
    )
    doc["units"]["precision"] = 0.5
    p, result = boundary_run(doc)
    later = tunnel_counts(
        p,
        TunnelCountQuery(
            p.demand_sets["d"], (16,), design_demand=2, offer=2, workers=1
        ),
    )
    assert boundary_rows(result)[0].result.plan.max_bandwidth_per_tunnel == 8
    assert later.rows[0].result.plan.max_bandwidth_per_tunnel == 0


def test_repeated_supplied_dags_retain_separate_rounding():
    from ngraph.analysis.programs import dag_from_edges

    q = 2**-14
    net = Network(nodes={n: Node(n) for n in "abcd"})
    for destination in "bc":
        for _ in range(10):
            net.add_link(Link("a", destination, 100, 1))
    net.add_link(Link("b", "d", 1, 1))
    net.add_link(Link("c", "d", 100, 1))
    p = prepare(Scenario(net, units=UnitsSettings(q)))
    t = p.topology
    dag = dag_from_edges(
        t.graph,
        [i for ref, i in t._edge_id_by_ref.items() if ref.direction == "forward"],
    )
    source, destination = t.node_id_by_name["a"], t.node_id_by_name["d"]
    program = core.ForwardingProgram.from_routes(
        t.graph,
        source,
        destination,
        [core.RouteDefinition(source, dag) for _ in range(100)],
    )
    result = capacity(
        p,
        CapacityQuery(
            Selector("^a$"),
            Selector("^d$"),
            core.FlowPolicyConfig(routing=core.Pinned(program)),
            offer=20,
            workers=1,
        ),
    )
    delivered = result.cases[0].states["converged"].rows[0].result.delivered
    # Half of proportional traffic crosses capacity one: fluid delivery is two.
    assert F(delivered) * F(q) == F(253, 128)
    assert F(2) - F(delivered) * F(q) == F(3, 128)


def test_lossy_weighted_delivery_has_no_equal_split_certificate():
    offer = 24458019
    net = line(2 * offer)
    for _ in range(19):
        net.add_link(Link("s", "t", 24000.5, 1))
    p = prepare(Scenario(net, units=UnitsSettings(1)))
    weights = [0] * p.topology.graph.num_edges()
    for ref, i in p.topology._edge_id_by_ref.items():
        weights[i] = 1000 if ref.link == "s|t|0" else 1
    config = core.FlowPolicyConfig(
        routing=core.ShortestPaths(
            allocation=core.RouteAllocation.WEIGHTED,
            weight_basis=core.WeightBasis.EXPLICIT,
            edge_weights=weights,
        ),
        admission=core.Admission.LOSSY,
    )
    result = capacity(
        p,
        CapacityQuery(Selector("^s$"), Selector("^t$"), config, offer=offer, workers=1),
    )
    delivered = result.cases[0].states["converged"].rows[0].result.delivered
    assert delivered == 24458019
    proportional = F(offer * 1000, 1019) + 19 * F(48001, 2)
    assert delivered - proportional == F(57361, 2038)


def test_lossy_simultaneous_sharing_is_integer_apportionment():
    doc = boundary_document(1, capacity=3)
    doc["demands"]["d"] = [
        dict(source="^S$", target="^T$", volume=v) for v in (5, 1, 1)
    ]
    doc["workflow"][0]["interaction"] = "simultaneous"
    _, result = boundary_run(doc)
    delivered = tuple(r.result.delivered for r in boundary_rows(result))
    assert delivered == (3, 0, 0)
    assert tuple(
        F(a) - F(3 * v, 7) for a, v in zip(delivered, (5, 1, 1), strict=True)
    ) == (F(6, 7), F(-3, 7), F(-3, 7))


def test_controller_weights_change_when_the_graph_quantum_changes():
    actual = []
    for q in (1, 1 / 1024):
        doc = boundary_document(q, 40)
        doc["network"] = dict(
            nodes={n: {} for n in ("S", "X1", "X2", "T")},
            links=[
                dict(source=s, target=t, capacity=c)
                for s, t, c in [
                    ("S", "X1", 100),
                    ("S", "X2", 100),
                    ("X1", "T", 30.0007),
                    ("X2", "T", 10),
                ]
            ],
        )
        doc["demands"]["d"][0]["preset"] = "SHORTEST_PATHS_WCMP"
        doc["routing"] = dict(igp_domain=dict(path="^X"), bgp_edge=dict(path="^(S|T)$"))
        doc["wcmp_controller"] = dict(scope="next_hop")
        p, _ = boundary_run(doc)
        actual.append(
            tuple(
                m.weight for m in p.demand_sets["d"].controller[0].programmed[0].members
            )
        )
    assert actual == [(3, 1), (30721, 10240)]


def test_msd_limit_stops_before_the_proportional_threshold():
    doc = boundary_document(1 / 512, capacity=10)
    doc["workflow"] = [
        dict(
            type="MaximumSupportedDemand",
            name="m",
            demand_set="d",
            alpha_max=1,
        )
    ]
    _, result = boundary_run(doc)
    answer = result.steps[0].result
    assert (F(answer.alpha_feasible.value), answer.search_status) == (F(1), "limit")
    assert F(10) / F(doc["demands"]["d"][0]["volume"]) == 10
