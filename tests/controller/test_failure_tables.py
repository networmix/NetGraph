"""WCMP controller tables in failure cases: per-case tables, fixed group caps, dead groups.

A failure case's converged table is built on the failed topology; a group repair
table on the nominal routes that survive. A root group with no live member keeps
its cap: its members stay in the program at their nominal shares and are black
holes, so its share is dropped at its router. Expected values are derived by hand
in each test; LOSSY figures forward the case table's own program natively.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import defaultdict
from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph import (
    FailureMode,
    FailurePolicy,
    FailureRule,
    PlacementQuery,
    Scenario,
    place,
    prepare,
    run,
)
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.topology import eligibility
from ngraph.model.network import DirectedLink
from ngraph.results import DeadCap
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement
from tests.controller.helpers import demand, prepared, scenario, tree
from tests.controller.test_declarations import FIXTURE
from tests.results.test_analysis_wire import project

ALL = ("converged", "stale", "repair")
R30_LINKS = [("S", f"A{i}", 100, 1) for i in (1, 2, 3, 4)] + [
    (f"A{i}", "T", 100, 2) for i in (1, 2, 3, 4)
]
R30_TREE = {
    "s": tree(
        "S", (1, [(1, "S|A1|0"), (1, "S|A2|0")]), (1, [(1, "S|A3|0"), (1, "S|A4|0")])
    )
}


def r30(links=R30_LINKS, trees=R30_TREE, volume=300):
    return prepared(
        links,
        "^A[1-5]$",
        "^(S|T)$",
        [demand("^S$", "^T$", volume, id="r30")],
        scope="group",
        trees=trees,
    )


def request(scope, path):
    rule = FailureRule(scope, mode="all", path=path)
    return FailureRequest(FailurePolicy(modes=[FailureMode(1, [rule])]), 1, 1)


def case_states(prep, failures, states=ALL):
    analysis = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"], failures=failures, workers=1, states=states
        ),
    )
    return analysis.cases[-1].states


def delivered(state):
    return [row.result.delivered for row in state.rows]


def case_mask(prep, nodes=(), links=()):
    return eligibility(prep.topology, excluded_nodes=nodes, excluded_links=links)


def tables(prep, mask, repair=False):
    return prep._controller.case_tables(
        prep.topology,
        prep.demand_sets["d"],
        mask,
        repair=repair,
        context="case c state s",
    )


def row(prep, table, router):
    graph, topology = prep.topology.graph, prep.topology
    node = topology.node_id_by_name[router]
    sources = graph.edge_sources()
    return {
        topology.edge_refs[e].link: table.weights[e]
        for e in (int(x) for x in table.dag.via_edges())
        if int(sources[e]) == node
    }


def lossy(prep, table, source, target, units, mask):
    """The case table's program for one demand, forwarded LOSSY natively."""
    topology = prep.topology
    endpoints = type(prep.demand_sets["d"].demands[0].endpoints)((source,), (target,))
    config = prep._controller.leaf_config(topology, table, endpoints, mask)
    config = ngc.FlowPolicyConfig(routing=config.routing, admission=ngc.Admission.LOSSY)
    result = ngc.evaluate_demand(
        topology.graph,
        [topology.node_id_by_name[source]],
        [topology.node_id_by_name[target]],
        ngc.EvaluationOptions(config, offer=units),
    )
    drops = {topology.edge_refs[int(e)].link: u for e, u in result.edge_drops if u}
    return result.delivered, drops


# --- groups: partial and dead ------------------------------------------------------------------------------------


def test_a_partly_failed_group_reflattens_within_its_cap():
    # S-A1 fails: group 0 keeps its half on A2; A3 and A4 keep a quarter each (2:1:1).
    # LOSSLESS: A2 carries x/2 <= 100, so 200 (201 puts 101 on A2). Stale: 75 x 4,
    # A1's 75 dropped. A recomputed 1:2 group split would admit 300.
    prep = r30()
    states = case_states(prep, request("link", "^S\\|A1$"))
    assert [delivered(states[s]) for s in ALL] == [[200], [225], [200]]
    assert states["converged"].dead_caps == () and states["repair"].dead_caps == ()
    assert states["stale"].dead_caps is None
    table = tables(prep, case_mask(prep, links=["S|A1|0"]))["T"]
    assert row(prep, table, "S") == {"S|A2|0": 2, "S|A3|0": 1, "S|A4|0": 1}


def test_a_dead_group_keeps_its_cap_and_drops_it_at_its_router():
    # Group 0 dead: its members stay at 1:1:1:1 and are black holes. LOSSLESS stops at
    # the first unit RR gives a dead member: A1 first gives 0; A3, A4 dead gives 2.
    prep = r30()
    first = case_states(prep, request("link", "^S\\|A[12]$"))
    assert [delivered(first[s]) for s in ALL] == [[0], [150], [0]]
    cap = DeadCap("T", "S", "s", 0, Fraction(1, 2))
    assert first["converged"].dead_caps == (cap,) == first["repair"].dead_caps
    last = case_states(prep, request("link", "^S\\|A[34]$"))
    assert [delivered(last[s]) for s in ALL] == [[2], [150], [2]]
    assert last["converged"].dead_caps == (DeadCap("T", "S", "s", 1, Fraction(1, 2)),)
    mask = case_mask(prep, links=["S|A1|0", "S|A2|0"])
    for repair in (False, True):
        table = tables(prep, mask, repair)["T"]
        assert row(prep, table, "S") == dict.fromkeys(
            ("S|A1|0", "S|A2|0", "S|A3|0", "S|A4|0"), 1
        )
        # LOSSY: 75 per member, the dead half dropped on S's own links (not 200 by spill).
        assert lossy(prep, table, "S", "T", 300, mask) == (
            150,
            {"S|A1|0": 75, "S|A2|0": 75},
        )


DOM4_LINKS = [
    ("S", "A", 100),
    ("S", "B", 100),
    ("U", "B", 100),
    ("A", "t", 100),
    ("B", "Y1", 100),
    ("B", "Y2", 100),
    ("Y1", "t", 100),
    ("Y2", "t", 100),
]
DOM4_TREES = {
    "s": tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|B|0")])),
    "u": tree("U", (1, [(1, "U|B|0")])),
}


def dom4(scope="group"):
    return prepared(
        DOM4_LINKS,
        "^(A|B|Y1|Y2)$",
        "^(S|U|t)$",
        [demand("^S$", "^t$", 100, id="s"), demand("^U$", "^t$", 100, id="u")],
        scope=scope,
        trees=DOM4_TREES,
    )


def test_live_routers_keep_their_failed_topology_rows():
    # S-B and B-Y1 fail. S's group {S->B} is dead; B still carries U's traffic on its
    # new row B->Y2. Keeping B's nominal row (B->Y1, B->Y2) would send half of U's
    # traffic into the failed B->Y1 (U 50).
    prep = dom4()
    states = case_states(prep, request("link", "^(S\\|B|B\\|Y1)$"))
    assert delivered(states["converged"]) == [1, 100]
    mask = case_mask(prep, links=["S|B|0", "B|Y1|0"])
    table = tables(prep, mask)["t"]
    assert row(prep, table, "B") == {"B|Y2|0": 1}
    assert lossy(prep, table, "S", "t", 100, mask) == (50, {"S|B|0": 50})
    assert lossy(prep, table, "U", "t", 100, mask) == (100, {})


def h_split(weights, total):
    """Highest averages unit by unit, ties to the earlier member: (held, unit owners)."""
    held, owners = [0] * len(weights), []
    for _ in range(total):
        best = max(
            (i for i, w in enumerate(weights) if w > 0),
            key=lambda i: (Fraction(weights[i], held[i] + 1), -i),
        )
        held[best] += 1
        owners.append(best)
    return held, owners


def nominal_next_hops(domain, pairs, costs):
    """Each domain node's tight next hops toward its nearest exit (exit links cost 0)."""
    exits = [d for d in domain if (d, "t") in pairs]
    near = defaultdict(list)
    for a, b in pairs:
        if a in domain and b in domain:
            near[a].append(b)
            near[b].append(a)
    dist, heap = dict.fromkeys(exits, 0), [(0, e) for e in exits]
    while heap:
        d, n = heapq.heappop(heap)
        for m in near[n]:
            if d + costs[frozenset((n, m))] < dist.get(m, math.inf):
                dist[m] = d + costs[frozenset((n, m))]
                heapq.heappush(heap, (dist[m], m))
    hops = {n: ["t"] if n in exits else [] for n in domain}
    for n in domain:
        if n not in exits and n in dist:
            hops[n] = [
                m for m in near[n] if dist[n] == costs[frozenset((n, m))] + dist[m]
            ]
    return hops, dist


def domain_oracle(domain, pairs, costs, ups, shapes, edge, nodes, links):
    """Per source: converged and repair (LOSSY delivered, LOSSLESS admitted), stale delivered."""
    hops, dist = nominal_next_hops(domain, pairs, costs)

    def up(a, b):
        return not ({(a, b), (b, a)} & links or {a, b} & nodes)

    def reach(starts, step):
        seen, pending = set(starts), list(starts)
        while pending:
            for m in step(pending.pop()):
                if m not in seen:
                    seen.add(m)
                    pending.append(m)
        return seen

    near = defaultdict(list)
    for a, b in pairs:
        if a in domain and b in domain and up(a, b):
            near[a].append(b)
            near[b].append(a)
    exits = [d for d in domain if (d, "t") in pairs and up(d, "t")]
    reached = {
        "converged": reach(exits, near.__getitem__),
        "repair": reach(
            ["t"], lambda n: [m for m in domain if n in hops[m] and up(m, n)]
        ),
    }
    want = {}
    for s, ds in ups.items():
        together, shares = shapes[s]
        members = sorted(ds, key=lambda d: edge[(s, d)])
        nominal = dict(zip(ds, shares, strict=True))
        for state, alive in reached.items():
            live = {d: up(s, d) and d in alive for d in ds}
            weights = {d: Fraction(nominal[d], sum(shares)) for d in ds}
            if together and any(live.values()):
                total = sum(nominal[d] for d in ds if live[d])
                weights = {d: Fraction(nominal[d] * live[d], total) for d in ds}
            scale = math.lcm(*(w.denominator for w in weights.values()))
            held, owners = h_split([int(weights[d] * scale) for d in members], 120)
            lossy = sum(h for h, d in zip(held, members, strict=True) if live[d])
            dead = (k for k, i in enumerate(owners) if not live[members[i]])
            # No live member: no row, or one that delivers nothing.
            want[s, state] = (lossy, next(dead, 120)) if any(live.values()) else (0, 0)
        held, _ = h_split([nominal[d] for d in members], 120)
        arrive = defaultdict(int)
        for h, d in zip(held, members, strict=True):
            arrive[d] += h if up(s, d) else 0
        delivered = 0
        for n in sorted(domain, key=lambda n: -dist.get(n, -1)):
            units = arrive.pop(n, 0)
            outs = sorted(hops[n], key=lambda m: edge[(n, m)])
            for j, m in enumerate(outs if units and n not in nodes else ()):
                share = units // len(outs) + (j < units % len(outs))
                if up(n, m) and m == "t":
                    delivered += share
                elif up(n, m):
                    arrive[m] += share
        want[s, "stale"] = delivered
    return want


def test_random_domains_match_an_independent_forwarding_oracle():
    # BGP-edge sources S and U, each with two random uplinks into a random domain
    # (one root group per uplink, or one group over both), t behind two exits; one
    # or two failed links, or a failed domain node; offers 120 (capacity never binds).
    # The oracle derives every state from the stated rules alone. Converged: an
    # uplink is live when it survives and its tail reaches a surviving exit inside the
    # domain; repair: when its tail still reaches t over surviving nominal next hops.
    # A group with a live child keeps its cap on its live children, a dead group its
    # nominal children at their shares, black-holed. Simultaneous (LOSSY) delivers the
    # live members' highest-averages shares; ordered (LOSSLESS) admits the units
    # before the first one into a dead member. Stale forwards the nominal programs
    # with the failures as black holes, round-robin at the domain's routers.
    rng = random.Random(20261031)
    checked = 0
    for _ in range(60):
        domain = [f"D{i}" for i in range(6)]
        pairs = {
            (a, b)
            for i, a in enumerate(domain)
            for b in domain[i + 1 :]
            if rng.random() < 0.45
        }
        pairs |= {("D4", "t"), ("D5", "t")}
        ups = {s: sorted(rng.sample(domain[:4], 2)) for s in ("S", "U")}
        pairs |= {(s, d) for s, ds in ups.items() for d in ds}
        costs = {frozenset(p): rng.randint(1, 3) for p in pairs}
        shapes, trees = {}, {}
        for s, ds in ups.items():
            together = rng.random() < 0.5
            shares = [1 if together else rng.choice((1, 2)), rng.choice((1, 2))]
            shapes[s] = (together, shares)
            leaves = [(w, f"{s}|{d}|0") for w, d in zip(shares, ds, strict=True)]
            groups = [(1, leaves)] if together else [(w, [(1, n)]) for w, n in leaves]
            trees[s.lower()] = tree(s, *groups)
        try:
            prep = prepared(
                [(a, b, 1000, costs[frozenset((a, b))]) for a, b in sorted(pairs)],
                "^D[0-5]$",
                "^(S|U|t)$",
                [demand("^S$", "^t$", 120, id="s"), demand("^U$", "^t$", 120, id="u")],
                scope="group",
                trees=trees,
            )
        except ValueError:
            continue  # a nominal declaration part B refuses (no route to t)
        if rng.random() < 0.3:
            nodes, links = {rng.choice(domain)}, set()
            failures = request("node", f"^{next(iter(nodes))}$")
        else:
            inner = sorted(pairs - {("D4", "t"), ("D5", "t")})
            nodes, links = set(), set(rng.sample(inner, rng.randint(1, 2)))
            path = "|".join(f"{a}\\|{b}" for a, b in links)
            failures = request("link", f"^({path})$")
        edge = {}
        for i, ref in enumerate(prep.topology.edge_refs):
            if isinstance(ref, DirectedLink):
                a, b, _ = ref.link.split("|")
                edge[(a, b) if ref.direction == "forward" else (b, a)] = i
        want = domain_oracle(domain, pairs, costs, ups, shapes, edge, nodes, links)
        for interaction in ("simultaneous", "ordered"):
            query = PlacementQuery(
                prep.demand_sets["d"],
                failures=failures,
                workers=1,
                states=ALL,
                interaction=interaction,
            )
            states = place(prep, query).cases[-1].states
            for s in ("S", "U"):
                rows = {
                    state: [
                        r.result for r in states[state].rows if r.id[0] == s.lower()
                    ]
                    for state in ALL
                }
                for state in ("converged", "repair"):
                    lossy, lossless = want[s, state]
                    if interaction == "simultaneous":
                        assert sum(r.delivered for r in rows[state]) == lossy
                    else:
                        assert sum(r.admitted for r in rows[state]) == lossless
                stale = [r.delivered for r in rows["stale"]]
                assert stale == [want[s, "stale"]]
                checked += 1
    assert checked >= 100


def test_a_router_with_no_route_leaves_its_demands_roster():
    # One demand from S and U; S's only uplink fails: S leaves the equal source roster
    # and U carries all 100 (keeping S's share would admit 0: RR's first unit is S's).
    prep = prepared(
        [("S", "A", 100), ("U", "B", 100), ("A", "t", 100), ("B", "t", 100)],
        "^(A|B)$",
        "^(S|U|t)$",
        [demand("^(S|U)$", "^t$", 100, id="su")],
        scope="group",
        trees={
            "s": tree("S", (1, [(1, "S|A|0")])),
            "u": tree("U", (1, [(1, "U|B|0")])),
        },
    )
    assert delivered(case_states(prep, request("link", "^S\\|A$"))["converged"]) == [
        100
    ]


# --- the disagreement check --------------------------------------------------------------------------------------

Z0_LINKS = [
    ("S", "A", 100),
    ("A", "t", 100),
    ("S", "B", 100),
    ("B", "X", 100),
    ("X", "t", 100),
    ("B", "Y", 100, 2),
    ("Y", "t", 0),
]


def z0(shares=(2, 1), extra=()):
    trees = {"s": tree("S", (shares[0], [(1, "S|A|0")]), (shares[1], [(1, "S|B|0")]))}
    return prepared(
        Z0_LINKS + list(extra),
        "^(A|B|X|Y|Z)$",
        "^(S|t)$",
        [demand("^S$", "^t$", 90, id="z")],
        scope="group",
        trees=trees,
    )


def test_a_pruned_dead_member_is_refused_per_case():
    # B-X fails; B's only row leads to Y-t (capacity 0), so S->B carries nothing alone
    # and group 1 is dead. WEIGHTED (caps 2:1) prunes S->B before black holes act, so
    # its third would spill into A (90 delivered instead of 60): refused.
    prep = z0()
    with pytest.raises(
        ValueError,
        match=r"forwarding_groups\.s\.groups\[1\]: case failure-000001 state converged: "
        r"toward t, router S forwards this dead group's share differently",
    ):
        case_states(prep, request("link", "^B\\|X$"))
    # Equal caps encode EQUAL, which keeps the member: half is lost on S->B.
    equal = z0((1, 1))
    assert delivered(case_states(equal, request("link", "^B\\|X$"))["converged"]) == [1]
    mask = case_mask(equal, links=["B|X|0"])
    assert lossy(equal, tables(equal, mask)["t"], "S", "t", 90, mask) == (
        45,
        {"S|B|0": 45},
    )


def test_the_refusal_names_the_dead_group_whose_member_pruning_removes():
    # Groups {S->A}, {S->B}, {S->C} with shares 1, 2, 3. A-t and B-X fail: group 0's
    # member keeps a nominal continuation (black-holed, not pruned); group 1's S->B
    # leads only to Y-t of capacity 0, so WEIGHTED prunes it and its share spills.
    links = [
        ("S", "A", 100),
        ("A", "t", 100),
        ("S", "B", 100),
        ("B", "X", 100),
        ("X", "t", 100),
        ("B", "Y", 100, 2),
        ("Y", "t", 0),
        ("S", "C", 100),
        ("C", "t", 100),
    ]
    trees = {
        "s": tree("S", (1, [(1, "S|A|0")]), (2, [(1, "S|B|0")]), (3, [(1, "S|C|0")]))
    }
    prep = prepared(
        links,
        "^(A|B|C|X|Y)$",
        "^(S|t)$",
        [demand("^S$", "^t$", 60, id="z")],
        scope="group",
        trees=trees,
    )
    with pytest.raises(ValueError, match=r"forwarding_groups\.s\.groups\[1\]: "):
        case_states(prep, request("link", "^(A\\|t|B\\|X)$"), ("converged",))


def test_a_dead_member_with_a_live_continuation_is_dropped_at_its_router():
    # With B-Z-t live beside the zero-capacity Y-t, preparation keeps S->B; its black
    # hole drops the dead third, so 60 arrive (90 if the dead cap could pass via Z).
    prep = z0(extra=[("B", "Z", 100, 2), ("Z", "t", 100)])
    states = case_states(prep, request("link", "^B\\|X$"))
    assert delivered(states["converged"]) == [2]  # H: units 1-2 to A, unit 3 to S->B
    mask = case_mask(prep, links=["B|X|0"])
    assert lossy(prep, tables(prep, mask)["t"], "S", "t", 90, mask) == (
        60,
        {"S|B|0": 30},
    )


def test_a_legal_weight_approximation_passes_the_check():
    # Root shares 1 : 2^-70 survive S-A1 as [2^62 - 2, 1] after apportionment; the
    # check compares with that integer row, so nothing is refused.
    prep = prepared(
        [("S", "A1", 100), ("S", "A2", 100), ("S", "B", 100)]
        + [(a, "T", 100) for a in ("A1", "A2", "B")],
        "^(A1|A2|B)$",
        "^(S|T)$",
        [demand("^S$", "^T$", 90, id="approx")],
        scope="group",
        trees={
            "g": tree(
                "S",
                (1, [(1, "S|A1|0"), (1, "S|A2|0")]),
                (Fraction(1, 2**70), [(1, "S|B|0")]),
            )
        },
    )
    table = tables(prep, case_mask(prep, links=["S|A1|0"]))["T"]
    assert row(prep, table, "S") == {"S|A2|0": 2**62 - 2, "S|B|0": 1}
    assert table.approximations
    assert delivered(case_states(prep, request("link", "^S\\|A1$"))["converged"]) == [
        90
    ]


# --- repair against converged ------------------------------------------------------------------------------------


def test_group_repair_uses_surviving_routes_only():
    # B-Y1 fails. Converged: B reroutes via Y2, both groups live, 100. Repair: B's
    # nominal route is gone, so group {S->B} is dead (LOSSLESS 1). Stale drops 50.
    prep = prepared(
        [
            ("S", "A", 100),
            ("S", "B", 100),
            ("A", "t", 100),
            ("B", "Y1", 100),
            ("Y1", "t", 100),
            ("B", "Y2", 100, 2),
            ("Y2", "t", 100),
        ],
        "^(A|B|Y1|Y2)$",
        "^(S|t)$",
        [demand("^S$", "^t$", 100, id="s")],
        scope="group",
        trees={"s": tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|B|0")]))},
    )
    states = case_states(prep, request("link", "^B\\|Y1$"))
    assert [delivered(states[s]) for s in ALL] == [[100], [50], [1]]
    assert states["repair"].dead_caps == (DeadCap("t", "S", "s", 1, Fraction(1, 2)),)
    assert states["converged"].dead_caps == ()


NH_LINKS = [
    ("S", "A", 100),
    ("S", "B", 100),
    ("A", "M", 100),
    ("A", "N", 100),
    ("M", "T", 60),
    ("N", "T", 60),
    ("B", "T", 100),
]


@pytest.mark.parametrize("scope", ["next_hop", "all_routers"])
def test_table_repair_prunes_the_nominal_table_instead_of_solving_again(scope):
    # M-T fails. Converged recomputes S's split (A alone 60 via N, B 100): 160 fit.
    # Repair replays the nominal 1:1 without A's M branch: A's 80 meet N-T 60, so
    # LOSSLESS admits 120. Stale replays 1:1 at 160: B delivers 80, and A's 80 split
    # by A's nominal row with the M part dropped on M->T (next_hop 40:40; all_routers
    # the nominal solve's flows).
    prep = prepared(
        NH_LINKS,
        "^(A|B|M|N)$",
        "^(S|T)$",
        [demand("^S$", "^T$", 160, id="s")],
        scope=scope,
    )
    nominal = row(prep, prep.demand_sets["d"].controller_table("T"), "A")
    via_n = Fraction(80 * nominal["A|N|0"], nominal["A|M|0"] + nominal["A|N|0"])
    assert via_n.denominator == 1
    states = case_states(prep, request("link", "^M\\|T$"))
    assert [delivered(states[s]) for s in ALL] == [[160], [80 + int(via_n)], [120]]
    # LOSSY, repair delivers 140: A's 80 meet N-T 60, 20 are dropped on N->T.
    query = PlacementQuery(
        prep.demand_sets["d"],
        failures=request("link", "^M\\|T$"),
        workers=1,
        states=("repair",),
        interaction="simultaneous",
    )
    (repaired,) = place(prep, query).cases[-1].states["repair"].rows
    drops = {
        prep.topology.edge_refs[int(e)].link: u for e, u in repaired.result.edge_drops
    }
    assert (repaired.result.delivered, drops) == (140, {"N|T|0": 20})


@pytest.mark.parametrize("scope", ["next_hop", "all_routers"])
def test_programmed_sets_accept_failure_policies_with_tables_per_case(scope):
    prep = dom4(scope)
    states = case_states(prep, request("link", "^(S\\|B|B\\|Y1)$"))
    assert delivered(states["converged"]) == [100, 100]
    assert states["converged"].dead_caps is None
    table = tables(prep, case_mask(prep, links=["S|B|0", "B|Y1|0"]))["t"]
    assert set(row(prep, table, "S")) == {"S|A|0"}


def test_the_controller_key_stays_the_nominal_tables():
    prep = r30()
    query = PlacementQuery(prep.demand_sets["d"], workers=1)
    nominal = project(place(prep, query))["analysis"]["controller"]
    failed = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"],
            failures=request("link", "^S\\|A1$"),
            workers=1,
            states=ALL,
        ),
    )
    assert project(failed)["analysis"]["controller"] == nominal


# --- the TARGET-INPUTS fixture ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "units", "converged_drop", "stale_drop", "group"),
    [
        (
            "{scope: link, mode: all, path: '^DC_A\\|A1$'}",
            0,
            "DC_A|A1|0",
            "DC_A|A1|0",
            0,
        ),
        ("{scope: link, mode: all, path: '^A2\\|B2$'}", 1, "DC_A|A2|0", "A2|B2|0", 1),
        ("{scope: node, mode: all, path: '^B1$'}", 0, "DC_A|A1|0", "A1|B1|0", 0),
    ],
)
def test_target_fixture_states(rule, units, converged_drop, stale_drop, group):
    # q = 1/64: 100 is 6,400 units, half on each group. The dead group's 3,200 units
    # are dropped on its own uplink in converged (a member black hole) and where they
    # meet the failure in stale. LOSSLESS stops at RR's first dead unit: DC_A->A1
    # first gives 0; A2 dead gives 1 unit.
    text = (
        FIXTURE.replace(
            "demand_set: ebb, workers: 1}",
            "demand_set: ebb, workers: 1, failure_policy: f, iterations: 1, "
            "failure_states: [converged, stale, repair]}",
        )
        + f"failures:\n  f:\n    modes:\n      - weight: 1\n        rules: [{rule}]\n"
    )
    prep = prepare(Scenario.from_yaml(text))
    case = run(prep).steps[0].result.cases[1]
    for name in ("converged", "repair"):
        result = case.states[name].rows[0].result
        assert (result.admitted, result.unadmitted) == (units, 6400 - units)
        assert case.states[name].dead_caps == (
            DeadCap("DC_B", "DC_A", "ingress", group, Fraction(1, 2)),
        )
    stale = case.states["stale"].rows[0].result
    topology = prep.topology
    assert stale.delivered == 3200
    assert {topology.edge_refs[int(e)].link: u for e, u in stale.edge_drops if u} == {
        stale_drop: 3200
    }
    ds = prep.demand_sets["ebb"]
    pattern = case.case.pattern
    mask = case_mask(prep, pattern.excluded_nodes, pattern.excluded_links)
    table = prep._controller.case_tables(topology, ds, mask, context="c")["DC_B"]
    endpoints = ds.demands[0].endpoints
    config = prep._controller.leaf_config(topology, table, endpoints, mask)
    config = ngc.FlowPolicyConfig(routing=config.routing, admission=ngc.Admission.LOSSY)
    result = ngc.evaluate_demand(
        topology.graph,
        [topology.node_id_by_name["DC_A"]],
        [topology.node_id_by_name["DC_B"]],
        ngc.EvaluationOptions(config, offer=6400),
    )
    assert result.delivered == 3200
    assert {topology.edge_refs[int(e)].link: u for e, u in result.edge_drops if u} == {
        converged_drop: 3200
    }


# --- refusal and edges -------------------------------------------------------------------------------------------

STACKED = [
    ("S", "U", 30),
    ("S", "C", 10),
    ("U", "A", 10),
    ("U", "B", 20),
    ("A", "T", 10),
    ("B", "T", 20),
    ("C", "T", 10),
]
STACKED_TREES = {
    "s": tree("S", (1, [(1, "S|U|0")]), (1, [(1, "S|C|0")])),
    "u": tree("U", (1, [(1, "U|A|0")]), (1, [(1, "U|B|0")])),
}


def test_group_states_refuse_a_programmed_router_inside_the_domain():
    demands = [demand("^S$", "^T$", 40, id="s"), demand("^U$", "^T$", 1, id="u")]
    prep = prepared(
        STACKED, "^(U|A|B|C)$", "^(S|T)$", demands, scope="group", trees=STACKED_TREES
    )
    text = (
        r"placement.states: forwarding_groups.u: router U is inside routing.igp_domain"
    )
    for iterations in (0, 3):
        failures = request("link", "^C\\|T$")
        failures = FailureRequest(failures.policy, iterations, 1)
        with pytest.raises(ValueError, match=text):
            place(
                prep,
                PlacementQuery(prep.demand_sets["d"], failures=failures, workers=1),
            )
    # Repair alone needs the tables too.
    for states in (("repair",), ("stale", "repair")):
        with pytest.raises(ValueError, match=text):
            case_states(prep, request("link", "^C\\|T$"), states)
    # A domain router programmed toward the second destination only.
    two = [
        ("S", "U", 100),
        ("U", "A", 100),
        ("U", "B", 100),
        ("A", "t1", 100),
        ("B", "t1", 100),
        ("A", "t2", 100),
        ("B", "t2", 100),
    ]
    trees = {
        "s": tree("S", (1, [(1, "S|U|0")])),
        "u": tree("U", (1, [(1, "U|A|0")]), (1, [(1, "U|B|0")])),
    }
    second = prepared(
        two,
        "^(U|A|B)$",
        "^(S|t1|t2)$",
        [demand("^S$", "^t1$", 10, id="s1"), demand("^U$", "^t2$", 10, id="u2")],
        scope="group",
        trees=trees,
    )
    with pytest.raises(ValueError, match=text):
        case_states(second, request("link", "^A\\|t1$"), ("converged",))
    # Stale alone, next_hop scope and a request without a policy run.
    stale = case_states(prep, request("link", "^C\\|T$"), states=("stale",))
    assert set(stale) == {"stale"}
    base = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"], failures=FailureRequest(None, 2), workers=1
        ),
    )
    assert len(base.cases) == 1
    hop = prepared(STACKED, "^(U|A|B|C)$", "^(S|T)$", demands)
    assert delivered(case_states(hop, request("link", "^C\\|T$"))["converged"])
    policy = request("link", "^C\\|T$").policy
    value = scenario(
        STACKED, "^(U|A|B|C)$", "^(S|T)$", demands, scope="group", trees=STACKED_TREES
    )
    step = TrafficMatrixPlacement(
        name="tm", demand_set="d", workers=1, failure_policy="f", iterations=0
    )
    with pytest.raises(ValueError, match="failure_states: forwarding_groups.u"):
        prepare(
            Scenario(
                value.network,
                (step,),
                demand_sets=value.demand_sets,
                failure_policies={"f": policy},
                units=value.units,
                routing=value.routing,
                wcmp_controller=value.wcmp_controller,
                forwarding_groups=value.forwarding_groups,
            )
        )


def test_a_dead_group_keeps_only_its_nominally_live_leaves():
    # Group 1 = {S->B, S->D}; S->D reaches t only over D-t of capacity 0, so its
    # nominal weight is 0. With B-t failed group 1 is dead and keeps S->B alone
    # within its cap: LOSSY, 50 of 100 are dropped on S->B.
    links = [
        ("S", "A", 100),
        ("A", "t", 100),
        ("S", "B", 100),
        ("B", "t", 100),
        ("S", "D", 100),
        ("D", "t", 0),
    ]
    trees = {"s": tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|B|0"), (1, "S|D|0")]))}
    prep = prepared(
        links,
        "^(A|B|D)$",
        "^(S|t)$",
        [demand("^S$", "^t$", 100, id="a")],
        scope="group",
        trees=trees,
    )
    failures = request("link", "^B\\|t$")
    cap = (DeadCap("t", "S", "s", 1, Fraction(1, 2)),)
    ordered = case_states(prep, failures, ("converged",))["converged"]
    assert (delivered(ordered), ordered.dead_caps) == ([1], cap)
    mask = case_mask(prep, links=["B|t|0"])
    assert lossy(prep, tables(prep, mask)["t"], "S", "t", 100, mask) == (
        50,
        {"S|B|0": 50},
    )


def test_every_destinations_dead_caps_reach_the_state():
    # Two destinations behind one domain; S has groups {S->A} and {S->B}. With B-t2
    # failed only the t2 table has a dead group.
    links = [
        ("S", "A", 100),
        ("S", "B", 100),
        ("A", "t1", 100),
        ("B", "t1", 100),
        ("A", "t2", 100),
        ("B", "t2", 100),
    ]
    trees = {"s": tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|B|0")]))}
    prep = prepared(
        links,
        "^(A|B)$",
        "^(S|t1|t2)$",
        [demand("^S$", "^t1$", 100, id="one"), demand("^S$", "^t2$", 100, id="two")],
        scope="group",
        trees=trees,
    )
    states = case_states(prep, request("link", "^B\\|t2$"), ("converged", "repair"))
    for state in ("converged", "repair"):
        assert states[state].dead_caps == (DeadCap("t2", "S", "s", 1, Fraction(1, 2)),)


def test_group_repair_prunes_every_route_that_no_longer_reaches_t():
    # B splits over B-Y-V-t and B-Z-W-t. With W-t failed, repair prunes Z-W and then
    # B->Z (two levels); B keeps B->Y, so group 0 stays live: nothing is lost.
    links = [
        ("S", "B", 100),
        ("B", "Y", 100),
        ("Y", "V", 100),
        ("V", "t", 100),
        ("B", "Z", 100),
        ("Z", "W", 100),
        ("W", "t", 100),
        ("S", "C", 100),
        ("C", "t", 100),
    ]
    trees = {"s": tree("S", (1, [(1, "S|B|0")]), (1, [(1, "S|C|0")]))}
    prep = prepared(
        links,
        "^(B|C|V|W|Y|Z)$",
        "^(S|t)$",
        [demand("^S$", "^t$", 100, id="s")],
        scope="group",
        trees=trees,
    )
    failures = request("link", "^W\\|t$")
    repair = case_states(prep, failures, ("converged", "repair"))["repair"]
    assert (delivered(repair), repair.dead_caps) == ([100], ())
    mask = case_mask(prep, links=["W|t|0"])
    assert (
        lossy(prep, tables(prep, mask, repair=True)["t"], "S", "t", 100, mask)[0] == 100
    )


def test_a_failed_destination():
    prep = r30()
    states = case_states(prep, request("node", "^T$"))
    for name in ("converged", "repair"):
        result = states[name].rows[0].result
        assert (result.admitted, result.termination) == (0, ngc.Termination.NO_ROUTE)
        assert states[name].dead_caps == ()
    stale = states["stale"].rows[0].result
    topology = prep.topology
    assert stale.delivered == 0
    assert {topology.edge_refs[int(e)].link: u for e, u in stale.edge_drops if u} == {
        f"A{i}|T|0": 75 for i in (1, 2, 3, 4)
    }


def test_a_nested_dead_group_keeps_its_children_within_its_cap():
    # Group 0's children 1:2 inside its half: S's row 2:4:3:3 (sixths and quarters).
    trees = {
        "s": tree(
            "S",
            (1, [(1, "S|A1|0"), (2, "S|A2|0")]),
            (1, [(1, "S|A3|0"), (1, "S|A4|0")]),
        )
    }
    prep = r30(trees=trees)
    states = case_states(prep, request("link", "^S\\|A[12]$"))
    assert states["converged"].dead_caps == (DeadCap("T", "S", "s", 0, Fraction(1, 2)),)
    mask = case_mask(prep, links=["S|A1|0", "S|A2|0"])
    table = tables(prep, mask)["T"]
    assert row(prep, table, "S") == {"S|A1|0": 2, "S|A2|0": 4, "S|A3|0": 3, "S|A4|0": 3}
    # H(300, [2, 4, 3, 3]) = 50, 100, 75, 75; the first two are dropped.
    assert lossy(prep, table, "S", "T", 300, mask) == (
        150,
        {"S|A1|0": 50, "S|A2|0": 100},
    )


def test_an_interior_node_failure_in_a_group_table():
    # Node B fails: S's group {S->B} is dead (kept and dropped on S->B); U has no
    # member left and leaves its demand's roster.
    prep = dom4()
    states = case_states(prep, request("node", "^B$"))
    s, u = (row.result for row in states["converged"].rows)
    assert s.admitted == 1
    assert (u.admitted, u.unadmitted, u.termination) == (
        0,
        100,
        ngc.Termination.NO_ROUTE,
    )
    assert states["converged"].dead_caps == (DeadCap("t", "S", "s", 1, Fraction(1, 2)),)


def test_a_zero_share_group_whose_member_fails_changes_nothing():
    links = R30_LINKS + [("S", "A5", 100, 1), ("A5", "T", 100, 2)]
    trees = {
        "s": tree(
            "S",
            (1, [(1, "S|A1|0"), (1, "S|A2|0")]),
            (1, [(1, "S|A3|0"), (1, "S|A4|0")]),
            (0, [(1, "S|A5|0")]),
        )
    }
    states = case_states(r30(links, trees), request("link", "^S\\|A[125]$"))
    assert [delivered(states[s]) for s in ALL] == [[0], [150], [0]]
    assert states["converged"].dead_caps == (DeadCap("T", "S", "s", 0, Fraction(1, 2)),)


def test_precision_misses_describe_published_converged_rows_by_their_case_table():
    # q = 1 misses the local target at S's router split. The failure case's row
    # splits over its case table's three members, the baseline's over four.
    prep = r30()
    failures = request("link", "^S\\|A1$")
    analysis = place(
        prep,
        PlacementQuery(prep.demand_sets["d"], failures=failures, workers=1, states=ALL),
    )
    routers = {
        miss.location.case_id: [
            c.members for c in miss.constraints if getattr(c, "kind", None) == "router"
        ]
        for miss in analysis.misses
    }
    assert routers == {"baseline": [4], "failure-000001": [3]}
    stale = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"], failures=failures, workers=1, states=["stale"]
        ),
    )
    assert stale.misses == ()


def test_dead_caps_reach_the_wire_on_converged_and_repair_only():
    prep = r30()
    analysis = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"],
            failures=request("link", "^S\\|A[12]$"),
            workers=1,
            states=ALL,
        ),
    )
    baseline, case = project(analysis)["analysis"]["cases"]
    cap = {
        "destination": "T",
        "router": "S",
        "forwarding_group": "s",
        "group": 0,
        "cap": {"numerator": 1, "denominator": 2},
    }
    for name in ("converged", "repair"):
        assert case["states"][name]["dead_caps"] == [cap]
        assert baseline["states"][name]["dead_caps"] == []
    assert "dead_caps" not in case["states"]["stale"]
    assert "failure" not in case["states"]["converged"]


def test_dead_groups_in_a_simultaneous_list():
    # The LOSSY figures through the product's simultaneous path: each dead cap is
    # dropped on its own member (DOM4 S 50 and U 100; Z0 equal caps 45; ZZ 60).
    def lossy_case(prep, path):
        analysis = place(
            prep,
            PlacementQuery(
                prep.demand_sets["d"],
                failures=request("link", path),
                workers=1,
                states=("converged",),
                interaction="simultaneous",
            ),
        )
        return analysis.cases[1].states["converged"].rows

    def dropped(prep, row):
        return {
            prep.topology.edge_refs[int(e)].link: u
            for e, u in row.result.edge_drops
            if u
        }

    prep = dom4()
    s, u = lossy_case(prep, "^(S\\|B|B\\|Y1)$")
    assert (s.result.delivered, dropped(prep, s), u.result.delivered) == (
        50,
        {"S|B|0": 50},
        100,
    )
    equal = z0((1, 1))
    (row,) = lossy_case(equal, "^B\\|X$")
    assert (row.result.delivered, dropped(equal, row)) == (45, {"S|B|0": 45})
    live = z0(extra=[("B", "Z", 100, 2), ("Z", "t", 100)])
    (row,) = lossy_case(live, "^B\\|X$")
    assert (row.result.delivered, dropped(live, row)) == (60, {"S|B|0": 30})


@pytest.mark.parametrize(
    ("failed", "expected"),
    [
        # g1 (share 2) keeps its cap 120; its survivor A2 carries 100; stale loses A1's 60.
        ("^S\\|A1$", [[280], [240], [280]]),
        # g1 dead: its 120 dropped at S, nothing spilled to g2's 180.
        ("^S\\|A[12]$", [[180], [180], [180]]),
        # g2 (share 3) keeps 180; A4 carries 100; stale loses A3's 90.
        ("^S\\|A3$", [[220], [210], [220]]),
    ],
)
def test_unequal_group_shares_stay_caps_in_every_state(failed, expected):
    # Router S, groups g1 share 2 {S-A1, S-A2} and g2 share 3 {S-A3, S-A4}, every link
    # 100, LOSSY offer 300 (the fixed-program simultaneous question), q = 1. Nominal:
    # g1 120 (60 + 60), g2 180 (90 + 90), all delivered.
    trees = {
        "s": tree(
            "S",
            (2, [(1, "S|A1|0"), (1, "S|A2|0")]),
            (3, [(1, "S|A3|0"), (1, "S|A4|0")]),
        )
    }
    prep = r30(trees=trees)
    analysis = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"],
            failures=request("link", failed),
            workers=1,
            states=ALL,
            interaction="simultaneous",
        ),
    )
    assert delivered(analysis.cases[0].states["converged"]) == [300]
    states = analysis.cases[1].states
    assert [delivered(states[s]) for s in ALL] == expected
