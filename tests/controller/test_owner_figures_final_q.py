"""The owner's figures at the q the recipe chooses, against independent oracles.

Every question is prepared with automatic q (precision 0.001), as declared. The
oracles share no code with the product: round robin over a source's members in
EdgeId order (ECMP keeps a zero-capacity member), highest averages over explicit
or flattened weights (a zero-capacity member has weight 0), and for tunnel counts
the chains' fluid sizing, round robin over the plan's tunnels and the per-chain
minimum. Values at q = 1 or 1/4096 are kept only as labelled comparisons.
"""

import math
from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    PlacementQuery,
    Scenario,
    Selector,
    TunnelCountQuery,
    UnitsSettings,
    place,
    prepare,
    run,
    tunnel_counts,
)
from ngraph.workflow import TunnelCountAnalysis
from tests.controller.helpers import delivered, demand, network, prepared, tree
from tests.controller.test_owner_figures import bound, ebb, ebb_links, planes
from tests.controller.test_tables import WCMP_SCOPE

ECMP, ECMP_LOSSY = (
    FlowPolicyPreset.SHORTEST_PATHS_ECMP,
    FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
)
IDEAL = {"S1": 3200, "S2": 2400, "S3": 3125, "S4": 3100, "S5": 3000, "S6": 2125}


def rr(x, k):
    return [x // k + (1 if i < x % k else 0) for i in range(k)]


def highest_averages(total, weights):
    w_sum = sum(weights)
    shares = [total * w // w_sum if w_sum else 0 for w in weights]
    for _ in range(total - sum(shares)):
        best = max(
            (i for i, w in enumerate(weights) if w),
            key=lambda i: (Fraction(weights[i], shares[i] + 1), -i),
        )
        shares[best] += 1
    return shares


def largest(fits, high):
    lo, hi = 0, high
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid - 1)
    return lo


def chain_minima(state, q):
    """DC_A's 32 members' chain minimums in units, in device order (DC_A's EdgeId order)."""
    caps = {(u, v): c for u, v, c, *_ in ebb_links(state)}
    out = []
    for p in range(8):
        for i in range(4):
            a, b = f"A{p}{i}", f"B{p}{i}"
            low = min(caps[("DC_A", a)], caps[(a, b)], caps[(b, "DC_B")])
            out.append(int(Fraction(low) / Fraction(q)))
    return out


def physical(units, q):
    return Fraction(units) * Fraction(q)


# --- tunnel counts (PLAN 5.3: S2 curve, S1-S6 rows at 32, 64 and up to 256) -------------


def t2(k, up_to=False):
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(k, up_to=up_to),
            prefer_headroom=True,
        )
    )


def count_rows(state, counts, q="auto"):
    spec = DemandSpec(
        Selector("^DC_A$"), Selector("^DC_B$"), IDEAL[state], t2(256, True), id="te"
    )
    step = TunnelCountAnalysis(
        "counts",
        demand_set="d",
        counts=counts,
        up_to=256,
        design_demand=IDEAL[state],
        offer=IDEAL[state],
    )
    prep = prepare(
        Scenario(
            network(ebb_links(state)),
            (step,),
            demand_sets={"d": DemandSet("d", (spec,))},
            units=UnitsSettings(q),
        )
    )
    if q == "auto":
        analysis = run(prep).steps[0].result
    else:
        query = TunnelCountQuery(
            prep.demand_sets["d"], counts, IDEAL[state], IDEAL[state], up_to=256
        )
        analysis = tunnel_counts(prep, query)
    return prep, analysis.rows


def check_tunnel_oracles(prep, state, row):
    """U, F and the lossy delivery of one row, from the chains alone."""
    topology, q = prep.topology, prep.topology.q
    minima = chain_minima(state, q)
    chain_of = {}
    for index, (p, i) in enumerate((p, i) for p in range(8) for i in range(4)):
        chain_of[topology.edges_by_link[f"DC_A|A{p}{i}|0"][0]] = index
    plan = row.result.plan
    tunnels = row.result.program.tunnels
    chosen = plan.tunnels_per_head

    def fluid_ok(s):
        return sum(c // s for c in minima) >= chosen

    size = largest(lambda s: s >= 1 and fluid_ok(s), max(minima)) if fluid_ok(1) else 0
    assert plan.max_bandwidth_per_tunnel == size
    k = len(tunnels)
    on = [chain_of[t.edges[0]] for t in tunnels]

    def fits(x):
        load = {}
        for j, amount in enumerate(rr(x, k)):
            load[on[j]] = load.get(on[j], 0) + amount
        return all(load[c] <= minima[c] for c in load)

    bound_units = largest(fits, sum(minima) + k)
    assert plan.max_lossless_offer == bound_units
    units = int(IDEAL[state] / q)
    load = {}
    for j, amount in enumerate(rr(units, k)):
        load[on[j]] = load.get(on[j], 0) + amount
    assert row.result.delivered == sum(min(v, minima[c]) for c, v in load.items())
    assert row.lossless_at_design_units == min(units, bound_units)
    assert plan.total_tunnel_cost == 3 * k


S2_CURVE = (8, 16, 24, 32, 48, 64, 96, 128)


def test_the_s2_count_curve_at_the_final_q():
    prep, rows = count_rows("S2", S2_CURVE)
    q = prep.topology.q
    # The up-to row's 256 members bind the recipe: 0.001 * 2400 / 255 -> 2^-7.
    assert q == 1 / 128
    for row in rows:
        check_tunnel_oracles(prep, "S2", row)
    lossless = [physical(r.lossless_at_design_units, q) for r in rows]
    # k = 64: U = floor(12800 / 3) = 4266, and the first three tunnels share one 100-chain
    # with 2 spare units: F = 64 * 4266 + 2 = 273026 units. k = 128: U = 2133, F = 273026.
    assert lossless[:-1] == [
        800,
        1600,
        1200,
        1600,
        2400,
        Fraction(273026, 128),
        2400,
        Fraction(273026, 128),
    ]
    assert (rows[-1].result.plan.tunnels_per_head, lossless[-1]) == (48, 2400)
    # S2 lossy at 64: shares 4800 units; 100-chains capped at 12800 (16), 50-chains 4800 (16).
    assert physical(rows[5].result.delivered, q) == 2200


def test_the_s2_count_curve_at_q_1_is_e2s_curve():
    # Labelled comparison: E2's figures were whole units at q = 1.
    prep, rows = count_rows("S2", S2_CURVE, q=1)
    assert [r.lossless_at_design_units for r in rows[:-1]] == [
        800,
        1600,
        1200,
        1600,
        2400,
        2113,
        2400,
        2052,
    ]
    assert (
        rows[-1].result.plan.tunnels_per_head,
        rows[-1].lossless_at_design_units,
    ) == (48, 2400)


@pytest.mark.parametrize(
    ("state", "final", "at_q1"),
    [
        # (lossless at D, lossy) for k = 32 and k = 64, then the up-to choice and its lossless.
        ("S1", (3200, 3200, 3200, 3200, 32, 3200), (3200, 3200, 3200, 3200, 32, 3200)),
        (
            "S2",
            (1600, 1600, Fraction(273026, 128), 2200, 48, 2400),
            (1600, 1600, 2113, 2192, 48, 2400),
        ),
        (
            "S3",
            (
                1600,
                Fraction(387800, 128),
                Fraction(273026, 128),
                Fraction(388100, 128),
                125,
                3125,
            ),
            (1600, 3029, 2113, 3031, 125, 3125),
        ),
        (
            "S4",
            (
                1600,
                Fraction(384800, 128),
                Fraction(273026, 128),
                Fraction(385200, 128),
                31,
                3100,
            ),
            (1600, 3006, 2113, 3006, 31, 3100),
        ),
        # S5 k = 32: s* = 50, U = 6400; the first 8 chains keep 6400 spare: F = 204800 + 8.
        (
            "S5",
            (
                Fraction(204808, 128),
                2825,
                Fraction(273026, 128),
                Fraction(363200, 128),
                60,
                3000,
            ),
            (1608, 2824, 2113, 2836, 60, 3000),
        ),
        (
            "S6",
            (1600, 1600, 1600, Fraction(237350, 128), 85, 2125),
            (1600, 1600, 1600, 1848, 85, 2125),
        ),
    ],
)
def test_t2_rows_of_every_ebb_state(state, final, at_q1):
    prep, rows = count_rows(state, (32, 64))
    q = prep.topology.q
    assert q == 1 / 128
    for row in rows:
        check_tunnel_oracles(prep, state, row)
    k32, k64, limit = rows
    assert (
        physical(k32.lossless_at_design_units, q),
        physical(k32.result.delivered, q),
        physical(k64.lossless_at_design_units, q),
        physical(k64.result.delivered, q),
        limit.result.plan.tunnels_per_head,
        physical(limit.lossless_at_design_units, q),
    ) == final
    _, rows = count_rows(state, (32, 64), q=1)
    k32, k64, limit = rows
    assert (
        k32.lossless_at_design_units,
        k32.result.delivered,
        k64.lossless_at_design_units,
        k64.result.delivered,
        limit.result.plan.tunnels_per_head,
        limit.lossless_at_design_units,
    ) == at_q1


# --- controller and native figures -------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value", "extra"),
    [
        ("S1", 3200, 0),
        ("S2", 1600, 16),
        ("S3", 800, 0),
        ("S4", 2400, 0),
        ("S5", 1600, 8),
        ("S6", 800, 0),
    ],
)
def test_ebb_groups_physical_at_the_final_q(name, value, extra):
    units, q = bound(ebb(name, scope="group", trees={"planes": planes()}))
    assert physical(units, q) == value + extra * Fraction(q)


def native_ebb(state, policy, volume):
    prep = prepare(
        Scenario(
            network(ebb_links(state)),
            demand_sets={
                "d": DemandSet("d", (demand("^DC_A$", "^DC_B$", volume, policy),))
            },
        ),
        demand_sets=("d",),
    )
    rows = place(
        prep, PlacementQuery(prep.demand_sets["d"], states=("converged",), workers=1)
    )
    return rows.cases[0].states["converged"].rows[0].result.delivered, prep.topology.q


@pytest.mark.parametrize(
    ("state", "q", "figure", "q1"),
    [("S2", 1 / 16, 1601, 1616), ("S5", 1 / 16, Fraction(3201, 2), 1608)],
)
def test_native_ecmp_lossless_at_the_final_q(state, q, figure, q1):
    units, chosen = native_ebb(state, ECMP, 10000)
    minima = chain_minima(state, chosen)
    assert chosen == q
    assert units == largest(
        lambda x: all(a <= c for a, c in zip(rr(x, 32), minima, strict=True)),
        sum(minima) + 32,
    )
    # 1600 plus one unit for each strong member ahead of the first weak one (16 in S2, 8 in S5).
    assert physical(units, chosen) == figure
    assert native_ebb_q1(state, ECMP, 10000) == q1


def native_ebb_q1(state, policy, volume):
    prep = prepare(
        Scenario(
            network(ebb_links(state)),
            demand_sets={
                "d": DemandSet("d", (demand("^DC_A$", "^DC_B$", volume, policy),))
            },
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )
    rows = place(
        prep, PlacementQuery(prep.demand_sets["d"], states=("converged",), workers=1)
    )
    return rows.cases[0].states["converged"].rows[0].result.delivered


def test_native_ecmp_s4_keeps_its_zero_member_at_the_final_q():
    units, q = native_ebb("S4", ECMP, 10000)
    # The first 6 units avoid the zero-capacity seventh member.
    assert (q, units, physical(units, q)) == (1 / 8, 6, Fraction(3, 4))
    units, q = native_ebb("S4", ECMP_LOSSY, 3100)
    minima = chain_minima("S4", q)
    offer = int(Fraction(3100) / Fraction(q))
    assert units == sum(min(a, c) for a, c in zip(rr(offer, 32), minima, strict=True))
    # 3100 / q = 49600 units, 1550 per member, the zero member's 1550 lost.
    assert (q, units, physical(units, q)) == (1 / 16, 48050, Fraction(24025, 8))
    assert (
        native_ebb_q1("S4", ECMP, 10000),
        native_ebb_q1("S4", ECMP_LOSSY, 3100),
    ) == (6, 3003)


def test_wcmp_scope_native_ecmp_at_the_final_q():
    prep = prepare(
        Scenario(
            network(WCMP_SCOPE),
            demand_sets={"d": DemandSet("d", (demand("^DC$", "^DCB$", 10000, ECMP),))},
        ),
        demand_sets=("d",),
    )
    q = Fraction(prep.topology.q)
    units = delivered(prep)[0]["d|0|0"]
    # QA1 (third uplink) halves its arrival onto the 20-link: x = 4 (40/q + 1) + 2 units.
    assert (q, units) == (Fraction(1, 32), int(4 * (40 / q + 1) + 2))
    assert physical(units, q) == 160 + 6 * q


def raw_plane(state, volume, admission):
    links = ebb_links(state)
    caps = {(u, v): c for u, v, c, *_ in links}
    plane = [
        sum(
            min(
                caps[("DC_A", f"A{p}{i}")],
                caps[(f"A{p}{i}", f"B{p}{i}")],
                caps[(f"B{p}{i}", "DC_B")],
            )
            for i in range(4)
        )
        for p in range(8)
    ]
    nodes = sorted({u for u, *_ in links} | {v for _, v, *_ in links})
    lines = ["network:", "  nodes:", *[f"    {n}: {{}}" for n in nodes], "  links:"]
    entries = []
    for u, v, c, *cost in links:
        lines.append(
            f"    - {{source: {u}, target: {v}, capacity: {c}, cost: {cost[0] if cost else 1}}}"
        )
        weight = plane[int(v[1])] if u == "DC_A" else 1
        entries.append(
            f"      - {{edge: {{link: '{u}|{v}|0', direction: forward}}, value: {weight}}}"
        )
    lines += ["weights:", "  raw:", "    entries:", *entries, "demands:", "  d:"]
    lines.append(
        f"    - {{id: d, source: '^DC_A$', target: '^DC_B$', volume: {volume}, model: {{routing: "
        "{type: shortest_paths, allocation: weighted, weight_basis: explicit, edge_weights: raw}, "
        f"admission: {admission}}}}}"
    )
    prep = prepare(Scenario.from_yaml("\n".join(lines)), demand_sets=("d",))
    result = place(
        prep, PlacementQuery(prep.demand_sets["d"], states=("converged",), workers=1)
    )
    q = prep.topology.q
    minima = chain_minima(state, q)
    weights = [plane[p] if minima[p * 4 + i] else 0 for p in range(8) for i in range(4)]
    return (
        result.cases[0].states["converged"].rows[0].result.delivered,
        q,
        minima,
        weights,
    )


@pytest.mark.parametrize(
    ("state", "q", "figure", "q1"),
    [
        ("S3", 1 / 32, Fraction(30780, 32), 968),
        ("S6", 1 / 32, Fraction(20920, 32), 648),
        ("S4", 1 / 8, 3025, 3025),
    ],
)
def test_raw_plane_weights_lossless_at_the_final_q(state, q, figure, q1):
    units, chosen, minima, weights = raw_plane(state, 10000, "lossless")
    assert chosen == q
    assert units == largest(
        lambda x: all(
            a <= c for a, c in zip(highest_averages(x, weights), minima, strict=True)
        ),
        sum(minima),
    )
    assert physical(units, q) == figure


def test_raw_plane_s4_lossy_at_the_final_q():
    units, q, minima, weights = raw_plane("S4", 3100, "lossy")
    offer = int(Fraction(3100) / Fraction(q))
    assert units == sum(
        min(a, c) for a, c in zip(highest_averages(offer, weights), minima, strict=True)
    )
    assert (q, physical(units, q)) == (1 / 16, Fraction(48490, 16))


@pytest.mark.parametrize(
    ("members", "groups", "volume", "carried"),
    [
        (3, [(1, [0]), (1, [1, 2])], 2, [1, Fraction(1, 2), Fraction(1, 2)]),
        (11, [(1, [0]), (1, list(range(1, 11)))], 10, [5] + [Fraction(1, 2)] * 10),
    ],
)
def test_groups_a_and_b_at_the_final_q(members, groups, volume, carried):
    links = [("S", "X", 10)] * members + [("X", "T", 200)]
    prep = prepared(
        links,
        "^X$",
        "^(S|T)$",
        [demand("^S$", "^T$", volume)],
        scope="group",
        q="auto",
        trees={
            "g": tree(
                "S",
                *[(share, [(1, f"S|X|{i}") for i in index]) for share, index in groups],
            )
        },
    )
    _, analysis = delivered(prep, outputs=ngc.OutputOptions(edge_flows=True))
    flows = analysis.cases[0].states["converged"].rows[0].result.edge_flows
    q = Fraction(prep.topology.q)
    units = [
        int(flows[prep.topology.edges_by_link[f"S|X|{i}"][0]]) for i in range(members)
    ]
    flat = [Fraction(share, len(index)) for share, index in groups for _ in index]
    scale = 1
    for f in flat:
        scale = scale * f.denominator // math.gcd(scale, f.denominator)
    assert q == Fraction(1, 1024)
    assert units == highest_averages(int(volume / q), [int(f * scale) for f in flat])
    assert [physical(u, q) for u in units] == carried


def test_groups_c_and_d_at_the_final_q():
    c = ebb(
        "S2",
        scope="group",
        trees={"planes": planes([2] * 4 + [1] * 4)},
        volume=2400,
        q="auto",
    )
    assert (c.topology.q, physical(delivered(c)[0]["d|0|0"], c.topology.q)) == (
        1 / 16,
        2400,
    )
    units, q = bound(ebb("S4", scope="group", trees={"planes": planes()}, q="auto"))
    assert (q, physical(units, q)) == (1 / 8, 2400)
