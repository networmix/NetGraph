"""Tunnel-count rows: one fresh native T2 evaluation per demand and count.

Expected plans are worked T2 examples, derived by hand; the
stated lossless delivery is checked against a separate native LOSSLESS
evaluation at the design, which no production code calls.
"""

import io
import json
from dataclasses import replace
from fractions import Fraction

import netgraph_core as ngc
import pytest

import ngraph
import ngraph.workflow
from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    TunnelCountQuery,
    UnitsSettings,
    prepare,
    tunnel_counts,
    write_json,
)
from ngraph.analysis import counts
from ngraph.analysis.placement import _endpoints
from ngraph.analysis.topology import SyntheticIngress
from ngraph.workflow import TunnelCountAnalysis

LOSSLESS, LOSSY = ngc.Admission.LOSSLESS, ngc.Admission.LOSSY
EQUAL = ngc.SourceAllocation.EQUAL
TE16 = FlowPolicyPreset.TE_ECMP_16_LSP
G1_Q = 2.0**-12


def t2(k=1, up_to=False, allocation=EQUAL, headroom=True, admission=LOSSLESS):
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=allocation,
            tunnel_count=ngc.TunnelCount(k, up_to=up_to),
            prefer_headroom=headroom,
        ),
        admission=admission,
    )


def network(links, nodes=()):
    names = sorted({u for u, v, *_ in links} | {v for u, v, *_ in links} | set(nodes))
    net = Network(nodes={name: Node(name) for name in names})
    for u, v, capacity, *cost in links:
        net.add_link(Link(u, v, capacity, cost[0] if cost else 1))
    return net


def spec(source, target, policy=None, volume=0, **fields):
    return DemandSpec(
        Selector(source), Selector(target), volume, policy or t2(), **fields
    )


def prepared(links, specs, q=1.0, steps=(), nodes=()):
    scenario = Scenario(
        network(links, nodes),
        steps,
        demand_sets={"d": DemandSet("d", tuple(specs))},
        units=UnitsSettings(q),
    )
    return prepare(scenario, demand_sets=("d",))


def ask(prep, counts_=(1,), design=0.0, offer=0.0, **fields):
    return tunnel_counts(
        prep,
        TunnelCountQuery(prep.demand_sets["d"], counts_, design, offer, **fields),
    )


def separate_lossless(prep, row, design_units, mask=None):
    """The native LOSSLESS delivery at offer = design, on a fresh evaluation."""
    demand = next(d for d in prep.demand_sets["d"].demands if d.id == row.id)
    model = demand.config.routing
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=model.source_allocation,
            tunnel_count=ngc.TunnelCount(row.count, up_to=row.up_to),
            prefer_headroom=model.prefer_headroom,
        )
    )
    sources, targets = _endpoints(prep.topology, demand)
    options = ngc.EvaluationOptions(
        config, eligibility=mask, design_demand=design_units, offer=design_units
    )
    return ngc.evaluate_demand(prep.topology.graph, sources, targets, options)


def plan(row):
    p = row.result.plan
    return (
        p.tunnels_per_head,
        p.design_demand,
        tuple(p.design_by_head),
        tuple(p.heads_with_capacity),
        p.insufficient_resolution,
        p.max_fractional_bandwidth_per_tunnel,
        p.max_bandwidth_per_tunnel,
        p.planned_bandwidth_per_tunnel,
        p.total_planned_bandwidth,
        p.total_tunnel_cost,
        p.headroom_penalty,
        p.max_lossless_offer,
    )


def lost(row):
    return row.result.source_drops + sum(units for _, units in row.result.edge_drops)


# G1: 0->1->3 two links of 2, 0->2->3 two links of 10 (at q = 2^-12: 8192, 40960 units).
G1 = [("n0", "n1", 2), ("n0", "n2", 10), ("n1", "n3", 2), ("n2", "n3", 10)]


def g1(k=16, up_to=False):
    return prepared(G1, [spec("^n0$", "^n3$", t2(k, up_to))], q=G1_Q)


def test_plan_and_delivery_at_a_design_equal_to_the_offer():
    (row,) = ask(g1(), (16,), 12, 12).rows
    p = row.result.plan
    assert (p.max_bandwidth_per_tunnel, p.planned_bandwidth_per_tunnel) == (2925, 2925)
    assert p.max_fractional_bandwidth_per_tunnel == Fraction(20480, 7)
    assert (p.total_planned_bandwidth, p.max_lossless_offer) == (46800, 46812)
    assert p.total_tunnel_cost == 32 and p.tunnels_per_head == 16
    assert (row.result.offered, row.result.delivered) == (49152, 47104)
    assert (row.result.source_drops, lost(row)) == (0, 2048)
    assert (
        row.lossless_at_design_units
        == 46812
        == separate_lossless(g1(), row, 49152).delivered
    )


def test_the_stated_lossless_delivery_is_min_of_design_and_bound():
    prep = g1()
    (row,) = ask(prep, (16,), 2, 12).rows
    p = row.result.plan
    # Working size u = min(U, ceil(8192 / 16)) = 512, not U = 2925.
    assert (p.max_bandwidth_per_tunnel, p.planned_bandwidth_per_tunnel) == (2925, 512)
    assert (p.total_planned_bandwidth, p.max_lossless_offer) == (8192, 46812)
    assert row.result.delivered == 47104
    # min(D, F) = 8192: neither F nor min(O, F) (46812 each).
    assert row.lossless_at_design_units == 8192
    assert separate_lossless(prep, row, 8192).delivered == 8192
    zero = prepared([("a", "b", 10)], [spec("^a$", "^b$", t2(2))])
    (row,) = ask(zero, (2,), 0, 4).rows
    p = row.result.plan
    assert (p.planned_bandwidth_per_tunnel, p.total_planned_bandwidth) == (1, 2)
    assert p.max_lossless_offer == 10 and row.result.delivered == 4
    # min(0, 10) = 0, not the planned total 2.
    assert (
        row.lossless_at_design_units == 0 == separate_lossless(zero, row, 0).delivered
    )


def test_the_plan_reads_the_design_only():
    prep = g1()
    for design in (12, 2):
        (row,) = ask(prep, (16,), design, 12).rows
        oracle = separate_lossless(prep, row, int(design / G1_Q))
        assert plan(row) == (
            oracle.plan.tunnels_per_head,
            oracle.plan.design_demand,
            tuple(oracle.plan.design_by_head),
            tuple(oracle.plan.heads_with_capacity),
            oracle.plan.insufficient_resolution,
            oracle.plan.max_fractional_bandwidth_per_tunnel,
            oracle.plan.max_bandwidth_per_tunnel,
            oracle.plan.planned_bandwidth_per_tunnel,
            oracle.plan.total_planned_bandwidth,
            oracle.plan.total_tunnel_cost,
            oracle.plan.headroom_penalty,
            oracle.plan.max_lossless_offer,
        )
    one = prepared([("a", "b", 10)], [spec("^a$", "^b$", t2(2))])
    (none,) = ask(one, (2,), 4, 0).rows
    (some,) = ask(one, (2,), 4, 6).rows
    assert none.result.termination == ngc.Termination.COMPLETE
    assert (none.result.delivered, none.result.source_drops) == (0, 0)
    assert plan(none) == plan(some) and plan(none)[1] == 4


def test_idle_tunnels_keep_their_rows():
    prep = prepared([("a", "b", 10)], [spec("^a$", "^b$", t2(4))])
    (row,) = ask(prep, (4,), 3, 3, export_details=True).rows
    p = row.result.plan
    assert (p.max_bandwidth_per_tunnel, p.planned_bandwidth_per_tunnel) == (2, 1)
    assert p.total_planned_bandwidth == 4
    assert [t.assigned for t in row.result.by_tunnel] == [1, 1, 1, 0]
    assert row.lossless_at_design_units == 3
    buffer = io.StringIO()
    write_json(ask(prep, (4,), 3, 3, export_details=True), buffer)
    (exported,) = json.loads(buffer.getvalue())["analysis"]["rows"]
    assert [t["assigned_units"] for t in exported["result"]["by_tunnel"]] == [
        1,
        1,
        1,
        0,
    ]


TINY = [("h0", "t", 1), ("h1", "t", 100)]


def test_a_live_head_too_weak_for_one_unit_per_tunnel():
    prep = prepared(TINY, [spec("^h[01]$", "^t$", t2(16))])
    exact, limit = ask(prep, (16,), 10, 10, up_to=3).rows
    p = exact.result.plan
    assert (p.insufficient_resolution, p.max_bandwidth_per_tunnel) == (True, 0)
    assert p.max_fractional_bandwidth_per_tunnel == Fraction(1, 16)
    assert len(exact.result.program.tunnels) == 0
    assert (exact.result.delivered, exact.result.source_drops) == (0, 10)
    assert exact.result.termination == ngc.Termination.COMPLETE
    assert exact.lossless_at_design_units == 0
    oracle = separate_lossless(prep, exact, 10)
    assert (oracle.delivered, oracle.termination) == (0, ngc.Termination.EXHAUSTED)
    # Up to 3: k = 1 has U = 1 and carries 2; k = 2 and 3 have U = 0.
    q = limit.result.plan
    assert (limit.count, limit.up_to, q.tunnels_per_head) == (3, True, 1)
    assert (q.max_bandwidth_per_tunnel, q.max_lossless_offer) == (1, 2)
    assert q.insufficient_resolution is False


def test_a_dead_head_keeps_its_share_and_loses_it():
    prep = prepared([("h0", "t", 0), ("h1", "t", 10)], [spec("^h[01]$", "^t$", t2(2))])
    exact, limit = ask(prep, (2,), 10, 10, up_to=2).rows
    p = exact.result.plan
    h1 = prep.topology.node_id_by_name["h1"]
    assert tuple(p.heads_with_capacity) == (h1,)
    # u = min(5, ceil(RR(10, 2, h1) / 2)) = 3: the design shares of the whole roster.
    assert (p.max_bandwidth_per_tunnel, p.planned_bandwidth_per_tunnel) == (5, 3)
    assert (p.total_planned_bandwidth, p.max_lossless_offer) == (6, 0)
    assert (exact.result.delivered, exact.result.source_drops) == (5, 5)
    assert exact.lossless_at_design_units == 0
    assert separate_lossless(prep, exact, 10).delivered == 0
    assert limit.result.plan.tunnels_per_head == 1


def test_up_to_rows_choose_the_smallest_sufficient_count():
    (row,) = ask(g1(6, True), (), 12, 12, up_to=6).rows
    assert (row.result.plan.tunnels_per_head, row.result.plan.max_lossless_offer) == (
        6,
        49152,
    )
    common = prepared(
        [("h0", "t", 6), ("h1", "t", 3), ("h1", "t", 3)],
        [spec("^h[01]$", "^t$", t2(2, True))],
    )
    (row,) = ask(common, (), 12, 12, up_to=2).rows
    assert row.result.plan.tunnels_per_head == 2
    assert len(row.result.program.tunnels) == 4


def test_a_pool_head_against_equal_physical_heads():
    links = [("a", "t", 2), ("b", "t", 10)]
    prep = prepared(
        links,
        [
            spec("^(a|b)$", "^t$", t2(2), id="equal"),
            spec("^(a|b)$", "^t$", TE16, id="pool"),
        ],
        steps=(
            TunnelCountAnalysis(
                "c", demand_set="d", counts=(2,), design_demand=12, offer=12
            ),
        ),
    )
    equal, pool = ask(prep, (2,), 12, 12).rows
    assert (
        len(equal.result.program.tunnels),
        equal.result.plan.max_bandwidth_per_tunnel,
    ) == (4, 1)
    assert equal.result.plan.max_lossless_offer == 4
    assert pool.pool is not None
    assert (
        len(pool.result.program.tunnels),
        pool.result.plan.max_bandwidth_per_tunnel,
    ) == (2, 5)
    assert pool.result.plan.max_lossless_offer == 10
    assert pool.result.plan.total_tunnel_cost == 4 and pool.physical_tunnel_cost == 2


def pool_scenario(offer):
    """S -> T over (1, cost 1) and (100, cost 2); a pooled TE demand; a count step's offer."""
    steps = ()
    if offer is not None:
        steps = (
            TunnelCountAnalysis(
                "c", demand_set="d", counts=(2,), design_demand=2, offer=offer
            ),
        )
    return prepared(
        [("S", "T", 1, 1), ("S", "T", 100, 2)],
        [spec("^S$", "^T$", TE16, id="pooled")],
        steps=steps,
    )


def ingress(prep):
    return [
        e
        for e, ref in enumerate(prep.topology.edge_refs)
        if isinstance(ref, SyntheticIngress)
    ]


def test_a_count_offer_is_the_pool_budget():
    prep = pool_scenario(1000)
    (demand,) = prep.demand_sets["d"].demands
    assert demand.pool.offer_limit_units == 1000
    edges = ingress(prep)
    assert [int(prep.topology.graph.edge_capacity_units()[e]) for e in edges] == [1000]
    (row,) = ask(prep, (2,), 2, 1000).rows
    assert row.result.plan.planned_bandwidth_per_tunnel == 1
    assert row.result.delivered == 1 + 100
    assert sum(units for e, units in row.result.edge_drops if e in edges) == 0
    # Without the count step the attachment is the outgoing capacity 101 and no lossy
    # budget exists, so the library question is refused rather than throttled to 51.
    bare = pool_scenario(None)
    assert [
        int(bare.topology.graph.edge_capacity_units()[e]) for e in ingress(bare)
    ] == [101]
    with pytest.raises(ValueError, match="exceeds the prepared lossy budget 0 units"):
        ask(bare, (2,), 2, 1000)


def test_the_headroom_penalty_prices_the_ingress_budget():
    (wide,) = ask(pool_scenario(1000), (2,), 2, 1000).rows
    (narrow,) = ask(pool_scenario(101), (2,), 2, 101).rows
    # Sum over links of floor(2^32 * j * u / B): ingress, the (1, 1) link, the (100, 2) link.
    two32 = 2**32
    assert (
        wide.result.plan.headroom_penalty
        == two32 // 1000 + 2 * two32 // 1000 + two32 + two32 // 100
    )
    assert narrow.result.plan.headroom_penalty == 4465490253
    assert type(wide.result.plan.headroom_penalty) is int


def test_physical_tunnel_cost_leaves_out_one_ingress_hop_per_tunnel():
    (pooled,) = ask(pool_scenario(1000), (2,), 2, 1000).rows
    assert (pooled.result.plan.total_tunnel_cost, pooled.physical_tunnel_cost) == (5, 3)
    (physical,) = ask(g1(), (16,), 12, 12).rows
    assert physical.physical_tunnel_cost == physical.result.plan.total_tunnel_cost == 32
    weak = prepared(
        [("S1", "X", 6), ("S2", "X", 5), ("X", "T", 7), ("S1", "T", 3, 4)],
        [spec("^S", "^T$", TE16, id="pool")],
        steps=(
            TunnelCountAnalysis(
                "c", demand_set="d", counts=(16,), design_demand=4, offer=4
            ),
        ),
    )
    (row,) = ask(weak, (16,), 4, 4).rows
    # 16 one-unit tunnels need a flow of 16 > 10: U = 0, no tunnels, nothing to subtract.
    assert row.result.plan.max_bandwidth_per_tunnel == 0
    assert (row.result.plan.total_tunnel_cost, row.physical_tunnel_cost) == (0, 0)
    assert type(row.physical_tunnel_cost) is int


def test_a_masked_roster_reports_no_route():
    prep = prepared([("a", "b", 10)], [spec("^a$", "^b$", t2(2))])
    nothing = prep.topology.graph.eligibility(
        excluded_nodes=[prep.topology.node_id_by_name["a"]]
    )
    (row,) = ask(prep, (2,), 4, 5, eligibility=nothing).rows
    assert row.result.termination == ngc.Termination.NO_ROUTE
    assert (row.result.delivered, row.result.source_drops) == (0, 5)
    assert tuple(row.result.plan.heads_with_capacity) == ()
    assert row.result.plan.max_lossless_offer == 0 and row.lossless_at_design_units == 0


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_a_zero_capacity_link_changes_no_plan_field(k):
    base = [("a", "m", 6, 1), ("a", "m", 9, 2), ("m", "b", 12, 1)]
    extra = [("a", "m", 6, 1), ("a", "m", 0, 1), ("a", "m", 9, 2), ("m", "b", 12, 1)]
    rows = [
        ask(prepared(links, [spec("^a$", "^b$", t2(k))]), (k,), 10, 11).rows[0]
        for links in (base, extra)
    ]
    assert plan(rows[0]) == plan(rows[1])
    assert [(r.result.delivered, r.result.source_drops) for r in rows][0] == (
        rows[1].result.delivered,
        rows[1].result.source_drops,
    )


def test_the_largest_count():
    prep = prepared([("a", "b", 10000, 3)], [spec("^a$", "^b$", t2(1))])
    (row,) = ask(prep, (10000,), 10000, 10000).rows
    p = row.result.plan
    assert (p.max_bandwidth_per_tunnel, p.planned_bandwidth_per_tunnel) == (1, 1)
    assert (p.total_planned_bandwidth, p.max_lossless_offer) == (10000, 10000)
    assert (p.total_tunnel_cost, row.result.delivered) == (30000, 10000)
    with pytest.raises(
        ValueError,
        match=r"^tunnel_counts\.counts\[0\]: expected an integer in \[1, 10000\], "
        r"got 10001$",
    ):
        ask(prep, (10001,), 1, 1)


def test_an_offer_at_the_units_bound_is_refused_with_its_label():
    prep = prepared([("a", "b", 10)], [spec("^a$", "^b$", t2(2))])
    with pytest.raises(ValueError, match=r"^tunnel_counts\.offer: to_units"):
        ask(prep, (2,), 1, 2.0**62)
    with pytest.raises(ValueError, match=r"^tunnel_counts\.design_demand: to_units"):
        ask(prep, (2,), 2.0**62, 1)


def test_rows_follow_the_set_then_the_declared_counts_then_up_to():
    prep = prepared(
        [("a", "t", 100), ("b", "t", 100)],
        [spec("^a$", "^t$", id="d0"), spec("^b$", "^t$", id="d1")],
    )
    rows = ask(prep, (16, 8), 10, 10, up_to=4).rows
    assert [(r.base_id, r.count, r.up_to) for r in rows] == [
        ("d0", 16, False),
        ("d0", 8, False),
        ("d0", 4, True),
        ("d1", 16, False),
        ("d1", 8, False),
        ("d1", 4, True),
    ]


MESH = [
    ("p0", "p2", 6),
    ("p0", "p3", 4, 2),
    ("p1", "p2", 5),
    ("p2", "p4", 7),
    ("p3", "p4", 9),
    ("p1", "p3", 3, 3),
]


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_batched_rows_equal_independent_evaluations_and_workers(k):
    prep = prepared(
        MESH,
        [
            spec("^p0$", "^p4$", id="x"),
            spec("^p1$", "^p4$", id="y"),
            spec("^p[01]$", "^p4$", id="z"),
        ],
    )
    topology = prep.topology
    refs = topology.edges_by_link["p1|p2|0"]
    mask = topology.graph.eligibility(excluded_edges=[refs[0]])
    one = ask(prep, (k,), 9, 11, eligibility=mask, workers=1).rows
    four = ask(prep, (k,), 9, 11, eligibility=mask, workers=4).rows
    for row, other in zip(one, four, strict=True):
        demand = next(d for d in prep.demand_sets["d"].demands if d.id == row.id)
        sources, targets = _endpoints(topology, demand)
        options = ngc.EvaluationOptions(
            t2(k, admission=LOSSY), eligibility=mask, design_demand=9, offer=11
        )
        alone = ngc.evaluate_demand(topology.graph, sources, targets, options)
        for value in (row.result, other.result):
            assert (value.delivered, value.source_drops, list(value.edge_drops)) == (
                alone.delivered,
                alone.source_drops,
                list(alone.edge_drops),
            )
            assert value.plan.max_lossless_offer == alone.plan.max_lossless_offer
            assert value.plan.headroom_penalty == alone.plan.headroom_penalty


def test_equal_models_share_one_call_and_rows_keep_the_set_order(monkeypatch):
    calls = []
    real = ngc.evaluate_pairs

    def counting(graph, pairs, options, workers=1):
        calls.append(len(pairs))
        return real(graph, pairs, options, workers=workers)

    monkeypatch.setattr(ngc, "evaluate_pairs", counting)
    prep = prepared(
        [("a", "t", 10), ("b", "t", 10), ("c", "t", 10)],
        [
            spec("^a$", "^t$", t2(1, headroom=False), id="A"),
            spec("^b$", "^t$", TE16, id="B"),
            spec("^c$", "^t$", t2(1, headroom=False), id="A2"),
        ],
        steps=(
            TunnelCountAnalysis(
                "c", demand_set="d", counts=(2,), design_demand=4, offer=4
            ),
        ),
    )
    calls.clear()
    rows = ask(prep, (2,), 4, 4, up_to=3).rows
    # Two model groups (A with A2, B) per row spec: four calls, not six.
    assert sorted(calls) == [1, 1, 2, 2]
    assert [r.base_id for r in rows] == ["A", "A", "B", "B", "A2", "A2"]
    assert [type(r.result.plan.headroom_penalty) for r in rows] == [
        type(None),
        type(None),
        int,
        int,
        type(None),
        type(None),
    ]


def test_every_leaf_needs_a_tunnelled_centralized_model():
    for policy in (
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        ngc.FlowPolicyConfig(routing=ngc.DistributedTE(ngc.TunnelCount(2))),
        ngc.FlowPolicyConfig(routing=ngc.CentralizedTE(source_allocation=EQUAL)),
    ):
        prep = prepared([("a", "t", 10)], [spec("^a$", "^t$", policy, id="x")])
        with pytest.raises(
            ValueError,
            match=r"^tunnel_counts\.demands: demand x\|0: TunnelCountAnalysis needs a "
            r"CentralizedTE model with a tunnel count$",
        ):
            ask(prep, (2,), 1, 1)
    ask(prepared([("a", "t", 10)], [spec("^a$", "^t$", id="x")]), (2,), 1, 1)


def test_an_offer_above_a_prepared_budget_is_refused():
    prep = pool_scenario(10)
    with pytest.raises(
        ValueError,
        match=r"^tunnel_counts\.offer: demand pooled\|0: offer 1000 units exceeds the "
        r"prepared lossy budget 10 units of TE ingress pool pooled\|0$",
    ):
        ask(prep, (2,), 2, 1000)
    # Offer 10 splits 5/5 over the two tunnels; the 1-unit link carries 1 of its 5.
    assert ask(prep, (2,), 2, 10).rows[0].result.delivered == 6


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"counts": ()},
            r"^tunnel_counts\.counts: give at least one count or up_to, got \(\)$",
        ),
        (
            {"counts": (0,)},
            r"^tunnel_counts\.counts\[0\]: expected an integer in \[1, 10000\], got 0$",
        ),
        ({"counts": (1, 10001)}, r"^tunnel_counts\.counts\[1\]: expected an integer"),
        ({"counts": (True,)}, r"^tunnel_counts\.counts\[0\]: expected an integer"),
        ({"counts": (3, 3)}, r"^tunnel_counts\.counts: duplicate count 3$"),
        (
            {"up_to": 0},
            r"^tunnel_counts\.up_to: expected an integer in \[1, 10000\], got 0$",
        ),
        (
            {"offer": float("nan")},
            r"^tunnel_counts\.offer: expected a finite nonnegative",
        ),
        (
            {"offer": float("inf")},
            r"^tunnel_counts\.offer: expected a finite nonnegative",
        ),
        ({"offer": -1}, r"^tunnel_counts\.offer: expected a finite nonnegative"),
        ({"design_demand": float("inf")}, r"^tunnel_counts\.design_demand: expected"),
        (
            {"offer": True},
            r"^tunnel_counts\.offer: expected a finite real number, got True$",
        ),
        (
            {"counts": (1.5,)},
            r"^tunnel_counts\.counts\[0\]: expected an integer in \[1, 10000\], got 1\.5$",
        ),
        (
            {"up_to": True},
            r"^tunnel_counts\.up_to: expected an integer in \[1, 10000\], got True$",
        ),
        (
            {"up_to": 2.5},
            r"^tunnel_counts\.up_to: expected an integer in \[1, 10000\], got 2\.5$",
        ),
    ],
)
def test_query_refusals(fields, message):
    demands = prepared([("a", "t", 10)], [spec("^a$", "^t$")]).demand_sets["d"]
    values = {"counts": (1,), "design_demand": 1, "offer": 1, **fields}
    with pytest.raises(ValueError, match=message):
        TunnelCountQuery(demands, **values)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"eligibility": "a"},
            r"^tunnel_counts\.eligibility: expected native Eligibility, got 'a'$",
        ),
        (
            {"outputs": {}},
            r"^tunnel_counts\.outputs: expected native OutputOptions, got \{\}$",
        ),
    ],
)
def test_query_type_refusals(fields, message):
    demands = prepared([("a", "t", 10)], [spec("^a$", "^t$")]).demand_sets["d"]
    with pytest.raises(TypeError, match=message):
        TunnelCountQuery(demands, (1,), 1, 1, **fields)


def test_legal_query_bounds():
    prep = prepared([("a", "t", 10)], [spec("^a$", "^t$")])
    assert len(ask(prep, (1, 10000), 0, 0, up_to=10000).rows) == 3
    assert ask(prep, (), 0, 0, up_to=1).rows[0].up_to


def test_a_stated_lossless_value_of_every_listed_case_matches_the_separate_evaluation():
    cases = [
        (g1(), (16,), 12, 12, {}),
        (prepared(TINY, [spec("^h[01]$", "^t$", t2(16))]), (16,), 10, 10, {"up_to": 3}),
        (
            prepared([("h0", "t", 0), ("h1", "t", 10)], [spec("^h[01]$", "^t$")]),
            (2,),
            10,
            10,
            {"up_to": 2},
        ),
        (pool_scenario(1000), (2,), 2, 1000, {}),
    ]
    for prep, values, design, offer, fields in cases:
        units = int(design / prep.topology.q)
        for row in ask(prep, values, design, offer, **fields).rows:
            assert (
                row.lossless_at_design_units
                == separate_lossless(prep, row, units).delivered
            )


def test_the_two_classes_named_tunnel_count_analysis_are_distinct():
    assert ngraph.TunnelCountAnalysis is not ngraph.workflow.TunnelCountAnalysis
    assert counts.TunnelCountAnalysis is ngraph.TunnelCountAnalysis


def counting_calls(monkeypatch):
    """Record each native call's pair count."""
    calls = []
    real = ngc.evaluate_pairs

    def counting(graph, pairs, options, workers=1):
        calls.append(len(pairs))
        return real(graph, pairs, options, workers=workers)

    monkeypatch.setattr(ngc, "evaluate_pairs", counting)
    return calls


def supported(shared):
    """Two S -> T demands whose supports keep link S|T|0 (capacity 1) and S|T|1
    (capacity 100), or both S|T|0's. The supports are bound on the prepared graph
    and no Python reference to them outlives this call."""
    prep = prepared(
        [("S", "T", 1, 1), ("S", "T", 100, 2)],
        [spec("^S$", "^T$", id="small"), spec("^S$", "^T$", id="large")],
    )
    topology = prep.topology
    source = topology.node_id_by_name["S"]
    supports = [
        ngc.spf(
            topology.graph,
            [source],
            ngc.SpfOptions(
                ngc.Direction.FORWARD,
                eligibility=topology.graph.eligibility(
                    excluded_edges=list(topology.edges_by_link[f"S|T|{other}"])
                ),
            ),
        ).dag
        for other in (1, 0)
    ]
    if shared:
        supports[1] = supports[0]
    demands = prep.demand_sets["d"]
    configs = [
        ngc.FlowPolicyConfig(
            routing=ngc.CentralizedTE(
                source_allocation=EQUAL, support=dag, tunnel_count=ngc.TunnelCount(1)
            )
        )
        for dag in supports
    ]
    return prep, replace(
        demands,
        demands=tuple(
            replace(d, config=c) for d, c in zip(demands.demands, configs, strict=True)
        ),
    )


@pytest.mark.parametrize(
    ("shared", "calls", "delivered", "bound"),
    [(False, [1, 1], [1, 10], [1, 100]), (True, [2], [1, 1], [1, 1])],
)
def test_rows_keep_their_support_and_share_a_call_only_with_the_same_one(
    monkeypatch, shared, calls, delivered, bound
):
    prep, demands = supported(shared)
    made = counting_calls(monkeypatch)
    rows = tunnel_counts(prep, TunnelCountQuery(demands, (1,), 10, 10)).rows
    # Offer 10 on one tunnel: the 1-unit link carries 1, the 100-unit link all 10.
    assert made == calls
    assert [r.result.delivered for r in rows] == delivered
    assert [r.result.plan.max_lossless_offer for r in rows] == bound


def test_the_group_key_separates_allocation_and_headroom(monkeypatch):
    # X and Y differ only in prefer_headroom, Y and Z only in source allocation.
    prep = prepared(
        [
            ("S", "A", 10),
            ("A", "T", 10),
            ("S", "B", 100),
            ("B", "T", 100),
            ("S", "C", 30),
            ("C", "T", 30),
        ],
        [
            spec("^S$", "^T$", t2(2, headroom=True), id="X"),
            spec("^S$", "^T$", t2(2, headroom=False), id="Y"),
            spec(
                "^S$",
                "^T$",
                t2(2, allocation=ngc.SourceAllocation.OPTIMIZED, headroom=False),
                id="Z",
            ),
        ],
    )
    made = counting_calls(monkeypatch)
    rows = ask(prep, (1, 2), 40, 40).rows
    assert made == [1] * 6
    # A plan reports its headroom penalty exactly when its own model prefers headroom.
    assert [(r.base_id, r.result.plan.headroom_penalty is None) for r in rows] == [
        ("X", False),
        ("X", False),
        ("Y", True),
        ("Y", True),
        ("Z", True),
        ("Z", True),
    ]


def test_a_query_mask_keeps_the_scenario_disabled_elements():
    net = network([("S", "A", 100), ("S", "B", 10, 5), ("B", "T", 10, 5)], nodes="C")
    net.add_link(Link("A", "T", 100, 1, disabled=True))
    net.add_link(Link("S", "C", 10, 5))
    net.add_link(Link("C", "T", 10, 5))
    scenario = Scenario(
        net, (), demand_sets={"d": DemandSet("d", (spec("^S$", "^T$", t2(1)),))}
    )
    prep = prepare(replace(scenario, units=UnitsSettings(1.0)), demand_sets=("d",))
    without_c = prep.topology.graph.eligibility(
        excluded_nodes=[prep.topology.node_id_by_name["C"]]
    )
    (row,) = ask(prep, (1,), 8, 8, eligibility=without_c).rows
    # S-A-T is disabled and C is excluded: the tunnel takes S-B-T (10, cost 5 + 5).
    plan = row.result.plan
    assert (
        plan.max_bandwidth_per_tunnel,
        plan.max_lossless_offer,
        plan.total_tunnel_cost,
        row.result.delivered,
    ) == (10, 10, 10, 8)
