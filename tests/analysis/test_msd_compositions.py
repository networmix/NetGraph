"""MSD over the demand forms the controller, failure states and pools added.

Each case's feasible boundary is derived by hand: the controller tables' lossless
bounds (640, 720 and 166 units on the wcmp_scope network), highest averages for
weighted sources, the pool's maximum flow. The persistent-roster probes are
compared with fresh placements at the same alpha.
"""

import netgraph_core as ngc
import pytest

from ngraph import (
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
    place,
    prepare,
)
from ngraph.analysis import controller
from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.analysis.topology import SyntheticIngress
from tests.controller.helpers import demand, prepared
from tests.controller.test_tables import WCMP_SCOPE, wcmp_scope_tree

TE16 = FlowPolicyPreset.TE_ECMP_16_LSP


def scope(name, volume=100, demands=None):
    trees = {"g": wcmp_scope_tree()} if name == "group" else {}
    return prepared(
        WCMP_SCOPE,
        "^(P|Q)(A|B)[12]$",
        "^DC",
        demands or [demand("^DC$", "^DCB$", volume)],
        scope=name,
        q=1,
        trees=trees,
    )


def physical(links, specs, q=1):
    names = sorted({u for u, v, *_ in links} | {v for u, v, *_ in links})
    net = Network(nodes={name: Node(name) for name in names})
    for u, v, capacity, *cost in links:
        net.add_link(Link(u, v, capacity, cost[0] if cost else 1))
    scenario = Scenario(
        net, demand_sets={"d": DemandSet("d", tuple(specs))}, units=UnitsSettings(q)
    )
    return prepare(scenario, demand_sets=("d",))


@pytest.mark.parametrize(
    ("name", "best", "upper"),
    [
        # Bound 640 units: 6.3984375 x 100 rounds to 640, 6.40625 x 100 to 641.
        ("next_hop", 6.3984375, 6.40625),
        # Bound 720 units.
        ("all_routers", 7.203125, 7.2109375),
        # Bound 166 units (160 + 6 by round robin).
        ("group", 1.6640625, 1.671875),
    ],
)
def test_controller_tables_are_fixed_programs_over_the_series(
    name, best, upper, monkeypatch
):
    prep = scope(name)
    built = []
    real = controller.destination_table

    def counting(*args, **kwargs):
        built.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(controller, "destination_table", counting)
    result = maximum_supported_demand(prep, MSDQuery(prep.demand_sets["d"]))
    assert built == []
    assert (result.proof, result.monotone_proven) == ("fixed_program", True)
    assert result.alpha_feasible.value == best
    certificate = result.upper_certificate
    assert (certificate.lower.value, certificate.upper.value) == (best, upper)
    assert result.search_status == "feasible"


def test_a_controlled_set_beside_a_live_controller_is_unproved():
    live = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    prep = scope(
        "next_hop",
        demands=[
            demand("^DC$", "^DCB$", 100),
            demand("^PA1$", "^DCB$", 10, live, priority=1),
        ],
    )
    result = maximum_supported_demand(prep, MSDQuery(prep.demand_sets["d"]))
    assert (result.proof, result.monotone_proven) == ("unproved", False)
    assert result.upper_certificate is None


def weighted(count):
    prep = physical([("A", "T", 3), ("B", "T", 8)], [])
    weights = [0] * prep.topology.graph.num_nodes()
    weights[prep.topology.node_id_by_name["A"]] = 1
    weights[prep.topology.node_id_by_name["B"]] = 3
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.WEIGHTED, source_weights=weights
        )
    )
    specs = [
        DemandSpec(Selector("^(A|B)$"), Selector("^T$"), 4, config, id=f"w{i}")
        for i in range(count)
    ]
    prep = physical([("A", "T", 3), ("B", "T", 8)], specs)
    return maximum_supported_demand(
        prep, MSDQuery(prep.demand_sets["d"], alpha_tolerance=0.25)
    )


def test_one_weighted_source_controller_is_proved_and_two_are_not():
    single = weighted(1)
    # x = 11: H(11, [1, 3]) = [3, 8] fits links of 3 and 8; x = 12 gives [3, 9].
    assert (single.proof, single.monotone_proven) == ("single_controller", True)
    assert single.alpha_feasible.value == 2.75
    assert single.upper_certificate is not None
    double = weighted(2)
    assert (double.proof, double.upper_certificate) == ("unproved", None)


POOL = [("S1", "X", 60), ("S2", "X", 50), ("X", "T", 70), ("S1", "T", 30, 4)]


def test_a_lossless_pool_in_msd_is_unproved_and_drops_nothing():
    prep = physical(
        POOL, [DemandSpec(Selector("^S"), Selector("^T$"), 40, TE16, id="p")]
    )
    (pooled,) = prep.demand_sets["d"].demands
    assert pooled.pool.offer_limit_units == 0
    result = maximum_supported_demand(
        prep, MSDQuery(prep.demand_sets["d"], export_probe_rows=True)
    )
    assert (result.proof, result.monotone_proven) == ("unproved", False)
    assert result.upper_certificate is None
    # The maximum flow is 70 + 30 = 100 units: 2.5078125 x 40 rounds to 100.
    assert result.alpha_feasible.value == 2.5078125
    for rows in result.probe_rows.values():
        for row in rows:
            assert (row.result.source_drops, list(row.result.edge_drops)) == (0, [])
    assert any(isinstance(ref, SyntheticIngress) for ref in prep.topology.edge_refs)


ARRAYS = ("edge_flows", "residual", "edge_reservations", "saturated_boundary_edges")
WITH_ARRAYS = ngc.OutputOptions(
    edge_flows=True,
    residual=True,
    edge_reservations=True,
    saturated_boundary_edges=True,
)


def fields(result):
    plan = result.plan
    return (
        result.requested,
        result.offered,
        result.admitted,
        result.delivered,
        result.unadmitted,
        result.source_drops,
        list(result.edge_drops),
        result.termination,
        [
            (
                s.source,
                s.offered,
                s.admitted,
                s.delivered,
                s.source_drops,
                s.total_edge_drops,
            )
            for s in result.by_source
        ],
        [
            (t.entry_id, t.head, t.status, t.assigned, t.delivered, t.total_edge_drops)
            for t in result.by_tunnel
        ],
        result.total_cost,
        # The call's own amounts and change flags: a stale hold left by an earlier probe
        # shows in the call fields even when the totals agree.
        result.call_delivered,
        result.call_undelivered,
        result.delivery_delta,
        list(result.call_edge_drops),
        result.call_source_drops,
        result.routes_changed,
        result.weights_changed,
        result.reservations_changed,
        None
        if result.marginal_cost_curve is None
        else [(p.marginal_cost, p.units) for p in result.marginal_cost_curve],
        None if result.min_cut is None else list(result.min_cut),
        None if result.program is None else len(result.program.tunnels),
        # Record counts and the requested native arrays.
        len(result.by_source),
        len(result.by_tunnel),
        *(
            None if (array := getattr(result, name)) is None else list(array)
            for name in ARRAYS
        ),
        None
        if plan is None
        else (
            plan.tunnels_per_head,
            plan.max_bandwidth_per_tunnel,
            plan.planned_bandwidth_per_tunnel,
            plan.max_lossless_offer,
            plan.total_tunnel_cost,
            plan.headroom_penalty,
            plan.design_demand,
            repr(plan.design_by_head),
            repr(plan.heads_with_capacity),
            plan.insufficient_resolution,
            str(plan.max_fractional_bandwidth_per_tunnel),
            plan.total_planned_bandwidth,
            plan.total_reserved_bandwidth,
        ),
    )


def two_controlled():
    # Two controlled demands S -> T through X (links of 10), the second after the first.
    return prepared(
        [("S", "X", 10), ("X", "T", 10)],
        "^X$",
        "^(S|T)$",
        [demand("^S$", "^T$", 4, id="a"), demand("^S$", "^T$", 4, id="b", priority=1)],
        q=1,
    )


def two_pools():
    specs = [
        DemandSpec(Selector("^S$"), Selector("^T$"), 40, TE16, id="p1"),
        DemandSpec(Selector("^S$"), Selector("^T$"), 40, TE16, id="p2", priority=1),
    ]
    return physical([("S", "T", 100)], specs)


@pytest.mark.parametrize(
    ("make", "history", "deliveries"),
    [
        (
            two_controlled,
            [
                (1.0, "feasible"),
                (2.0, "infeasible"),
                (1.5, "infeasible"),
                (1.25, "feasible"),
            ],
            [[4, 4], [8, 2], [6, 4], [5, 5]],
        ),
        (
            two_pools,
            None,
            # Alpha 2: the second pool sees residual 20; U = floor(20 / 16) = 1, F = 20.
            [[40, 40], [80, 20]],
        ),
    ],
)
def test_every_probe_starts_from_an_empty_ledger(
    monkeypatch, make, history, deliveries
):
    # MSD asks no native arrays; here every probe asks the flows, residual capacity and
    # reservations, so the retained rows can be compared with a fresh ledger's in full.
    from ngraph.analysis import msd

    apply = msd._apply_matrix
    monkeypatch.setattr(
        msd,
        "_apply_matrix",
        lambda ledger, owners, requests: apply(ledger, owners, requests, WITH_ARRAYS),
    )
    prep = make()
    demands = prep.demand_sets["d"]
    result = maximum_supported_demand(
        prep, MSDQuery(demands, alpha_tolerance=0.25, export_probe_rows=True)
    )
    if history is not None:
        assert [(p.alpha.value, p.outcome) for p in result.history] == history
    probes = sorted(result.probe_rows.items())
    assert [[r.result.delivered for r in rows] for _, rows in probes][
        : len(deliveries)
    ] == deliveries
    for index, rows in probes:
        alpha = result.history[index].alpha.value
        fresh = place(
            prep,
            PlacementQuery(
                demands,
                alpha=alpha,
                states=("converged",),
                workers=1,
                outputs=WITH_ARRAYS,
            ),
        )
        assert all(
            getattr(r.result, name) is not None for r in rows for name in ARRAYS[:3]
        )
        assert [fields(r.result) for r in rows] == [
            fields(r.result) for r in fresh.cases[0].states["converged"].rows
        ]


def test_trivial_and_range_statuses_on_a_controlled_set():
    zero = scope("next_hop", volume=0)
    result = maximum_supported_demand(zero, MSDQuery(zero.demand_sets["d"]))
    assert (result.proof, result.search_status, result.stop_reason) == (
        "declared_zero",
        "trivial",
        "declared_zero",
    )
    assert [p.outcome for p in result.history] == ["feasible"]
    big = scope("next_hop")
    result = maximum_supported_demand(
        big, MSDQuery(big.demand_sets["d"], alpha_start=1e17, alpha_max=1e18)
    )
    assert (result.proof, result.search_status, result.stop_reason) == (
        "fixed_program",
        "range",
        "offer_range",
    )
    assert result.alpha_feasible is None
    refusal = result.history[0].range_refusal
    assert (refusal.label, refusal.reason) == (
        "demand.d|0.volume",
        "native_units_range",
    )


def test_a_pool_that_cannot_lay_out_its_tunnels_has_no_feasible_alpha():
    weak = [("S1", "X", 6), ("S2", "X", 5), ("X", "T", 7), ("S1", "T", 3, 4)]
    prep = physical(
        weak, [DemandSpec(Selector("^S"), Selector("^T$"), 4, TE16, id="p")]
    )
    result = maximum_supported_demand(
        prep, MSDQuery(prep.demand_sets["d"], alpha_tolerance=0.25)
    )
    # 16 one-unit tunnels need a flow of 16 > 10: U = 0 at every design, nothing admitted.
    assert (result.proof, result.search_status, result.alpha_feasible) == (
        "unproved",
        "none_feasible",
        None,
    )
    assert result.stop_reason == "unit_resolution"
    assert [p.outcome for p in result.history] == [
        "infeasible",
        "infeasible",
        "infeasible",
        "infeasible",
        "below_resolution",
    ]
