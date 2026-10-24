"""Failure states of placement: converged, stale and repair on hand-derived networks.

Stale forwards each demand's baseline program unchanged, LOSSY, at its baseline
admitted total, with the case's failures as black holes; repair forwards the
baseline program under the failure mask at the declared request; converged
computes the declared demands again on the failed network. Every expected
value below is derived by hand in its comment.
"""

from __future__ import annotations

from fractions import Fraction

import jsonschema
import netgraph_core as ngc
import pytest

import ngraph.analysis.placement as placement
import ngraph.analysis.states as states_module
from ngraph import (
    Condition,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRule,
    FlowPolicyPreset,
    Link,
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
)
from ngraph.analysis.failures import FailureRequest
from ngraph.results import ForwardingFailure
from tests.results.test_analysis_wire import project

ALL = ("converged", "stale", "repair")
PERIOD_2 = "lossy forwarding iteration entered a period-2 cycle"
ROUND_LIMIT = (
    "lossy forwarding iteration did not reach a fixed point within the round limit"
)


def network(links, disabled=()):
    """Physical links (source, target, capacity[, cost[, attrs]])."""
    names = sorted({u for u, v, *_ in links} | {v for u, v, *_ in links})
    net = Network(nodes={name: Node(name) for name in names})
    for u, v, capacity, *rest in links:
        cost = rest[0] if rest else 1
        attrs = rest[1] if len(rest) > 1 else {}
        net.add_link(Link(u, v, capacity, cost, attrs=attrs))
    for link in disabled:
        net.disable_link(link)
    return net


def prepared(links, demands, *, routes=None, disabled=()):
    return prepare(
        Scenario(
            network(links, disabled),
            demand_sets={"d": DemandSet("d", tuple(demands))},
            routes=routes or {},
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )


def demand(source, target, volume, policy=FlowPolicyPreset.SHORTEST_PATHS_ECMP, **kw):
    return DemandSpec(Selector(source), Selector(target), volume, policy, **kw)


def links_failing(path):
    """One sampled case failing every link whose ``source|target`` matches."""
    rule = FailureRule("link", mode="all", path=path)
    return FailureRequest(FailurePolicy(modes=[FailureMode(1, [rule])]), 1, 1)


def nodes_failing(path):
    rule = FailureRule("node", mode="all", path=path)
    return FailureRequest(FailurePolicy(modes=[FailureMode(1, [rule])]), 1, 1)


def tagged_failing():
    rule = FailureRule("link", [Condition("fail", "==", True)], mode="all")
    return FailureRequest(FailurePolicy(modes=[FailureMode(1, [rule])]), 1, 1)


def run(prep, failures=None, states=("converged", "stale"), **kw):
    query = PlacementQuery(
        prep.demand_sets["d"], failures=failures, workers=1, states=states, **kw
    )
    return place(prep, query)


def edge_name(prep, edge):
    ref = prep.topology.edge_refs[int(edge)]
    return f"{ref.link} {ref.direction}"


def drops(prep, result):
    return {edge_name(prep, e): units for e, units in result.edge_drops if units}


def flows(prep, result):
    return {
        edge_name(prep, e): int(units)
        for e, units in enumerate(result.edge_flows)
        if units
    }


# E80: S splits equally over S-A-M and S-B-M (50 each); M-T 80 bounds the lossless
# request 100 at 80 (40 + 40). Failing A-M leaves S-B-M-T: 50.
E80 = [
    ("S", "A", 50),
    ("S", "B", 50),
    ("A", "M", 50),
    ("B", "M", 50),
    ("M", "T", 80),
]
# BY: the direct link (cost 1) is the only shortest route; the bypass costs 4.
BY = [("S", "T", 10, 1), ("S", "U", 10, 2), ("U", "T", 10, 2)]


def e80():
    return prepared(E80, [demand("^S$", "^T$", 100, id="e")])


# --- the states selector -------------------------------------------------------------------------------------


def test_states_default_to_converged_and_are_held_in_canonical_order():
    prep = e80()
    ds = prep.demand_sets["d"]
    assert PlacementQuery(ds).states == ("converged",)
    assert PlacementQuery(ds, states=["repair", "converged"]).states == (
        "converged",
        "repair",
    )
    for bad in ([], ["stale", "stale"], ["stale", "x"], "stale", None, [1]):
        with pytest.raises(ValueError, match="placement.states: expected"):
            PlacementQuery(ds, states=bad)
    analysis = run(prep, links_failing("^A\\|M$"), states=["repair", "stale"])
    assert [tuple(case.states) for case in analysis.cases] == [("stale", "repair")] * 2


def test_yaml_failure_states_parse_and_refuse_with_the_step_label():
    base = """
network:
  nodes: {S: {}, T: {}}
  links: [{source: S, target: T, capacity: 10, cost: 1}]
demands:
  d: [{source: ^S$, target: ^T$, volume: 4}]
workflow:
  - {type: TrafficMatrixPlacement, name: tm, demand_set: d, workers: 1%s}
"""
    from ngraph import run as run_scenario

    step = run_scenario(prepare(Scenario.from_yaml(base % ""))).steps[0]
    assert tuple(step.result.cases[0].states) == ("converged",)
    step = run_scenario(
        prepare(Scenario.from_yaml(base % ", failure_states: [repair, converged]"))
    ).steps[0]
    assert tuple(step.result.cases[0].states) == ("converged", "repair")
    refused = (ValueError, jsonschema.ValidationError)
    for bad in (", failure_states: []", ", failure_states: [stale, stale]"):
        with pytest.raises(refused, match="failure_states|non-empty|unique"):
            Scenario.from_yaml(base % bad)
    with pytest.raises(refused, match="states"):
        Scenario.from_yaml(base % ", states: [stale]")


# --- the baseline ----------------------------------------------------------------------------------------------


def test_stale_and_repair_replay_the_baseline_program_not_the_cases():
    # The baseline routes S-T directly; the case's converged route is S-U-T. Stale
    # drops the 10 units on the failed link; repair has no surviving route.
    prep = prepared(BY, [demand("^S$", "^T$", 10, id="by")])
    case = run(prep, links_failing("^S\\|T$"), states=ALL).cases[1]
    converged, stale, repair = (case.states[s].rows[0].result for s in ALL)
    assert converged.delivered == 10
    assert (stale.delivered, drops(prep, stale)) == (0, {"S|T|0 forward": 10})
    assert (repair.delivered, repair.unadmitted) == (0, 10)
    assert repair.termination == ngc.Termination.NO_ROUTE


def test_the_baseline_case_computes_every_requested_state_natively():
    for prep, expected in ((e80(), 80), (prepared(BY, [demand("^S$", "^T$", 10)]), 10)):
        (case,) = run(prep, states=ALL).cases
        results = [case.states[s].rows[0].result for s in ALL]
        assert [r.delivered for r in results] == [expected] * 3
        # Stale is a LOSSY replay at the admitted total; the others keep LOSSLESS.
        assert [r.offered for r in results] == [None, expected, None]


def test_stale_alone_still_takes_its_programs_from_an_unpublished_baseline():
    prep = e80()
    analysis = run(prep, links_failing("^A\\|M$"), states=["stale"])
    assert [tuple(c.states) for c in analysis.cases] == [("stale",), ("stale",)]
    assert analysis.cases[1].states["stale"].rows[0].result.delivered == 40


def test_converged_only_builds_no_baseline_and_schedules_cases_alone(monkeypatch):
    built = []
    original = states_module.Baseline.of
    monkeypatch.setattr(
        placement.Baseline,
        "of",
        classmethod(lambda cls, state: built.append(1) or original(state)),
    )
    scheduled = []
    original_schedule = placement.schedule_cases
    monkeypatch.setattr(
        placement,
        "schedule_cases",
        lambda cases, solve, workers: scheduled.append(len(cases))
        or original_schedule(cases, solve, workers),
    )
    prep = e80()
    request = FailureRequest(
        FailurePolicy(
            modes=[FailureMode(1, [FailureRule("link", mode="choice", count=1)])]
        ),
        8,
        3,
    )
    one = run(prep, request, states=["converged"])
    four = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"], failures=request, workers=4, states=["converged"]
        ),
    )
    assert built == []
    assert len(one.cases) > 2
    # Converged alone needs no baseline first: one schedule over every case.
    assert scheduled == [len(one.cases), len(one.cases)]
    assert [
        [r.result.delivered for r in c.states["converged"].rows] for c in one.cases
    ] == [[r.result.delivered for r in c.states["converged"].rows] for c in four.cases]


# --- stale ---------------------------------------------------------------------------------------------------


def test_stale_forwards_the_baseline_admitted_total_against_the_declared_reference():
    prep = e80()
    case = run(prep, links_failing("^A\\|M$"), states=ALL).cases[1]
    stale = case.states["stale"]
    row = stale.rows[0]
    # 80 forwarded as 40/40; A's 40 dropped on A->M.
    assert (row.result.requested, row.result.offered, row.result.delivered) == (
        80,
        80,
        40,
    )
    assert drops(prep, row.result) == {"A|M|0 forward": 40}
    assert row.reference_request_units == 100
    assert stale.totals.reference_shortfall_units == 60
    assert stale.totals.delivery_ratio == Fraction(40, 100)
    converged, repair = case.states["converged"].rows[0], case.states["repair"].rows[0]
    assert (converged.result.delivered, converged.result.unadmitted) == (50, 50)
    assert (
        repair.result.requested,
        repair.result.delivered,
        repair.result.unadmitted,
    ) == (100, 50, 50)


def test_a_baseline_that_admitted_nothing_replays_zero():
    prep = prepared(E80, [demand("^S$", "^T$", 100)], disabled=["M|T|0"])
    (case,) = run(prep, states=ALL).cases
    converged, stale = case.states["converged"].rows[0], case.states["stale"].rows[0]
    assert converged.result.admitted == 0
    assert converged.result.termination == ngc.Termination.NO_ROUTE
    assert (
        stale.result.requested,
        stale.result.delivered,
        stale.result.source_drops,
    ) == (0, 0, 0)
    assert stale.result.termination == ngc.Termination.COMPLETE
    assert stale.reference_request_units == 100
    assert case.states["stale"].totals.delivery_ratio == 0


def test_stale_black_holes_a_failed_source_with_its_own_share():
    # Equal sources S1, S2 get 5 and 5; S1 failed drops its 5 at the source.
    prep = prepared([("S1", "T", 10), ("S2", "T", 10)], [demand("^S[12]$", "^T$", 10)])
    case = run(prep, nodes_failing("^S1$")).cases[1]
    stale = case.states["stale"].rows[0].result
    assert (stale.source_drops, stale.delivered) == (5, 5)
    assert case.states["converged"].rows[0].result.delivered == 10


def test_stale_relief_is_native_forwarding_not_baseline_subtraction():
    # a: U-M-T, b: V-M-T, all 10, LOSSY offers 10 and 10. Ordered: a 10, b 0 (b's 10
    # dropped on M->T). Fail U-M: a's 10 die on U->M, so b's 10 pass M->T.
    lossy = FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY
    prep = prepared(
        [("U", "M", 10), ("V", "M", 10), ("M", "T", 10)],
        [
            demand("^U$", "^T$", 10, lossy, id="a", priority=0),
            demand("^V$", "^T$", 10, lossy, id="b", priority=1),
        ],
    )
    outputs = ngc.OutputOptions(edge_flows=True)
    analysis = run(prep, links_failing("^U\\|M$"), outputs=outputs)
    assert [r.result.delivered for r in analysis.cases[0].states["converged"].rows] == [
        10,
        0,
    ]
    a, b = (r.result for r in analysis.cases[1].states["stale"].rows)
    assert (a.delivered, drops(prep, a), flows(prep, a)) == (
        0,
        {"U|M|0 forward": 10},
        {},
    )
    assert (b.delivered, drops(prep, b)) == (10, {})
    assert flows(prep, b) == {"V|M|0 forward": 10, "M|T|0 forward": 10}
    # Simultaneous: the baseline shares M->T 5 and 5; stale relieves b the same way.
    together = run(prep, links_failing("^U\\|M$"), interaction="simultaneous")
    assert [
        [r.result.delivered for r in case.states[state].rows]
        for case, state in zip(together.cases, ("converged", "stale"), strict=True)
    ] == [[5, 5], [0, 10]]


def test_stale_pooled_remainder_splits_the_traffic_that_arrives():
    # U and V send one unit each into M, which splits 2 over two parallel links. Fail
    # U-M and the second M-T: V's unit is M's only arrival and takes the first link.
    links = [
        ("U", "M", 10, 1, {"fail": True}),
        ("V", "M", 10),
        ("M", "T", 10),
        ("M", "T", 10, 1, {"fail": True}),
    ]
    prep = prepared(links, [demand("^[UV]$", "^T$", 2)])
    first, second = (
        prep.topology.edge_refs.index(
            type(prep.topology.edge_refs[0])("M|T|0", "forward")
        ),
        prep.topology.edge_refs.index(
            type(prep.topology.edge_refs[0])("M|T|1", "forward")
        ),
    )
    assert first < second
    analysis = run(prep, tagged_failing(), outputs=ngc.OutputOptions(edge_flows=True))
    base = analysis.cases[0].states["converged"].rows[0].result
    assert base.admitted == 2
    assert flows(prep, base) == {
        "U|M|0 forward": 1,
        "V|M|0 forward": 1,
        "M|T|0 forward": 1,
        "M|T|1 forward": 1,
    }
    stale = analysis.cases[1].states["stale"].rows[0].result
    assert (stale.delivered, drops(prep, stale)) == (1, {"U|M|0 forward": 1})
    assert flows(prep, stale) == {"V|M|0 forward": 1, "M|T|0 forward": 1}


def test_replay_rows_book_no_holds_and_carry_no_plan():
    t1 = ngc.FlowPolicyConfig(
        routing=ngc.DistributedTE(ngc.TunnelCount(1)), admission=ngc.Admission.LOSSY
    )
    prep = prepared([("S", "T", 10)], [demand("^S$", "^T$", 10, t1)])
    outputs = ngc.OutputOptions(edge_reservations=True)
    (case,) = run(prep, states=ALL, outputs=outputs).cases
    forward = prep.topology.edge_refs.index(
        type(prep.topology.edge_refs[0])("S|T|0", "forward")
    )
    converged = case.states["converged"].rows[0].result
    assert converged.plan is not None and converged.edge_reservations[forward] == 10
    for name in ("stale", "repair"):
        replay = case.states[name].rows[0].result
        assert replay.plan is None and not any(replay.edge_reservations)
        assert replay.delivered == 10


def test_a_pool_replays_its_tunnels_through_its_own_attachments():
    prep = prepared(
        [("S1", "T", 10), ("S2", "T", 10)],
        [demand("^S[12]$", "^T$", 20, FlowPolicyPreset.TE_ECMP_16_LSP, id="p")],
    )
    analysis = run(prep, nodes_failing("^S1$"), export_details=True)
    base = analysis.cases[0].states["converged"].rows[0].result
    s1 = prep.topology.node_id_by_name["S1"]
    sources = prep.topology.graph.edge_sources()
    via_s1 = {
        t.entry_id for t in base.program.tunnels if int(sources[t.edges[1]]) == s1
    }
    lost = sum(row.assigned for row in base.by_tunnel if row.entry_id in via_s1)
    assert 0 < lost < base.delivered
    stale = analysis.cases[1].states["stale"].rows[0].result
    assert stale.delivered == base.admitted - lost
    wire = project(analysis)["analysis"]["cases"][1]["states"]["stale"]["rows"][0]
    assert wire["result"]["synthetic_ingress"]["edge_drops"] == [
        {"edge": {"pool_id": "p|0", "source": "S1"}, "units": lost}
    ]


# --- repair ----------------------------------------------------------------------------------------------------


def test_an_explicit_route_demand_forwards_the_same_program_in_converged_and_repair():
    prep = prepared(
        BY,
        [demand("^S$", "^T$", 10, PinnedRoutes(("direct",)))],
        routes={"direct": RouteSpec("S", nodes=("S", "T"))},
    )
    case = run(prep, links_failing("^S\\|T$"), states=ALL).cases[1]
    converged, repair = (case.states[s].rows[0].result for s in ("converged", "repair"))
    for field in ("delivered", "admitted", "unadmitted", "source_drops", "termination"):
        assert getattr(converged, field) == getattr(repair, field)
    assert [t.status for t in converged.by_tunnel] == [
        t.status for t in repair.by_tunnel
    ]


@pytest.mark.parametrize(
    "model",
    [
        ngc.DistributedTE(ngc.TunnelCount(1)),
        ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(1),
        ),
    ],
)
def test_tunnel_repair_keeps_a_reachable_heads_share(model):
    # Heads A and B, one tunnel each over A-t and B-t; A-t fails. Converged sets A
    # up again via X; stale drops A's 10 on A->t; repair keeps A in the roster (it
    # still reaches t via X) with no surviving tunnel: LOSSLESS admits nothing.
    links = [("A", "t", 10, 1), ("B", "t", 10, 1), ("A", "X", 10, 5), ("X", "t", 10, 5)]
    for admission, repaired in (
        (ngc.Admission.LOSSLESS, (0, 20, 0)),
        (ngc.Admission.LOSSY, (10, 0, 10)),
    ):
        config = ngc.FlowPolicyConfig(routing=model, admission=admission)
        prep = prepared(links, [demand("^[AB]$", "^t$", 20, config)])
        case = run(prep, links_failing("^A\\|t$"), states=ALL).cases[1]
        assert case.states["converged"].rows[0].result.delivered == 20
        assert case.states["stale"].rows[0].result.delivered == 10
        repair = case.states["repair"].rows[0].result
        assert (repair.delivered, repair.unadmitted, repair.source_drops) == repaired


def test_repair_is_computed_only_when_requested(monkeypatch):
    seen = []
    original = placement.participants
    monkeypatch.setattr(
        placement,
        "participants",
        lambda *args: seen.append(args[5]) or original(*args),
    )
    analysis = run(e80(), links_failing("^A\\|M$"))
    assert all("repair" not in case.states for case in analysis.cases)
    assert "repair" not in seen and set(seen) == {"converged", "stale"}


# --- outcomes of lossy forwarding ------------------------------------------------------------------------------

CR_LINKS = [
    ("H", "P", 10),
    ("P", "Q", 1),
    ("Q", "R", 10),
    ("R", "S", 2),
    ("S", "D", 10),
    ("H", "R", 10),
    ("S", "P", 10),
    ("Q", "D", 10),
    ("H", "W", 10),
    ("W", "P", 9),
]
CR_ROUTES = {
    "one": RouteSpec("H", nodes=("H", "P", "Q", "R", "S", "D"), weight=1),
    "two": RouteSpec("H", nodes=("H", "R", "S", "P", "Q", "D"), weight=2),
    "three": RouteSpec("H", nodes=("H", "W", "P", "Q", "D"), weight=2),
}


def crossing(routes, volume):
    policy = PinnedRoutes(tuple(routes), admission=ngc.Admission.LOSSY)
    return prepared(
        CR_LINKS,
        [demand("^H$", "^D$", volume, policy)],
        routes={name: CR_ROUTES[name] for name in routes},
    )


def test_an_ordered_list_records_a_loss_iteration_outcome_per_case_and_state():
    # One demand's own tunnels cross (P->Q then R->S, and R->S then P->Q). Nominally
    # the third route relieves the cycle (offered 5, delivered 1); with W-P failed,
    # stale keeps the third route's share as a drop and the two others cycle.
    prep = crossing(("one", "two", "three"), 5)
    analysis = run(prep, links_failing("^W\\|P$"))
    base = analysis.cases[0].states
    assert base["converged"].rows[0].result.offered == 5
    assert base["converged"].rows[0].result.delivered == 1
    case = analysis.cases[1].states
    assert case["stale"].failure == ForwardingFailure(PERIOD_2)
    assert case["stale"].rows == () and case["stale"].totals is None
    converged = case["converged"].rows[0].result
    assert (converged.delivered, converged.termination) == (0, ngc.Termination.COMPLETE)
    assert case["converged"].failure is None
    # At alpha 0.6 (request 3) the failed case's repair cycles natively; stale
    # delivers 1.
    case = run(prep, links_failing("^W\\|P$"), states=ALL, alpha=0.6).cases[1]
    assert case.states["repair"].failure == ForwardingFailure(PERIOD_2)
    assert case.states["repair"].rows == () and case.states["repair"].totals is None
    assert case.states["stale"].rows[0].result.delivered == 1


def test_a_baseline_outcome_aborts_only_when_a_replay_needs_its_programs():
    # Two crossing tunnels with weights 1:2 at offer 3 are the contract's D-C2 in
    # one demand: the baseline cycles. Preparation forwards the nominal volume 1
    # (H gives it to the weight-2 route alone), so the cycle appears at alpha 3.
    # P-Q fails every tunnel in the other case.
    prep = crossing(("one", "two"), 1)
    with pytest.raises(ValueError, match="case baseline: " + PERIOD_2):
        run(prep, links_failing("^P\\|Q$"), alpha=3)
    analysis = run(prep, links_failing("^P\\|Q$"), states=["converged"], alpha=3)
    assert analysis.cases[0].states["converged"].failure == ForwardingFailure(PERIOD_2)
    # Every tunnel crosses P-Q; H still reaches D (via R), so it keeps its share
    # with no active route and loses it at the source (CONTRACT 8.4).
    failed = analysis.cases[1].states["converged"].rows[0].result
    assert (failed.delivered, failed.source_drops) == (0, 3)
    assert failed.termination == ngc.Termination.NO_ACTIVE_WEIGHT


def test_only_the_two_loss_iteration_texts_are_outcomes(monkeypatch):
    removed = []
    original_remove = placement.remove_policies
    monkeypatch.setattr(
        placement,
        "remove_policies",
        lambda owners: removed.append(len(owners)) or original_remove(owners),
    )
    original = ngc.apply_actions
    prep = e80()
    for error in (
        RuntimeError("lossy forwarding fixed-point verification failed"),
        ValueError("another native refusal"),
        ValueError(f"{PERIOD_2} near miss"),
    ):

        def failing(ledger, actions, *, mode, outputs=None, error=error):
            raise error

        monkeypatch.setattr(ngc, "apply_actions", failing)
        removed.clear()
        with pytest.raises(type(error), match=str(error)):
            run(prep, states=["converged"])
        assert removed and all(n == 1 for n in removed)
    calls = []

    def round_limit(ledger, actions, *, mode, outputs=None):
        calls.append(1)
        if len(calls) == 2:  # the baseline's stale state
            raise ValueError(ROUND_LIMIT)
        return original(ledger, actions, mode=mode, outputs=outputs)

    monkeypatch.setattr(ngc, "apply_actions", round_limit)
    (case,) = run(prep).cases
    assert case.states["stale"].failure == ForwardingFailure(ROUND_LIMIT)
    assert case.states["converged"].rows[0].result.delivered == 80


# --- lifetimes and workers --------------------------------------------------------------------------------------


def test_every_policy_is_removed_when_a_state_fails_and_a_retry_matches(monkeypatch):
    prep = e80()
    fresh = run(prep, links_failing("^A\\|M$"), states=ALL)
    created, removed = [], []
    real = ngc.FlowPolicy
    original_remove = placement.remove_policies
    monkeypatch.setattr(
        placement,
        "remove_policies",
        lambda owners: removed.extend(owners) or original_remove(owners),
    )
    for k in range(1, 7):

        def counting(*args, k=k):
            if len(created) + 1 == k:
                raise MemoryError("planted")
            policy = real(*args)
            created.append(policy)
            return policy

        created.clear()
        removed.clear()
        monkeypatch.setattr(ngc, "FlowPolicy", counting)
        with pytest.raises(MemoryError):
            run(prep, links_failing("^A\\|M$"), states=ALL)
        assert {id(p) for p in created} <= {id(p) for p in removed}

    def recording(*args):
        policy = real(*args)
        created.append(policy)
        return policy

    monkeypatch.setattr(ngc, "FlowPolicy", recording)
    real_apply = ngc.apply_actions
    # Six forwarding lists (two cases, three states); fail each, then none.
    for k in (1, 2, 3, 4, 5, 6, None):
        calls = []

        def apply(ledger, actions, *, mode, outputs=None, k=k, calls=calls):
            calls.append(1)
            if len(calls) == k:
                raise MemoryError("planted")
            return real_apply(ledger, actions, mode=mode, outputs=outputs)

        created.clear()
        removed.clear()
        monkeypatch.setattr(ngc, "apply_actions", apply)
        if k is None:
            run(prep, links_failing("^A\\|M$"), states=ALL)
        else:
            with pytest.raises(MemoryError):
                run(prep, links_failing("^A\\|M$"), states=ALL)
        assert created and {id(p) for p in created} <= {id(p) for p in removed}
        # Removed policies hold no program (replace_matrix's own release precedes it).
        assert all(policy.program is None for policy in created)
    monkeypatch.setattr(ngc, "apply_actions", real_apply)
    monkeypatch.setattr(ngc, "FlowPolicy", real)
    retry = run(prep, links_failing("^A\\|M$"), states=ALL)
    assert [
        [
            (s, r.result.delivered, r.result.admitted)
            for s, st in c.states.items()
            for r in st.rows
        ]
        for c in retry.cases
    ] == [
        [
            (s, r.result.delivered, r.result.admitted)
            for s, st in c.states.items()
            for r in st.rows
        ]
        for c in fresh.cases
    ]


def test_workers_give_the_same_states_and_the_lowest_failing_case(monkeypatch):
    prep = e80()
    request = FailureRequest(
        FailurePolicy(
            modes=[FailureMode(1, [FailureRule("link", mode="choice", count=1)])]
        ),
        12,
        5,
    )

    def table(analysis):
        return [
            [
                (s, r.result.delivered, r.result.edge_drops)
                for s, st in c.states.items()
                for r in st.rows
            ]
            for c in analysis.cases
        ]

    one = run(prep, request, states=ALL)
    four = place(
        prep,
        PlacementQuery(prep.demand_sets["d"], failures=request, workers=4, states=ALL),
    )
    assert len(one.cases) >= 4 and table(one) == table(four)
    original = placement.participants

    def failing(*args):
        case = args[4]
        if case.id in ("failure-000002", "failure-000003"):
            raise ValueError(f"planted in {case.id}")
        return original(*args)

    monkeypatch.setattr(placement, "participants", failing)
    with pytest.raises(ValueError, match="planted in failure-000002"):
        place(
            prep,
            PlacementQuery(
                prep.demand_sets["d"], failures=request, workers=4, states=ALL
            ),
        )


# --- export and edges -------------------------------------------------------------------------------------------


def test_the_states_mapping_and_question_reach_the_wire():
    prep = e80()
    analysis = run(prep, links_failing("^A\\|M$"), states=["repair", "stale"])
    wire = project(analysis)["analysis"]
    case = wire["cases"][1]
    assert list(case["states"]) == ["stale", "repair"]
    assert set(case["states"]["stale"]) == {"rows", "totals"}
    assert case["states"]["stale"]["rows"][0]["result"]["delivered_units"] == 40
    assert case["states"]["stale"]["rows"][0]["reference_request_units"] == 100
    assert case["states"]["repair"]["totals"]["delivered_units"] == 50
    failing = run(
        crossing(("one", "two"), 1),
        links_failing("^P\\|Q$"),
        states=["converged"],
        alpha=3,
    )
    state = project(failing)["analysis"]["cases"][0]["states"]["converged"]
    assert state == {
        "rows": [],
        "totals": None,
        "failure": {"kind": "loss_iteration", "message": PERIOD_2},
    }


def test_cost_distributions_belong_to_converged_rows_only():
    prep = e80()
    analysis = run(prep, links_failing("^A\\|M$"), export_cost_distribution=True)
    for case in analysis.cases:
        assert case.states["converged"].rows[0].cost_distribution is not None
        stale = case.states["stale"].rows[0]
        assert stale.cost_distribution is None and not stale.unavailable_outputs


def test_a_zero_offer_changes_no_other_output():
    alone = run(e80(), links_failing("^A\\|M$"), states=ALL)
    prep = prepared(
        E80, [demand("^S$", "^T$", 100, id="e"), demand("^S$", "^T$", 0, id="z")]
    )
    both = run(prep, links_failing("^A\\|M$"), states=ALL)
    for one, two in zip(alone.cases, both.cases, strict=True):
        for name in ALL:
            a, (b, z) = one.states[name].rows[0].result, two.states[name].rows
            assert (a.delivered, a.edge_drops, a.admitted) == (
                b.result.delivered,
                b.result.edge_drops,
                b.result.admitted,
            )
            assert z.result.delivered == 0


def test_every_link_failed():
    prep = e80()
    case = run(prep, links_failing(".*"), states=ALL).cases[1]
    converged, stale, repair = (case.states[s].rows[0].result for s in ALL)
    assert (converged.unadmitted, converged.termination) == (
        100,
        ngc.Termination.NO_ROUTE,
    )
    assert drops(prep, stale) == {"S|A|0 forward": 40, "S|B|0 forward": 40}
    assert stale.delivered == 0 and stale.source_drops == 0
    assert (repair.unadmitted, repair.termination) == (100, ngc.Termination.NO_ROUTE)


def test_an_interior_node_failure_drops_on_the_links_entering_it():
    prep = e80()
    case = run(prep, nodes_failing("^M$"), states=ALL).cases[1]
    converged, stale, repair = (case.states[s].rows[0].result for s in ALL)
    assert drops(prep, stale) == {"A|M|0 forward": 40, "B|M|0 forward": 40}
    assert stale.delivered == 0
    assert (converged.unadmitted, repair.unadmitted) == (100, 100)


def test_a_zero_matrix_reports_every_state():
    prep = prepared(E80, [demand("^S$", "^T$", 0)])
    (case,) = run(prep, states=ALL).cases
    for name in ALL:
        assert case.states[name].rows[0].result.delivered == 0
        assert case.states[name].totals.delivery_ratio == 1
