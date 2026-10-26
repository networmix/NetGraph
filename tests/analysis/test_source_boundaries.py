"""Source precision follows positive reachable senders and the actual support."""

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
from ngraph.workflow import MaxFlow


def network():
    value = Network(nodes={name: Node(name) for name in ("a", "b", "t")})
    for source in ("a", "b"):
        value.add_link(Link(source, "t", 100))
    return value


def weighted(weights):
    return core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.WEIGHTED,
            source_weights=weights,
        )
    )


def check_source(constraints, label, amount, basis="declared"):
    assert [
        (
            c.kind,
            c.label,
            c.incoming_physical,
            c.basis,
            c.members,
            c.q_upper_bound,
            c.met,
        )
        for c in constraints
    ] == [
        (
            "source",
            label + ".sources",
            Fraction(amount),
            basis,
            2,
            Fraction(0.075) * amount,
            False,
        )
    ]


@pytest.mark.parametrize("weights", [(1, 1, 0), (2, 1, 0)])
def test_weighted_sources_have_the_same_local_bound_on_every_reader(weights):
    model = weighted(weights)
    demands = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, model),))
    prepared = prepare(
        Scenario(network(), demand_sets={"d": demands}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    assert prepared.units_report.target_met is False
    check_source(prepared.units_report.nominal_splits, "demand.d|0|0", 10)
    answer = capacity(
        prepared,
        CapacityQuery(Selector("a|b"), Selector("t"), model, offer=10, workers=1),
    )
    assert len(answer.misses) == 1
    check_source(answer.misses[0].constraints, "capacity.pair[0]", 10)
    placed = place(prepared, PlacementQuery(prepared.demand_sets["d"], workers=1))
    assert len(placed.misses) == 1
    check_source(placed.misses[0].constraints, "demand.d|0|0", 10)
    small = network()
    for key in tuple(small.links):
        small.replace_link(key, capacity=4)
    sensitive = edge_sensitivity(
        prepare(Scenario(small, units=UnitsSettings(1, 0.075))),
        SensitivityQuery(Selector("a|b"), Selector("t"), model, workers=1),
    )
    amount = 8 if weights[0] == 1 else 6
    assert sensitive.result.baseline.delivered == amount
    constraint = next(
        c
        for m in sensitive.misses
        for c in m.constraints
        if c.label == "sensitivity.baseline.sources"
    )
    check_source((constraint,), "sensitivity.baseline", amount, "observed")


@pytest.mark.parametrize("weights", [(1, 0, 0), (0, 0, 0), (0, 1, 0)])
def test_zero_weight_sources_do_not_invent_a_split(weights):
    model = weighted(weights)
    d = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, model),))
    p = prepare(
        Scenario(network(), demand_sets={"d": d}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    assert p.units_report.nominal_splits == ()
    assert p.units_report.target_met is True
    for offer in (0, 10):
        answer = capacity(
            p,
            CapacityQuery(
                Selector("a|b"), Selector("t"), model, offer=offer, workers=1
            ),
        )
        assert answer.misses == ()
    assert place(p, PlacementQuery(p.demand_sets["d"], workers=1)).misses == ()


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("live", [0, 1, 2])
def test_tunnel_precision_support_equals_the_same_edges_masked(count, live):
    p = prepare(Scenario(network(), units=UnitsSettings(1, 0.075)))
    forward = [
        p.topology._edge_id_by_ref[DirectedLink(f"{s}|t|0", "forward")]
        for s in ("a", "b")
    ]
    edges = forward[:live]
    support = dag_from_edges(p.topology.graph, edges)
    supported = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            support=support,
            tunnel_count=core.TunnelCount(count),
        ),
        admission=core.Admission.LOSSY,
    )
    unrestricted = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(count),
        ),
        admission=core.Admission.LOSSY,
    )
    mask = p.topology.graph.eligibility(
        excluded_edges=[
            e for e in range(p.topology.graph.num_edges()) if e not in edges
        ]
    )
    answers = []
    for config, eligibility in ((supported, None), (unrestricted, mask)):
        answer = capacity(
            p,
            CapacityQuery(
                Selector("a|b"),
                Selector("t"),
                config,
                offer=10,
                design_demand=10,
                failures=(
                    FailureRequest(
                        FailurePolicy(
                            modes=(
                                FailureMode(
                                    1,
                                    (
                                        FailureRule(
                                            "link",
                                            path=".*" if live == 0 else r"^b\|t$",
                                        ),
                                    ),
                                ),
                            )
                        ),
                        1,
                        1,
                    )
                    if eligibility is not None and live < 2
                    else None
                ),
                workers=1,
            ),
        )
        row = answer.cases[-1].states["converged"].rows[0]
        assert row.result.plan.design_by_head == tuple(
            (i, 10 // live) for i in range(live)
        )
        constraints = tuple(
            c
            for m in answer.misses
            if m.location.case_id == answer.cases[-1].case.id
            for c in m.constraints
        )
        answers.append(
            tuple(
                (c.kind, c.incoming_physical, c.members, c.q_upper_bound, c.met)
                for c in constraints
            )
        )
        expected = (
            [("source", Fraction(10), 2, Fraction(0.075) * 10, False)]
            if live == 2
            else []
        )
        if count == 2:
            expected.extend(
                (
                    "tunnel",
                    Fraction(10, live),
                    2,
                    Fraction(0.075) * Fraction(10, live),
                    False,
                )
                for _ in range(live)
            )
        assert list(answers[-1]) == expected
        assert all(c.basis == "declared" for c in constraints)
        assert [c.label for c in constraints] == [
            *(["capacity.pair[0].sources"] if live == 2 else []),
            *(f"capacity.pair[0].head[{head}]" for head in range(live) if count == 2),
        ]
        assert sum(c.kind == "source" for c in constraints) == (live == 2)
        assert sum(c.kind == "tunnel" for c in constraints) == (
            live if count == 2 else 0
        )
        demands = resolve_demands(
            p, DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, config),))
        )
        counted = tunnel_counts(
            p,
            TunnelCountQuery(
                demands, (count,), 10, 10, eligibility=eligibility, workers=1
            ),
        )
        assert (
            counted.rows[0].result.plan.design_by_head == row.result.plan.design_by_head
        )
        assert (
            tuple(
                (c.kind, c.incoming_physical, c.members, c.q_upper_bound, c.met)
                for m in counted.misses
                for c in m.constraints
            )
            == answers[-1]
        )
    assert answers[0] == answers[1]


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
@pytest.mark.parametrize("valid", [False, True])
def test_diagonal_capacity_validates_the_same_model_as_other_pairs(mode, valid):
    n = Network(nodes={s: Node(s) for s in ("a", "b")})
    n.add_link(Link("a", "b", 10))
    model = core.FlowPolicyConfig(
        routing=core.ShortestPaths(
            allocation=core.RouteAllocation.WEIGHTED,
            weight_basis=core.WeightBasis.EXPLICIT,
            edge_weights=[1, 1] if valid else [1],
        )
    )
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    query = CapacityQuery(Selector("a"), Selector("a"), model, mode=mode, workers=1)
    step = MaxFlow(source=Selector("a"), target=Selector("a"), model=model, mode=mode)
    if valid:
        rows = capacity(p, query).cases[0].states["converged"].rows
        assert len(rows) == 1 and isinstance(rows[0], SelfPair)
        assert rows[0].node == "a"
        result = run(prepare(Scenario(n, [step], units=UnitsSettings(1))))
        assert isinstance(
            result.steps[0].result.cases[0].states["converged"].rows[0], SelfPair
        )
    else:
        with pytest.raises(ValueError, match="edge_weights: expected 2 entries"):
            capacity(p, query)
        with pytest.raises(ValueError, match="edge_weights: expected 2 entries"):
            prepare(Scenario(n, [step], units=UnitsSettings(1)))
        with pytest.raises(ValueError, match="edge_weights: expected 2 entries"):
            capacity(p, CapacityQuery(Selector("a"), Selector("b"), model, workers=1))


def test_positive_but_unreachable_weighted_sources_have_no_share_or_constraint():
    n = network()
    n.replace_link("b|t|0", disabled=True)
    model = weighted((1, 1, 0))
    d = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, model),))
    p = prepare(
        Scenario(n, demand_sets={"d": d}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    assert p.units_report.nominal_splits == ()
    assert place(p, PlacementQuery(p.demand_sets["d"], workers=1)).misses == ()
    assert (
        capacity(
            p, CapacityQuery(Selector("a|b"), Selector("t"), model, offer=10, workers=1)
        ).misses
        == ()
    )


def test_failure_eligibility_removes_weighted_source_precision_in_both_readers():
    model = weighted((1, 1, 0))
    d = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, model),))
    p = prepare(
        Scenario(network(), demand_sets={"d": d}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    failures = FailureRequest(
        FailurePolicy(modes=(FailureMode(1, (FailureRule("link", path=r"^b\|t$"),)),)),
        1,
        1,
    )
    for answer in (
        place(p, PlacementQuery(p.demand_sets["d"], failures=failures, workers=1)),
        capacity(
            p,
            CapacityQuery(
                Selector("a|b"),
                Selector("t"),
                model,
                offer=10,
                failures=failures,
                workers=1,
            ),
        ),
    ):
        assert len(answer.cases) == 2
        assert len(answer.misses) == 1
        assert answer.misses[0].location.case_id == "baseline"


def test_each_placed_tunnel_plan_stays_paired_with_its_own_demand():
    model = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(1),
        )
    )
    d = DemandSet(
        "d",
        (
            DemandSpec(Selector("a|b"), Selector("t"), 10, model),
            DemandSpec(Selector("a"), Selector("t"), 20, model),
        ),
    )
    p = prepare(
        Scenario(network(), demand_sets={"d": d}, units=UnitsSettings(1, 0.075)),
        demand_sets=("d",),
    )
    check_source(p.units_report.nominal_splits, "demand.d|0|0", 10)
    answer = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    assert len(answer.misses) == 1
    check_source(answer.misses[0].constraints, "demand.d|0|0", 10)
