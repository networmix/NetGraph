"""Simultaneous placement: one native SIMULTANEOUS list per case and state.

Every participant forwards LOSSY on a fixed program: models that can be LOSSY
join as LOSSY copies (tunnel models set up first, then forwarded), live
controllers are prepared, exported and imported as LOSSY Pinned. Expected values
are derived by hand in each test.
"""

from __future__ import annotations

import itertools

import netgraph_core as ngc
import pytest

import ngraph.analysis.placement as placement
from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Network,
    Node,
    PinnedRoutes,
    PlacementQuery,
    RouteSpec,
    Scenario,
    Selector,
    UnitsSettings,
    place,
    prepare,
    run,
)
from ngraph.analysis.topology import compile_topology
from ngraph.model.network import DirectedLink, Link
from ngraph.results import ForwardingFailure, SyntheticIngress
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement
from tests.analysis.test_failure_states import (
    ALL,
    PERIOD_2,
    ROUND_LIMIT,
    demand,
    links_failing,
    prepared,
)
from tests.controller.test_failure_tables import r30, request

LOSSY = ngc.Admission.LOSSY


def simultaneous(prep, failures=None, states=("converged", "stale"), **kw):
    query = PlacementQuery(
        prep.demand_sets["d"],
        failures=failures,
        workers=1,
        states=states,
        interaction="simultaneous",
        **kw,
    )
    return place(prep, query)


def delivered(state):
    return [row.result.delivered for row in state.rows]


def test_interaction_defaults_to_ordered_and_refuses_other_values():
    prep = prepared([("S", "T", 10)], [demand("^S$", "^T$", 4)])
    assert PlacementQuery(prep.demand_sets["d"]).interaction == "ordered"
    with pytest.raises(ValueError, match="placement.interaction: expected ordered"):
        PlacementQuery(prep.demand_sets["d"], interaction="parallel")
    with pytest.raises(ValueError, match="workflow.tm.interaction: expected ordered"):
        TrafficMatrixPlacement(name="tm", demand_set="d", interaction="parallel")


def test_one_list_shares_losses_where_the_ordered_list_gives_priority():
    # One link of 10, two ECMP demands of 10. Ordered: 10 and 0, and stale replays
    # offers 10 and 0. Simultaneous: 5 and 5 (CONTRACT D-simultaneous), stale 5/5.
    prep = prepared(
        [("S", "T", 10)],
        [
            demand("^S$", "^T$", 10, id="d1"),
            demand("^S$", "^T$", 10, id="d2", priority=1),
        ],
    )
    query = PlacementQuery(
        prep.demand_sets["d"], workers=1, states=["converged", "stale"]
    )
    ordered = place(prep, query).cases[0]
    assert [delivered(ordered.states[s]) for s in ("converged", "stale")] == [
        [10, 0]
    ] * 2
    (case,) = simultaneous(prep).cases
    assert [delivered(case.states[s]) for s in ("converged", "stale")] == [[5, 5]] * 2
    assert all(row.result.offered == 10 for row in case.states["converged"].rows)


def test_the_r30_lossy_figures_through_the_product():
    # LOSSY 300 over the four-branch domain: one member down 250 / 225 / 250; a whole
    # group down 150 in every state (caps kept, nothing spilled).
    prep = r30()
    one = simultaneous(prep, request("link", "^S\\|A1$"), states=ALL).cases[1]
    assert [delivered(one.states[s]) for s in ALL] == [[250], [225], [250]]
    for path in ("^S\\|A[12]$", "^S\\|A[34]$"):
        dead = simultaneous(prep, request("link", path), states=ALL).cases[1]
        assert [delivered(dead.states[s]) for s in ALL] == [[150], [150], [150]]


@pytest.mark.parametrize(
    "live",
    [FlowPolicyPreset.TE_MAXFLOW_UNLIM, FlowPolicyPreset.SHORTEST_PATHS_MAXFLOW],
)
def test_a_live_controller_is_imported_after_the_roster(live):
    # One link of 9; the live controller (priority 0) and ECMP (priority 1) offer 5
    # each. The controller is prepared, exported and imported as LOSSY Pinned,
    # created after the ECMP copy, so H(9, [5, 5]) gives the odd unit to ECMP. Stale
    # and repair create the controller's participant last too, so the baseline and a
    # failure case (the unused S-U fails) give 4 and 5 in every state.
    prep = prepared(
        [("S", "T", 9), ("S", "U", 1)],
        [
            demand("^S$", "^T$", 5, live, id="live"),
            demand("^S$", "^T$", 5, id="ecmp", priority=1),
        ],
    )
    analysis = simultaneous(prep, links_failing("^S\\|U$"), states=ALL)
    for case in analysis.cases:
        assert [delivered(case.states[s]) for s in ALL] == [[4, 5]] * 3
    controller = analysis.cases[0].states["converged"].rows[0].result
    assert controller.offered == 5
    ordered = place(
        prep, PlacementQuery(prep.demand_sets["d"], workers=1, states=["converged"])
    )
    assert delivered(ordered.cases[0].states["converged"]) == [5, 4]


def t1(count, admission):
    return ngc.FlowPolicyConfig(
        routing=ngc.DistributedTE(ngc.TunnelCount(count)), admission=admission
    )


def test_a_tunnel_model_is_set_up_on_the_ledger_and_keeps_its_holds():
    # One link of 10: the LOSSY T1 reserves 10 and a LOSSY pinned route offers 10;
    # forwarded together they share the link 5 and 5, the T1 hold stays.
    prep = prepared(
        [("S", "T", 10)],
        [
            demand("^S$", "^T$", 10, t1(1, LOSSY), id="t1"),
            demand(
                "^S$",
                "^T$",
                10,
                PinnedRoutes(("st",), admission=LOSSY),
                id="pin",
                priority=1,
            ),
        ],
        routes={"st": RouteSpec("S", nodes=("S", "T"))},
    )
    outputs = ngc.OutputOptions(edge_reservations=True)
    (case,) = simultaneous(prep, states=["converged"], outputs=outputs).cases
    tunnel, pinned = (row.result for row in case.states["converged"].rows)
    assert (tunnel.delivered, pinned.delivered) == (5, 5)
    forward = prep.topology.edges_by_link["S|T|0"][0]
    assert tunnel.edge_reservations[forward] == 10


@pytest.mark.parametrize("tunnels", ["T1", "T2"])
def test_a_lossless_tunnel_model_joins_as_a_lossy_copy(tunnels):
    # S-A-T (cost 2) and S-B-T (cost 4), links 10. d1, two tunnels for 12, joins as a
    # LOSSY copy: its setup reserves 6 per tunnel (T1); beside an ECMP offer of 10 the
    # list gives d1 10 and d2 6. An import would hold none.
    model = (
        ngc.DistributedTE(ngc.TunnelCount(2))
        if tunnels == "T1"
        else ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(2),
        )
    )
    links = [("S", "A", 10, 1), ("A", "T", 10, 1), ("S", "B", 10, 2), ("B", "T", 10, 2)]
    prep = prepared(
        links,
        [
            demand("^S$", "^T$", 12, ngc.FlowPolicyConfig(routing=model), id="d1"),
            demand(
                "^S$",
                "^T$",
                10,
                FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
                id="d2",
                priority=1,
            ),
        ],
    )
    outputs = ngc.OutputOptions(edge_reservations=True)
    (case,) = simultaneous(prep, states=["converged"], outputs=outputs).cases
    rows = {row.id: row.result for row in case.states["converged"].rows}
    assert (rows["d1|0"].delivered, rows["d2|0"].delivered) == (10, 6)
    assert rows["d1|0"].plan is not None
    held = [
        int(
            rows["d1|0"].edge_reservations[prep.topology.edges_by_link[f"{u}|{v}|0"][0]]
        )
        for u, v, *_ in links
    ]
    assert held == ([6, 6, 6, 6] if tunnels == "T1" else [0, 0, 0, 0])


RESIDUAL = ngc.FlowPolicyConfig(
    routing=ngc.ShortestPaths(
        allocation=ngc.RouteAllocation.WEIGHTED,
        weight_basis=ngc.WeightBasis.RESIDUAL_SNAPSHOT,
    ),
    admission=LOSSY,
)
AVAILABLE = ngc.FlowPolicyConfig(
    routing=ngc.ShortestPaths(
        multipath=False, tie_break=ngc.RouteTieBreak.HIGHER_AVAILABLE_CAPACITY
    ),
    admission=LOSSY,
)


def permutation_fixtures():
    two = [("S", "T", 10), ("S", "T", 10)]
    pinned = PinnedRoutes(("st",), admission=LOSSY)
    yield (
        "residual snapshot",
        prepared(
            two,
            [
                demand("^S$", "^T$", 10, RESIDUAL, id="a"),
                demand("^S$", "^T$", 10, RESIDUAL, id="b"),
            ],
        ),
        None,
    )
    yield (
        "available tie",
        prepared(
            two,
            [
                demand("^S$", "^T$", 10, AVAILABLE, id="a"),
                demand("^S$", "^T$", 10, AVAILABLE, id="b"),
            ],
        ),
        None,
    )
    yield (
        "pinned and t1",
        prepared(
            [("S", "T", 10)],
            [
                demand("^S$", "^T$", 10, t1(1, LOSSY), id="t"),
                demand("^S$", "^T$", 10, pinned, id="p"),
            ],
            routes={"st": RouteSpec("S", nodes=("S", "T"))},
        ),
        None,
    )
    yield "r30 stale programs", r30(), request("link", "^S\\|A1$")
    # T1C: T1 with two LOSSLESS tunnels for 12, an ECMP LOSSY copy and a pinned route.
    square = [
        ("S", "A", 10, 1),
        ("A", "T", 10, 1),
        ("S", "B", 10, 2),
        ("B", "T", 10, 2),
    ]
    yield (
        "t1c, ecmp and pinned",
        prepared(
            square,
            [
                demand("^S$", "^T$", 12, t1(2, ngc.Admission.LOSSLESS), id="d1"),
                demand(
                    "^S$",
                    "^T$",
                    10,
                    FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
                    id="d2",
                    priority=1,
                ),
                demand(
                    "^S$",
                    "^T$",
                    4,
                    PinnedRoutes(("sbt",), admission=LOSSY),
                    id="d3",
                    priority=2,
                ),
            ],
            routes={"sbt": RouteSpec("S", nodes=("S", "B", "T"))},
        ),
        links_failing("^A\\|T$"),
    )
    yield (
        "live controller among direct members",
        prepared(
            [("S", "T", 9)],
            [
                demand("^S$", "^T$", 5, FlowPolicyPreset.TE_MAXFLOW_UNLIM, id="te"),
                demand("^S$", "^T$", 5, id="ecmp", priority=1),
                demand("^S$", "^T$", 3, pinned, id="pin", priority=2),
            ],
            routes={"st": RouteSpec("S", nodes=("S", "T"))},
        ),
        None,
    )


def permuted(order, real=ngc.apply_actions):
    """``apply_actions`` submitting a SIMULTANEOUS list in ``order``; results in list order."""

    def apply(ledger, actions, *, mode, outputs=None):
        if mode != ngc.BatchMode.SIMULTANEOUS:
            return real(ledger, actions, mode=mode, outputs=outputs)
        listed = real(ledger, [actions[i] for i in order], mode=mode, outputs=outputs)
        by_position = dict(zip(order, listed, strict=True))
        return tuple(by_position[i] for i in range(len(actions)))

    return apply


def signature(analysis):
    return [
        [
            (
                name,
                row.id,
                row.result.delivered,
                row.result.edge_drops,
                row.result.source_drops,
                tuple(row.result.edge_flows),
            )
            for name, state in case.states.items()
            for row in state.rows
        ]
        for case in analysis.cases
    ]


def test_permuting_the_submitted_participants_changes_nothing(monkeypatch):
    # The common view (CONTRACT 11.2): residual-snapshot weights and availability ties
    # are read once for every participant; ties follow creation order, never the list.
    outputs = ngc.OutputOptions(edge_flows=True)
    for name, prep, failures in permutation_fixtures():
        expected = signature(simultaneous(prep, failures, states=ALL, outputs=outputs))
        if name == "residual snapshot":
            rows = [
                r.result
                for r in simultaneous(prep, outputs=outputs)
                .cases[0]
                .states["converged"]
                .rows
            ]
            assert [r.delivered for r in rows] == [10, 10]
            assert [sorted(int(x) for x in r.edge_flows if x) for r in rows] == [
                [5, 5],
                [5, 5],
            ]
        if name == "available tie":
            # Both read the same view and pick the same link: 5 and 5 on it.
            rows = [
                r.result
                for r in simultaneous(prep, outputs=outputs)
                .cases[0]
                .states["converged"]
                .rows
            ]
            assert [r.delivered for r in rows] == [5, 5]
            used = [[e for e, x in enumerate(r.edge_flows) if x] for r in rows]
            assert used[0] == used[1] and len(used[0]) == 1
        n = len(prep.demand_sets["d"].demands)
        for order in itertools.permutations(range(n)):
            monkeypatch.setattr(ngc, "apply_actions", permuted(order))
            assert (
                signature(simultaneous(prep, failures, states=ALL, outputs=outputs))
                == expected
            ), (name, order)
        monkeypatch.undo()
    # A failed list leaves nothing behind; the retry gives the same answer.
    prep = r30()
    calls = []
    real = ngc.apply_actions

    def fail_once(ledger, actions, *, mode, outputs=None):
        if mode == ngc.BatchMode.SIMULTANEOUS and not calls:
            calls.append(1)
            raise MemoryError("planted")
        return real(ledger, actions, mode=mode, outputs=outputs)

    monkeypatch.setattr(ngc, "apply_actions", fail_once)
    with pytest.raises(MemoryError):
        simultaneous(prep, request("link", "^S\\|A1$"), states=ALL, outputs=outputs)
    assert signature(
        simultaneous(prep, request("link", "^S\\|A1$"), states=ALL, outputs=outputs)
    ) == signature(
        place(
            prep,
            PlacementQuery(
                prep.demand_sets["d"],
                failures=request("link", "^S\\|A1$"),
                workers=1,
                states=ALL,
                interaction="simultaneous",
                outputs=outputs,
            ),
        )
    )


DC_LINKS = [("P", "Q", 1), ("Q", "R", 10), ("R", "S", 2), ("S", "P", 10), ("W", "P", 9)]
DC_ROUTES = {
    "a": RouteSpec("P", nodes=("P", "Q", "R", "S")),
    "b": RouteSpec("R", nodes=("R", "S", "P", "Q")),
    "z": RouteSpec("W", nodes=("W", "P", "Q")),
}


def ring(z_volume):
    def lossy(name):
        return PinnedRoutes((name,), admission=LOSSY)

    return prepared(
        DC_LINKS,
        [
            demand("^P$", "^S$", 1, lossy("a"), id="a"),
            demand("^R$", "^Q$", 2, lossy("b"), id="b"),
            demand("^W$", "^Q$", z_volume, lossy("z"), id="z"),
        ],
        routes=DC_ROUTES,
    )


def test_a_simultaneous_cycle_is_that_case_and_states_outcome():
    # The D-C2 ring plus Z on its own link W-P: Z's load settles the baseline
    # (A 0, B 1, Z 0); with W-P failed Z's traffic is dead and the ring cycles.
    analysis = simultaneous(ring(2), links_failing("^W\\|P$"))
    assert delivered(analysis.cases[0].states["converged"]) == [0, 1, 0]
    for name in ("converged", "stale"):
        state = analysis.cases[1].states[name]
        assert state.failure == ForwardingFailure(PERIOD_2)
        assert state.rows == () and state.totals is None


def test_a_simultaneous_baseline_outcome_with_converged_only():
    # With Z's volume 1 the baseline cycles. Converged alone records it; the P-Q case
    # fails every route, whose heads then reach nothing: NO_ROUTE, source drops 1, 2, 1.
    prep = ring(1)
    with pytest.raises(ValueError, match="case baseline: " + PERIOD_2):
        simultaneous(prep, links_failing("^P\\|Q$"))
    analysis = simultaneous(prep, links_failing("^P\\|Q$"), states=["converged"])
    assert analysis.cases[0].states["converged"].failure == ForwardingFailure(PERIOD_2)
    rows = [row.result for row in analysis.cases[1].states["converged"].rows]
    assert [(r.delivered, r.source_drops, r.termination) for r in rows] == [
        (0, 1, ngc.Termination.NO_ROUTE),
        (0, 2, ngc.Termination.NO_ROUTE),
        (0, 1, ngc.Termination.NO_ROUTE),
    ]


def test_precision_reads_the_common_view_in_a_simultaneous_list():
    # a is pinned to the second link and fills it (20 of 20); b weighs both links by
    # residual snapshot and sends one unit, which H puts on the first link. Ordered:
    # b reads the second link's residual 0, prunes it and does not split. In one
    # simultaneous list b reads the common view (a released): two members, as b
    # alone. Reading a's flow out of the view would prune the second link again.
    links = [("S", "T", 20), ("S", "T", 20)]
    second = DirectedLink("S|T|1", "forward")
    pinned = PinnedRoutes(("a",), admission=LOSSY)
    routes = {"a": RouteSpec("S", edges=(second,))}
    both = prepared(
        links,
        [
            demand("^S$", "^T$", 20, pinned, id="a"),
            demand("^S$", "^T$", 1, RESIDUAL, id="b", priority=1),
        ],
        routes=routes,
    )
    alone = prepared(links, [demand("^S$", "^T$", 1, RESIDUAL, id="b")])

    def bounds(analysis):
        return sorted(
            c.q_upper_bound
            for miss in analysis.misses
            for c in miss.constraints
            if getattr(c, "kind", None) == "router" and c.label.startswith("demand.b")
        )

    ordered = place(
        both, PlacementQuery(both.demand_sets["d"], workers=1, states=["converged"])
    )
    together = simultaneous(both, states=["converged"])
    single = place(
        alone, PlacementQuery(alone.demand_sets["d"], workers=1, states=["converged"])
    )
    rows = together.cases[0].states["converged"].rows
    assert [r.result.delivered for r in rows] == [20, 1]
    assert bounds(ordered) == []
    assert bounds(together) == bounds(single) != []


# --- pool offer budgets ------------------------------------------------------------------------------------------


def test_a_pool_budget_lets_a_lossy_offer_pass_its_attachment():
    # Head h over source s; s-T 1 (cost 1) and s-T 100 (cost 2): B_s = 101. Two tunnels
    # sized for 2 take one route each; a LOSSY offer of 1,000 splits 500/500. Through
    # an attachment of 101 each tunnel gets about 50: 1 + 50 = 51. With the budget
    # 1,000 the attachment passes it all: 1 + 100 = 101, nothing dropped on it.
    net = Network(nodes={"s": Node("s"), "T": Node("T")})
    net.add_link(Link("s", "T", 1, 1))
    net.add_link(Link("s", "T", 100, 2))
    tunnels = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(2),
        ),
        admission=LOSSY,
    )
    got = {}
    for budget in (0, 1000):
        topology = compile_topology(net, 1, pools={"p": ("s",)}, budgets={"p": budget})
        assert topology.pool_budgets == {"p": budget}
        ledger = ngc.FlowLedger(topology.graph)
        policy = ngc.FlowPolicy(
            ledger, [topology.pool_heads["p"]], [topology.node_id_by_name["T"]], tunnels
        )
        try:
            policy.replace(2, design_demand=2)
            (result,) = ngc.apply_actions(
                ledger, [ngc.Forward(policy, 1000)], mode=ngc.BatchMode.SIMULTANEOUS
            )
        finally:
            policy.remove()
        attachment = next(
            e
            for e, ref in enumerate(topology.edge_refs)
            if isinstance(ref, SyntheticIngress)
        )
        got[budget] = (result.delivered, dict(result.edge_drops).get(attachment, 0))
    assert got[0][0] == 51 and got[0][1] > 0
    assert got[1000] == (101, 0)


def pool_scenario(volume, steps, group_mode="per_group", units=None):
    """A TE_ECMP_16_LSP combine over S0, S1, S2 (one pool per source with per_group)."""
    sources = ("S0", "S1", "S2")
    net = Network(nodes={name: Node(name) for name in (*sources, "T")})
    for source in sources:
        net.add_link(Link(source, "T", 200, 1))
    spec = DemandSpec(
        Selector("^S", group_by="name"),
        Selector("^T$"),
        volume,
        FlowPolicyPreset.TE_ECMP_16_LSP,
        id="pooled",
        mode="combine",
        group_mode=group_mode,
    )
    return Scenario(
        net,
        tuple(steps),
        demand_sets={"d": DemandSet("d", (spec,))},
        units=units or UnitsSettings(1),
    )


def step(name, **kw):
    return TrafficMatrixPlacement(
        name=name, demand_set="d", workers=1, interaction="simultaneous", **kw
    )


def test_pool_budgets_come_from_the_runs_own_expansion():
    # Volume 1 over three pooled sources at q = 1: the run's split gives 1, 0, 0, so
    # the budgets are [1, 0, 0] (rounding each third alone would give [0, 0, 0] and
    # refuse the first). Volume 10 with steps at alpha 1 and 0.5: requests 4, 3, 3
    # and 2, 2, 1; budgets [4, 3, 3].
    value = pool_scenario(1, [step("tm")])
    prep = prepare(value)
    assert [d.pool.offer_limit_units for d in prep.demand_sets["d"].demands] == [
        1,
        0,
        0,
    ]
    rows = run(prep).steps[0].result.cases[0].states["converged"].rows
    assert [r.result.delivered for r in rows] == [1, 0, 0]
    value = pool_scenario(10, [step("one", alpha=1.0), step("half", alpha=0.5)])
    prep = prepare(value)
    assert [d.pool.offer_limit_units for d in prep.demand_sets["d"].demands] == [
        4,
        3,
        3,
    ]
    for result in run(prep).steps:
        for row in result.result.cases[0].states["converged"].rows:
            assert row.result.source_drops == 0 and not row.result.edge_drops


def test_pool_budgets_refuse_unknown_and_larger_offers():
    # A simultaneous scale from an MSD step is unknown at preparation; a library
    # query above the prepared budget is refused at run.
    msd = MaximumSupportedDemand(name="msd", demand_set="d")
    value = pool_scenario(10, [msd, step("tm", alpha_from_step="msd")])
    with pytest.raises(
        ValueError,
        match="workflow.tm.interaction: demand pooled\\|0: its scale comes from MSD step "
        "msd, unknown at preparation, so TE ingress pool pooled\\|0 has no lossy offer budget",
    ):
        prepare(value)
    value = pool_scenario(10, [step("tm", alpha=1.0)])
    prep = prepare(value)
    with pytest.raises(
        ValueError,
        match="placement.interaction: demand pooled\\|0: offer 7 units exceeds the "
        "prepared lossy budget 4 units of TE ingress pool pooled\\|0",
    ):
        place(
            prep,
            PlacementQuery(
                prep.demand_sets["d"], alpha=2.0, interaction="simultaneous", workers=1
            ),
        )
    # Ordered placement needs no budget; an ordered-only preparation keeps budgets 0.
    ordered = prepare(
        pool_scenario(
            10, [TrafficMatrixPlacement(name="tm", demand_set="d", workers=1)]
        )
    )
    assert [d.pool.offer_limit_units for d in ordered.demand_sets["d"].demands] == [
        0,
        0,
        0,
    ]
    place(ordered, PlacementQuery(ordered.demand_sets["d"], alpha=2.0, workers=1))


def test_an_msd_scaled_simultaneous_step_without_a_pool_runs():
    # The pooled demand's sources select nothing, so no pool needs a budget: the
    # MSD-scaled simultaneous step prepares and runs like the ordered one.
    net = Network(nodes={name: Node(name) for name in ("S", "T", "U")})
    net.add_link(Link("S", "T", 100, 1))
    net.add_link(Link("U", "T", 100, 1))
    specs = (
        DemandSpec(Selector("^S$"), Selector("^T$"), 10, id="plain"),
        DemandSpec(
            Selector("^NONE"),
            Selector("^T$"),
            10,
            FlowPolicyPreset.TE_ECMP_16_LSP,
            id="pooled",
            mode="combine",
        ),
    )
    msd = MaximumSupportedDemand(name="msd", demand_set="d")
    value = Scenario(
        net,
        (msd, step("tm", alpha_from_step="msd")),
        demand_sets={"d": DemandSet("d", specs)},
        units=UnitsSettings(1),
    )
    rows = run(prepare(value)).steps[1].result.cases[0].states["converged"].rows
    assert [row.id for row in rows] == ["plain|0"]


def test_a_budget_counts_in_the_range_check():
    # One pool over three sources with volume 2^61: each attachment carries the whole
    # budget, so the augmented capacity sum is about 3 * 2^61 / q. The precision
    # target wants q <= 0.25 (links of 200); the budget needs q >= 2, so preparation
    # keeps the finest range-valid q and reports the capacity sum as binding.
    volume = float(2**61)
    auto = UnitsSettings("auto")
    ordered = TrafficMatrixPlacement(name="tm", demand_set="d", workers=1)
    plain = prepare(pool_scenario(volume, [ordered], "flatten", auto))
    lossy = prepare(pool_scenario(volume, [step("tm")], "flatten", auto))
    assert lossy.topology.q > plain.topology.q
    assert int(lossy.topology.graph.edge_capacity_units().sum()) < 2**62
    (pooled,) = lossy.demand_sets["d"].demands
    assert pooled.pool.offer_limit_units > 0
    assert any(
        c.label == "topology.augmented_capacity_sum"
        for c in lossy.units_report.binding_constraints
    )


def test_automatic_resolution_passes_a_q_whose_budget_does_not_fit():
    # Volume 1 at the known alpha 2^62 in one pool over three sources: at q = 1 the
    # budget 2^62 is outside the native range, which rejects that q like any other
    # range failure; the search goes on to the legal q = 4 (budget 2^60).
    args = (1, [step("tm", alpha=float(2**62))], "flatten")
    explicit = prepare(pool_scenario(*args, UnitsSettings(4)))
    automatic = prepare(pool_scenario(*args, UnitsSettings("auto")))
    for prep in (explicit, automatic):
        assert prep.topology.q == 4
        (pooled,) = prep.demand_sets["d"].demands
        assert pooled.pool.offer_limit_units == 2**60
    assert int(automatic.topology.graph.edge_capacity_units().sum()) < 2**62


def test_the_range_check_counts_only_what_a_budget_adds():
    # Each source also has a link of capacity 1e17, so its outgoing capacity exceeds
    # the budget 9e16: the budgets add nothing to the attachments, and the
    # simultaneous step keeps the ordered step's q.
    net = Network(nodes={n: Node(n) for n in ("S0", "S1", "S2", "T", "X0", "X1", "X2")})
    for i in range(3):
        net.add_link(Link(f"S{i}", "T", 200, 1))
        net.add_link(Link(f"S{i}", f"X{i}", 1.0e17, 1))
    spec = DemandSpec(
        Selector("^S"),
        Selector("^T$"),
        9.0e16,
        FlowPolicyPreset.TE_ECMP_16_LSP,
        id="pooled",
        mode="combine",
    )
    chosen = []
    for interaction in ("ordered", "simultaneous"):
        placement = TrafficMatrixPlacement(
            name="tm", demand_set="d", workers=1, interaction=interaction
        )
        value = Scenario(
            net,
            (placement,),
            demand_sets={"d": DemandSet("d", (spec,))},
            units=UnitsSettings("auto"),
        )
        chosen.append(prepare(value).topology.q)
    assert chosen == [0.25, 0.25]


def test_imports_are_released_when_a_list_fails_and_a_retry_matches(monkeypatch):
    # A live controller's program is imported into a LOSSY participant created after
    # the roster. Every created policy, the imports included, is removed and holds no
    # program after the run, whichever list fails (setup or simultaneous, any case
    # and state), and a retry gives the clean answer.
    prep = prepared(
        [("S", "T", 9), ("S", "U", 1)],
        [
            demand("^S$", "^T$", 5, FlowPolicyPreset.TE_MAXFLOW_UNLIM, id="te"),
            demand("^S$", "^T$", 5, id="ecmp", priority=1),
        ],
    )
    outputs = ngc.OutputOptions(edge_flows=True)

    def go():
        return simultaneous(prep, links_failing("^S\\|U$"), states=ALL, outputs=outputs)

    fresh = signature(go())
    created, removed, calls = [], [], []
    real, real_apply = ngc.FlowPolicy, ngc.apply_actions
    original_remove = placement.remove_policies
    monkeypatch.setattr(
        placement,
        "remove_policies",
        lambda owners: removed.extend(owners) or original_remove(owners),
    )

    def recording(*args):
        policy = real(*args)
        created.append(policy)
        return policy

    def apply(ledger, actions, *, mode, outputs=None):
        calls.append(mode)
        if len(calls) == fail_at:
            raise MemoryError("planted")
        return real_apply(ledger, actions, mode=mode, outputs=outputs)

    monkeypatch.setattr(ngc, "FlowPolicy", recording)
    monkeypatch.setattr(ngc, "apply_actions", apply)
    fail_at = None
    go()
    lists = len(calls)
    assert ngc.BatchMode.ORDERED in calls and len(created) == 2 * (2 + 1 + 2 + 2)
    for fail_at in (*range(1, lists + 1), None):
        created.clear(), removed.clear(), calls.clear()
        if fail_at is None:
            assert signature(go()) == fresh
        else:
            with pytest.raises(MemoryError):
                go()
        assert created and {id(p) for p in created} <= {id(p) for p in removed}
        assert all(policy.program is None for policy in created)


@pytest.mark.parametrize(
    ("interaction", "mode"),
    [
        ("ordered", ngc.BatchMode.ORDERED),
        ("simultaneous", ngc.BatchMode.ORDERED),
        ("simultaneous", ngc.BatchMode.SIMULTANEOUS),
    ],
)
@pytest.mark.parametrize("target", ALL)
def test_a_loss_iteration_outcome_belongs_to_its_case_and_state(
    monkeypatch, interaction, mode, target
):
    # The round-limit outcome raised by the failure case's list of one state (in a
    # simultaneous converged state, also by the live controller's setup list) is that
    # case and state's outcome: no rows, no totals; every policy is released and a
    # retry gives the clean answer.
    prep = prepared(
        [("S", "T", 9), ("S", "U", 1)],
        [
            demand("^S$", "^T$", 5, FlowPolicyPreset.TE_MAXFLOW_UNLIM, id="te"),
            demand("^S$", "^T$", 5, id="ecmp", priority=1),
        ],
    )
    outputs = ngc.OutputOptions(edge_flows=True)
    query = PlacementQuery(
        prep.demand_sets["d"],
        failures=links_failing("^S\\|U$"),
        workers=1,
        states=ALL,
        interaction=interaction,
        outputs=outputs,
    )
    fresh = signature(place(prep, query))
    current, created = {}, []
    real, real_apply, real_state = (
        ngc.FlowPolicy,
        ngc.apply_actions,
        placement._place_state,
    )

    def tracking(prepared, query, case, state, *rest):
        current.update(kind=case.kind, state=state)
        return real_state(prepared, query, case, state, *rest)

    def recording(*args):
        created.append(real(*args))
        return created[-1]

    def apply(ledger, actions, *, mode, outputs=None, raises=mode):
        if (current["kind"], current["state"], mode) == ("failure", target, raises):
            raise ValueError(ROUND_LIMIT)
        return real_apply(ledger, actions, mode=mode, outputs=outputs)

    monkeypatch.setattr(placement, "_place_state", tracking)
    monkeypatch.setattr(ngc, "FlowPolicy", recording)
    monkeypatch.setattr(ngc, "apply_actions", apply)
    analysis = place(prep, query)
    monkeypatch.undo()
    assert all(policy.program is None for policy in created)
    raised = interaction == "ordered" or mode == ngc.BatchMode.SIMULTANEOUS
    raised = raised or target == "converged"  # only converged sets up the controller
    for case in analysis.cases:
        for name, state in case.states.items():
            if (case.case.kind, name) == ("failure", target) and raised:
                assert state.failure == ForwardingFailure(ROUND_LIMIT)
                assert state.rows == () and state.totals is None
            else:
                assert state.failure is None and state.rows
    assert signature(place(prep, query)) == fresh


def test_without_a_budget_the_range_screen_scans_no_link(monkeypatch):
    # Outgoing capacities enter the range screen only through a pool budget: an
    # ordered step (no budget) never scans the links; a simultaneous one does.
    import ngraph.analysis.preparation as preparation

    scans = []
    original = preparation.outgoing_units
    monkeypatch.setattr(
        preparation,
        "outgoing_units",
        lambda network, q: scans.append(q) or original(network, q),
    )
    ordered = TrafficMatrixPlacement(name="tm", demand_set="d", workers=1)
    auto = UnitsSettings("auto")
    prepare(pool_scenario(10, [ordered], "flatten", auto))
    assert scans == []
    prepare(pool_scenario(10, [step("tm")], "flatten", auto))
    assert scans
