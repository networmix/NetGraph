"""A live native tunnel plan with no whole-unit size misses precision."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from typing import get_type_hints

import jsonschema
import netgraph_core as core
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    FlowPolicyPreset,
    Link,
    MSDQuery,
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
    maximum_supported_demand,
    place,
    prepare,
    run,
    tunnel_counts,
)
from ngraph.analysis.counts import count_splits
from ngraph.analysis.precision import query_splits
from ngraph.analysis.programs import dag_from_edges
from ngraph.export import project as record_wire
from ngraph.workflow import MaxFlow, TunnelCountAnalysis
from tests.results.test_analysis_wire import SCHEMA, project


def config(count=16, up_to=False, t1=False, admission=core.Admission.LOSSY):
    tunnels = core.TunnelCount(count, up_to=up_to)
    routing = (
        core.DistributedTE(tunnels)
        if t1
        else core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL, tunnel_count=tunnels
        )
    )
    return core.FlowPolicyConfig(routing=routing, admission=admission)


def scenario(
    heads=12,
    cap=10,
    volume=1000,
    count=16,
    q=0.5,
    up_to=False,
    t1=False,
    pooled=False,
    parallel=False,
    huge=False,
):
    network = Network(
        nodes={
            name: Node(name) for name in (*(f"s{i}" for i in range(heads)), "x", "t")
        }
    )
    for i in range(heads):
        network.add_link(Link(f"s{i}", "x", 1000))
    network.add_link(Link("x", "t", cap / 2 if parallel else cap))
    if parallel:
        network.add_link(Link("x", "t", cap / 2))
    if huge:
        network.add_node(Node("u"))
        network.add_node(Node("v"))
        network.add_link(Link("u", "v", float(2**61)))
    model = FlowPolicyPreset.TE_ECMP_16_LSP if pooled else config(count, up_to, t1)
    demands = DemandSet(
        "d", (DemandSpec(Selector("^s"), Selector("^t$"), volume, model),)
    )
    return Scenario(network, demand_sets={"d": demands}, units=UnitsSettings(q, 0.1))


def prepared(**kwargs):
    return prepare(scenario(**kwargs), demand_sets=("d",))


def two_stars(capacities=(10, 10), q=0.5):
    names = [
        name
        for prefix in ("a", "b")
        for name in (*(f"{prefix}{i}" for i in range(12)), f"x{prefix}", f"t{prefix}")
    ]
    network = Network(nodes={name: Node(name) for name in names})
    for prefix, cap in zip(("a", "b"), capacities, strict=True):
        for i in range(12):
            network.add_link(Link(f"{prefix}{i}", f"x{prefix}", 1000))
        network.add_link(Link(f"x{prefix}", f"t{prefix}", cap))
    demands = DemandSet(
        "d",
        tuple(
            DemandSpec(
                Selector(f"^{prefix}\\d"), Selector(f"^t{prefix}$"), 1000, config()
            )
            for prefix in ("a", "b")
        ),
    )
    return Scenario(network, demand_sets={"d": demands}, units=UnitsSettings(q, 0.1))


def causes(constraints):
    return [record_wire(c) for c in constraints if c.kind == "tunnel_resolution"]


def missed(answer):
    return causes(c for miss in answer.misses for c in miss.constraints)


def expected(label="demand.d|0|0", q=0.5, heads=None):
    return {
        "kind": "tunnel_resolution",
        "label": label,
        "q": q,
        "heads": sorted(f"s{i}" for i in range(12)) if heads is None else heads,
        "met": False,
    }


def first_result(answer):
    return answer.cases[0].states["converged"].rows[0].result


def test_manual_and_automatic_resolution_observe_the_shared_link(monkeypatch):
    # 12*16=192 paths need one unit each on the shared link. At q=.5
    # its20 units fail; at1/16 its160 fail; at1/32 its320 fit.
    import ngraph.analysis.preparation as preparation

    original = preparation._nominal_splits
    seen = []

    def observe(p, demands, precision):
        seen.append(p.topology.q)
        return original(p, demands, precision)

    monkeypatch.setattr(preparation, "_nominal_splits", observe)
    p = prepared()
    assert p.units_report.target_met is False
    assert causes(p.units_report.binding_constraints) == [expected()]
    assert p.units_report.nominal_split_count == 13
    assert len(p.units_report.nominal_splits) == 13
    assert all(c.met for c in p.units_report.nominal_splits)
    assert p.units_report.inexact_inputs == p.units_report.zeroed_inputs == 0
    a = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert missed(a) == [expected()]
    assert first_result(a).delivered == 0
    assert first_result(a).plan.max_fractional_bandwidth_per_tunnel == Fraction(5, 48)
    assert project(run(p))["units_report"]["binding_constraints"][-1] == expected()
    seen.clear()
    fine = prepared(q="auto")
    assert seen == [2, 1, 0.5, 0.25, 0.125, 0.0625, 0.03125]
    assert fine.topology.q == 1 / 32
    assert fine.units_report.target_met is True
    assert causes(fine.units_report.binding_constraints) == [expected(q=1 / 16)]
    assert fine.units_report.nominal_split_count == 13
    assert fine.units_report.misses == ()
    from tests.typing.valid_client import read_units

    assert read_units(fine.units_report) == 1 / 32
    assert project(run(fine))["units_report"]["binding_constraints"] == [
        expected(q=1 / 16)
    ]
    answer = place(fine, PlacementQuery(fine.demand_sets["d"], workers=1))
    assert missed(answer) == []
    assert answer.units_report.target_met is True
    assert first_result(answer).plan.max_bandwidth_per_tunnel == 1
    assert first_result(answer).delivered == 320  # physical10


def test_workflow_capacity_preparation_checks_each_existing_plan(monkeypatch):
    s = scenario()
    step = MaxFlow(
        name="cap",
        source=Selector("^s"),
        target=Selector("^t$"),
        model=config(),
        offer=1000,
        design_demand=1000,
        workers=1,
    )
    calls = []
    original = core.evaluate_demand

    def evaluate(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(core, "evaluate_demand", evaluate)
    p = prepare(replace(s, workflow=(step,), demand_sets={}))
    assert causes(p.units_report.binding_constraints) == [
        expected("workflow.cap.pair[0]")
    ]
    assert p.units_report.target_met is False
    assert len(calls) == 1
    calls.clear()
    fine = prepare(
        replace(s, workflow=(step,), demand_sets={}, units=UnitsSettings("auto", 0.1))
    )
    assert fine.topology.q == 1 / 32 and fine.units_report.target_met is True
    assert causes(fine.units_report.binding_constraints) == [
        expected("workflow.cap.pair[0]", q=1 / 16)
    ]
    assert len(calls) == 7  # one existing evaluation per candidate, no reporting solve


@pytest.mark.parametrize(
    "capacities,bad_prefixes", [((10, 20), ("a",)), ((10, 10), ("a", "b"))]
)
def test_automatic_binding_keeps_only_plans_at_the_next_coarser_unit(
    capacities, bad_prefixes
):
    # At1/16 the first star has160 path units<192; the second has320>=192.
    # At1/8 both failed, but that older observation does not bind1/32.
    p = prepare(two_stars(capacities, q="auto"), demand_sets=("d",))
    assert p.topology.q == 1 / 32 and p.units_report.target_met is True
    want = [
        expected(
            f"demand.d|{index}|0", 1 / 16, sorted(f"{prefix}{i}" for i in range(12))
        )
        for index, prefix in enumerate(("a", "b"))
        if prefix in bad_prefixes
    ]
    assert causes(p.units_report.binding_constraints) == want
    assert p.units_report.nominal_split_count == 26
    assert p.units_report.misses == ()
    # Manual preparation does not describe an unobserved coarser plan.
    manual = prepare(two_stars(capacities, q=1 / 32), demand_sets=("d",))
    assert manual.units_report.target_met is True
    assert causes(manual.units_report.binding_constraints) == []


def test_binding_head_identity_comes_from_the_coarser_observation():
    network = Network(
        nodes={name: Node(name) for name in ("s0", "s1", "s2", "s3", "x", "t")}
    )
    for i, cap in enumerate((100, 100, 100, 0.75)):
        network.add_link(Link(f"s{i}", "x", cap))
    network.add_link(Link("x", "t", 4))
    demands = DemandSet(
        "d", (DemandSpec(Selector("^s"), Selector("^t$"), 1000, config(1)),)
    )
    p = prepare(
        Scenario(network, demand_sets={"d": demands}, units=UnitsSettings("auto", 2)),
        demand_sets=("d",),
    )
    # p=2 admits candidate q2: the .75 branch rounds to0, leaving3 live
    # heads behind2 shared units. At q1 all4 are live and4 shared units fit.
    assert p.topology.q == 1 and p.units_report.target_met is True
    assert causes(p.units_report.binding_constraints) == [
        expected(q=2, heads=["s0", "s1", "s2"])
    ]
    answer = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert len(first_result(answer).plan.heads_with_capacity) == 4
    assert missed(answer) == []


def test_coarser_plan_records_append_to_current_binding_bounds():
    p = prepared(q="auto", volume=90)
    assert p.topology.q == p.units_report.q == 1 / 32
    assert p.units_report.target_met is True
    assert [c.kind for c in p.units_report.binding_constraints] == ["tunnel"] * 12 + [
        "tunnel_resolution"
    ]
    # Each of12 heads splits90/12 over16 tunnels: the bound is p/2.
    # It lies between1/32 and1/16, so these12 met bounds also bind q.
    numeric = [
        c for c in p.units_report.binding_constraints if c.kind != "tunnel_resolution"
    ]
    assert [(c.kind, c.label, c.q_upper_bound, c.met) for c in numeric] == [
        ("tunnel", f"demand.d|0|0.head[{i}]", Fraction(0.1) / 2, True)
        for i in range(12)
    ]
    assert causes(p.units_report.binding_constraints) == [expected(q=1 / 16)]


def test_unsuccessful_automatic_preparation_keeps_only_current_resolution():
    s = scenario(heads=2, cap=2**-32, volume=1, count=2)
    p = prepare(replace(s, units=UnitsSettings("auto", 1)), demand_sets=("d",))
    # At both2^-31 and2^-32 the shared link has1 unit<4 paths. The floor
    # remains insufficient; historical coarser causes must not be appended.
    assert p.topology.q == 2**-32 and p.units_report.target_met is False
    assert causes(p.units_report.binding_constraints) == [
        expected(q=2**-32, heads=["s0", "s1"])
    ]


def test_each_bad_placement_plan_has_its_own_resolution_record():
    p = prepare(two_stars(), demand_sets=("d",))
    answer = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    want = [
        expected(f"demand.d|{index}|0", heads=sorted(f"{prefix}{i}" for i in range(12)))
        for index, prefix in enumerate(("a", "b"))
    ]
    assert missed(answer) == want
    assert causes(p.units_report.binding_constraints) == want
    assert [
        row.result.delivered for row in answer.cases[0].states["converged"].rows
    ] == [0, 0]
    project(answer)


def test_each_bad_capacity_pair_has_its_own_resolution_record():
    p = prepare(replace(two_stars(), demand_sets={}))
    answer = capacity(
        p,
        CapacityQuery(
            Selector(r"^(a|b)\d"),
            Selector("^t(a|b)$"),
            config(),
            mode="pairwise",
            offer=1000,
            design_demand=1000,
            workers=1,
        ),
    )
    want = [
        expected(
            f"capacity.pair[{index}]", heads=sorted(f"{prefix}{i}" for i in range(12))
        )
        for index, prefix in ((0, "a"), (3, "b"))
    ]
    assert missed(answer) == want
    rows = answer.cases[0].states["converged"].rows
    assert len(rows) == 4
    assert [len(row.result.plan.heads_with_capacity) for row in rows] == [12, 0, 0, 12]
    assert [row.result.delivered for row in rows] == [0, 0, 0, 0]
    project(answer)


def test_insufficient_up_to_count_row_has_its_own_resolution_record():
    p = prepared(count=1, q=2)
    answer = tunnel_counts(
        p, TunnelCountQuery(p.demand_sets["d"], (1,), 1000, 1000, up_to=256, workers=1)
    )
    want = [
        expected(f"tunnel_counts.demand[d|0|0].{suffix}", 2)
        for suffix in ("count[1]", "up_to[256]")
    ]
    assert missed(answer) == want
    assert [
        (
            row.count,
            row.up_to,
            row.result.plan.tunnels_per_head,
            row.result.plan.insufficient_resolution,
            row.result.delivered,
        )
        for row in answer.rows
    ] == [(1, False, 1, True, 0), (256, True, 1, True, 0)]
    project(answer)


def test_no_legal_resolution_still_refuses_and_has_a_succeeding_control():
    s = scenario()
    s.network.replace_link("x|t|0", capacity=1e100)
    with pytest.raises(ValueError, match="no legal resolution represents"):
        prepare(replace(s, units=UnitsSettings("auto", 0.1)), demand_sets=("d",))
    assert prepared(q="auto").units_report.target_met is True


@pytest.mark.parametrize("offer,design", [(1000, 1000), (0, 0), (1000, 0), (0, 1000)])
def test_capacity_observes_once_independent_of_offer_and_design(offer, design):
    p = prepared()
    answer = capacity(
        p,
        CapacityQuery(
            Selector("^s"),
            Selector("^t$"),
            config(),
            offer=offer,
            design_demand=design,
            workers=1,
        ),
    )
    assert missed(answer) == [expected("capacity.pair[0]")]
    assert first_result(answer).delivered == 0
    assert project(answer)["units_report"]["misses"][0]["constraints"][-1] == expected(
        "capacity.pair[0]"
    )


def test_zero_nominal_and_lossless_zero_observation_keep_the_constraint():
    p = prepared(volume=0)
    assert p.units_report.nominal_split_count == 0
    assert causes(p.units_report.binding_constraints) == [expected()]
    assert p.units_report.target_met is False
    for design in (None, 1000):
        answer = capacity(
            p,
            CapacityQuery(
                Selector("^s"),
                Selector("^t$"),
                config(admission=core.Admission.LOSSLESS),
                design_demand=design,
                workers=1,
            ),
        )
        assert first_result(answer).delivered == 0
        assert missed(answer) == [expected("capacity.pair[0]")]


@pytest.mark.parametrize(
    "routing",
    [
        core.ShortestPaths(),
        core.CentralizedTE(source_allocation=core.SourceAllocation.EQUAL),
    ],
)
def test_nontunnel_zero_delivery_has_no_plan_constraint(routing):
    p = prepared(cap=0)
    answer = capacity(
        p,
        CapacityQuery(
            Selector("^s"),
            Selector("^t$"),
            core.FlowPolicyConfig(routing=routing, admission=core.Admission.LOSSLESS),
            offer=1000,
            workers=1,
        ),
    )
    assert first_result(answer).plan is None
    assert first_result(answer).delivered == 0
    assert missed(answer) == []


def test_later_count_query_does_not_rechoose_q_or_change_preparation():
    p = prepared(count=1)
    original = p.units_report
    assert original.target_met is True
    answer = tunnel_counts(
        p,
        TunnelCountQuery(p.demand_sets["d"], (1, 16), 1000, 1000, up_to=256, workers=1),
    )
    assert missed(answer) == [expected("tunnel_counts.demand[d|0|0].count[16]")]
    assert [r.result.delivered for r in answer.rows] == [20, 0, 20]
    assert [r.result.plan.tunnels_per_head for r in answer.rows] == [1, 16, 1]
    assert answer.prepared.units_report is original
    assert original.target_met is True and p.topology.q == 0.5
    # This helper is also preparation's count path: it has no native results.
    local, extra = count_splits(p, answer.query, "workflow.counts", p.topology.disabled)
    assert causes((*local, *extra)) == []


def test_sensitivity_baseline_has_a_plan_but_edge_entries_do_not(monkeypatch):
    p = prepared()
    import ngraph.analysis.precision as precision

    original = precision.query_splits
    observations = []

    def observe(*args, **kwargs):
        splits, extra = original(*args, **kwargs)
        observations.append((kwargs.get("result"), causes(extra)))
        return splits, extra

    monkeypatch.setattr(precision, "query_splits", observe)
    answer = edge_sensitivity(
        p,
        SensitivityQuery(
            Selector("^s"),
            Selector("^t$"),
            config(),
            offer=1000,
            design_demand=1000,
            workers=1,
        ),
    )
    assert missed(answer) == [expected("sensitivity.baseline")]
    assert observations[0][0] is not None
    assert all(plan is None and not extra for plan, extra in observations[1:])
    assert len(observations) == len(answer.result.entries) + 1
    pair = answer.endpoints
    splits, extra = query_splits(
        p.topology, p._named, answer.query, pair, 0, p.topology.disabled, "no-plan", 0.1
    )
    assert causes((*splits, *extra)) == []
    assert [c.members for c in splits if c.kind == "tunnel"] == [16] * 12


@pytest.mark.parametrize(
    "up_to,q,want", [(False, 0.5, True), (True, 2, True), (True, 0.5, False)]
)
def test_fixed_and_up_to_read_actual_resolution(up_to, q, want):
    p = prepared(count=256 if up_to else 16, up_to=up_to, q=q)
    answer = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert missed(answer) == ([expected(q=q)] if want else [])
    result = first_result(answer)
    assert result.plan.insufficient_resolution is want
    assert result.plan.tunnels_per_head == (1 if up_to else 16)
    if up_to and want:
        assert [
            c.members for c in p.units_report.nominal_splits if c.kind == "tunnel"
        ] == [256] * 12


@pytest.mark.parametrize(
    "kwargs",
    [{"t1": True}, {"cap": 0}, {"q": 1 / 32}, {"count": 1}, {"q": 1 / 32, "volume": 0}],
)
def test_t1_dead_and_sufficient_plans_do_not_report_resolution(kwargs):
    p = prepared(**kwargs)
    answer = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert causes(p.units_report.binding_constraints) == missed(answer) == []
    if kwargs.get("t1"):
        assert first_result(answer).plan.insufficient_resolution is None
        assert first_result(answer).plan.heads_with_capacity is None


def test_live_heads_have_native_order_and_exclude_dead_heads():
    n = Network(nodes={s: Node(s) for s in ("z", "a", "dead", "t")})
    for s, cap in (("z", 1), ("a", 100), ("dead", 0)):
        n.add_link(Link(s, "t", cap))
    d = DemandSet(
        "d", (DemandSpec(Selector("^(z|a|dead)$"), Selector("^t$"), 1000, config(2)),)
    )
    p = prepare(
        Scenario(n, demand_sets={"d": d}, units=UnitsSettings(1, 0.1)),
        demand_sets=("d",),
    )
    assert causes(p.units_report.binding_constraints) == [
        expected(q=1, heads=["a", "z"])
    ]
    answer = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert missed(answer) == [expected(q=1, heads=["a", "z"])]
    assert first_result(answer).plan.heads_with_capacity == (0, 3)


@pytest.mark.parametrize("details", [False, True])
def test_pool_head_identity_is_structured_in_every_observed_reader(details):
    s = scenario(q=1, pooled=True)
    counts = TunnelCountAnalysis(
        name="counts",
        demand_set="d",
        counts=(16,),
        design_demand=1000,
        offer=1000,
        workers=1,
    )
    p = prepare(replace(s, workflow=(counts,)), demand_sets=("d",))
    head = {"pool_id": "d|0|0", "physical_sources": sorted(f"s{i}" for i in range(12))}
    nominal = expected("demand.d|0|0", 1, [head])
    assert causes(p.units_report.binding_constraints) == [nominal]
    placed = place(
        p, PlacementQuery(p.demand_sets["d"], workers=1, export_details=details)
    )
    assert missed(placed) == [nominal]
    counted = tunnel_counts(
        p,
        TunnelCountQuery(
            p.demand_sets["d"], (16,), 1000, 1000, workers=1, export_details=details
        ),
    )
    assert missed(counted) == [
        expected("tunnel_counts.demand[d|0|0].count[16]", 1, [head])
    ]
    cfg = p.demand_sets["d"].demands[0].config
    asked = capacity(
        p,
        CapacityQuery(
            Selector("^s"),
            Selector("^t$"),
            cfg,
            offer=1000,
            design_demand=1000,
            declaration=FlowPolicyPreset.TE_ECMP_16_LSP,
            workers=1,
            export_details=details,
        ),
    )
    assert missed(asked) == [expected("capacity.pair[0]", 1, [head])]
    for answer in (placed, counted, asked):
        project(answer)
    assert project(run(p))["units_report"]["binding_constraints"][-1] == nominal


@pytest.mark.parametrize("all_dead", [False, True])
def test_failure_case_observes_its_own_plan(all_dead):
    p = prepared(q=1 / 32, parallel=True)
    failure = FailureRequest(
        FailurePolicy(
            modes=(
                FailureMode(
                    1,
                    (
                        FailureRule(
                            "link",
                            path=r"^x\|t$",
                            mode="all" if all_dead else "choice",
                            count=1,
                        ),
                    ),
                ),
            )
        ),
        1,
        7,
    )
    for answer in (
        capacity(
            p,
            CapacityQuery(
                Selector("^s"),
                Selector("^t$"),
                config(),
                offer=1000,
                design_demand=1000,
                failures=failure,
                workers=1,
            ),
        ),
        place(
            p,
            PlacementQuery(
                p.demand_sets["d"],
                failures=failure,
                workers=1,
                states=("converged", "stale", "repair"),
            ),
        ),
    ):
        assert first_result(answer).plan.max_bandwidth_per_tunnel == 1
        assert len(answer.cases) == 2
        failed = answer.cases[1].states["converged"].rows[0].result
        assert failed.plan.max_bandwidth_per_tunnel == 0
        assert len(failed.plan.heads_with_capacity) == (0 if all_dead else 12)
        prefix = "capacity.pair[0]" if answer.kind == "capacity" else "demand.d|0|0"
        assert missed(answer) == ([] if all_dead else [expected(prefix, 1 / 32)])
        assert [m.location.case_id for m in answer.misses if causes(m.constraints)] == (
            [] if all_dead else ["failure-000001"]
        )


def test_supported_count_plan_and_mask_have_the_same_live_resolution():
    p = prepared(q=1 / 32, parallel=True)
    blocked = p.topology.edges_by_link["x|t|1"]
    mask = p.topology.graph.eligibility(excluded_edges=blocked)
    ordinary = tunnel_counts(
        p,
        TunnelCountQuery(
            p.demand_sets["d"], (16,), 1000, 1000, eligibility=mask, workers=1
        ),
    )
    forward = [p.topology.edges_by_link[f"s{i}|x|0"][0] for i in range(12)]
    support = dag_from_edges(
        p.topology.graph, [*forward, p.topology.edges_by_link["x|t|0"][0]]
    )
    cfg = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(16),
            support=support,
        ),
        admission=core.Admission.LOSSY,
    )
    demands = replace(
        p.demand_sets["d"],
        demands=tuple(replace(d, config=cfg) for d in p.demand_sets["d"].demands),
    )
    supported = tunnel_counts(
        p, TunnelCountQuery(demands, (16,), 1000, 1000, workers=1)
    )
    assert (
        missed(ordinary)
        == missed(supported)
        == [expected("tunnel_counts.demand[d|0|0].count[16]", 1 / 32)]
    )


def test_ordered_residual_and_simultaneous_use_their_native_plans():
    s = scenario(heads=1, q=1 / 32)
    d = DemandSet(
        "d",
        (
            DemandSpec(Selector("^s"), Selector("^t$"), 9.75, config()),
            DemandSpec(Selector("^s"), Selector("^t$"), 1000, config()),
        ),
    )
    p = prepare(replace(s, demand_sets={"d": d}), demand_sets=("d",))
    assert causes(p.units_report.binding_constraints) == [
        expected("demand.d|1|0", 1 / 32, ["s0"])
    ]
    ordered = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert missed(ordered) == [expected("demand.d|1|0", 1 / 32, ["s0"])]
    assert [r.result.delivered for r in ordered.cases[0].states["converged"].rows] == [
        312,
        0,
    ]
    simultaneous = place(
        p, PlacementQuery(p.demand_sets["d"], workers=1, interaction="simultaneous")
    )
    assert missed(simultaneous) == [expected("demand.d|1|0", 1 / 32, ["s0"])]
    bad = prepared()
    simultaneous = place(
        bad, PlacementQuery(bad.demand_sets["d"], workers=1, interaction="simultaneous")
    )
    assert missed(simultaneous) == [expected()]


def test_msd_observes_each_bad_plan_at_its_own_probe():
    p = prepared()
    answer = maximum_supported_demand(
        p,
        MSDQuery(
            p.demand_sets["d"],
            alpha_min=0.5,
            alpha_start=1,
            alpha_max=2,
            max_bracket_iters=2,
            max_bisect_iters=2,
            export_probe_rows=True,
        ),
    )
    assert answer.search_status == "none_feasible"
    assert missed(answer) == [expected()] * len(answer.history)
    assert [
        m.location.probe_index for m in answer.misses if causes(m.constraints)
    ] == list(range(len(answer.history)))
    assert p.topology.q == 0.5


@pytest.mark.parametrize("which", ["floor", "range"])
def test_finest_legal_q_keeps_resolution_and_existing_misses(which):
    p = (
        prepared(heads=2, cap=2**-32, volume=1, count=2, q="auto")
        if which == "floor"
        else prepared(q="auto", huge=True)
    )
    q = 2**-32 if which == "floor" else 2
    heads = ["s0", "s1"] if which == "floor" else None
    assert p.topology.q == q and p.units_report.target_met is False
    assert causes(p.units_report.binding_constraints) == [expected(q=q, heads=heads)]
    assert any(
        c.kind == ("input" if which == "floor" else "capacity_sum") and not c.met
        for c in p.units_report.binding_constraints
    )


def test_constraint_wire_fields_reject_missing_null_and_near_values():
    from ngraph import TunnelResolutionConstraint, UnitsReport

    p = prepared()
    actual = causes(p.units_report.binding_constraints)[0]
    want = expected()
    assert actual == want
    assert (
        get_type_hints(TunnelResolutionConstraint)["q"]
        is get_type_hints(UnitsReport)["q"]
    )
    assert type(TunnelResolutionConstraint("x", 0.5, ("s0",)).q) is type(
        p.units_report.q
    )
    schema = {
        "$ref": "#/$defs/TunnelResolutionConstraintJSON",
        "$defs": SCHEMA["$defs"],
    }
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(actual)
    wrong = {
        "kind": "tunnel",
        "label": "demand.other",
        "q": 0.25,
        "heads": ["other", *want["heads"][1:]],
        "met": True,
    }
    for key in want:
        for mutation in ("absent", "null", "wrong"):
            changed = deepcopy(actual)
            if mutation == "absent":
                del changed[key]
            else:
                changed[key] = None if mutation == "null" else wrong[key]
            with pytest.raises(AssertionError):
                assert changed == want
            if mutation != "wrong" or key in ("kind", "met"):
                assert list(validator.iter_errors(changed))
    for value in ([], [0], None):
        assert list(validator.iter_errors({**actual, "heads": value}))
    for extra in ("reason", "tunnels_per_head", "q_upper_bound"):
        assert list(validator.iter_errors({**actual, extra: 1}))


def test_concepts_state_the_live_plan_rule():
    for q, met in ((0.5, False), (1 / 32, True)):
        p = prepared(q=q)
        assert p.units_report.target_met is met
        assert bool(causes(p.units_report.binding_constraints)) is (not met)


def test_the_automatic_preparation_description_checks_live_tunnel_plans():
    coarse = prepared(q=0.5)
    assert all(c.met for c in coarse.units_report.nominal_splits)
    assert coarse.units_report.inexact_inputs == coarse.units_report.zeroed_inputs == 0
    fine = prepared(q="auto")
    assert fine.units_report.target_met is True and fine.topology.q == 1 / 32
    assert causes(fine.units_report.binding_constraints) == [expected(q=1 / 16)]
