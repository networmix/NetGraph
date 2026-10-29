"""Columns, progressive filling and integer weights against independent references."""

import random
from fractions import Fraction
from math import lcm

import netgraph_core as ngc
import pytest

from ngraph.analysis.controller import fill, integer_weights, member_column, propagate
from tests.controller.helpers import (
    delivered,
    demand,
    filling_oracle,
    fluid_column,
    lossless_oracle,
    native_graph,
    prepared,
    row,
    table,
)
from tests.controller.test_tables import STACKED, STACKED_DOMAIN, STACKED_EDGE

L = 1 << 62


def alone_of(column, capacity):
    if any(capacity[e] == 0 for e in column):
        return Fraction(0)
    return min(Fraction(capacity[e]) / a for e, a in column.items())


def test_a_hand_column_through_a_finalized_downstream_row():
    prep = prepared(STACKED, STACKED_DOMAIN, STACKED_EDGE, [demand("^S$", "^T$", 1)])
    topology = prep.topology
    graph = topology.graph
    by_link = {link: ids[0] for link, ids in topology.edges_by_link.items()}
    rows = {
        topology.node_id_by_name["U"]: [(by_link["U|A|0"], 1), (by_link["U|B|0"], 2)],
        **{
            topology.node_id_by_name[n]: [(by_link[f"{n}|T|0"], 1)]
            for n in ("A", "B", "C")
        },
    }
    t = topology.node_id_by_name["T"]
    column, alone = member_column(graph, rows, by_link["S|U|0"], t)
    third = Fraction(1, 3)
    assert column == {
        by_link["S|U|0"]: 1,
        by_link["U|A|0"]: third,
        by_link["A|T|0"]: third,
        by_link["U|B|0"]: 2 * third,
        by_link["B|T|0"]: 2 * third,
    }
    assert alone == 30
    heads = {e: int(graph.edge_destinations()[e]) for e in range(graph.num_edges())}
    capacity = {e: int(c) for e, c in enumerate(graph.edge_capacity_units())}
    assert fluid_column(rows, heads, capacity, by_link["S|U|0"], t) == (column, alone)


def test_a_column_through_an_unprogrammed_zero_member_carries_nothing_alone():
    g = native_graph([(0, 1, 10), (1, 2, 0), (1, 2, 10)])
    rows = {1: [(1, 1), (2, 1)]}
    column, alone = member_column(g, rows, 0, 2)
    assert column[0] == 1 and alone == 0
    # Skipping the zero member would carry 10.
    assert member_column(g, {1: [(2, 1)]}, 0, 2)[1] == 10


def random_dag(rng, layers=4, width=3, zero=0.15, skip=0.3):
    """A DAG over layers from node 0 to one destination; returns (edges, t).

    Edges join consecutive layers; with probability ``skip`` a node also gets
    an edge to any deeper layer, so merges join paths of unequal hop count.
    Interior node ids are shuffled, so a longer path's last router may have a
    higher id than the merge it enters.
    """
    nodes = [[0]]
    count = 1
    for _ in range(layers - 1):
        layer = list(range(count, count + rng.randint(1, width)))
        count += len(layer)
        nodes.append(layer)
    t = count
    nodes.append([t])
    edges = []
    for depth in range(len(nodes) - 1):
        for u in nodes[depth]:
            if depth + 2 < len(nodes) and rng.random() < skip:
                deeper = nodes[rng.randrange(depth + 2, len(nodes))]
                edges.append((u, rng.choice(deeper), rng.randint(1, 9)))
            targets = rng.sample(
                nodes[depth + 1], rng.randint(1, len(nodes[depth + 1]))
            )
            for v in targets:
                cap = 0 if rng.random() < zero else rng.randint(1, 9)
                edges.append((u, v, cap))
        for v in nodes[depth + 1]:
            if not any(e[1] == v for e in edges):
                edges.append((rng.choice(nodes[depth]), v, rng.randint(1, 9)))
    interior = list(range(1, t))
    rng.shuffle(interior)
    label = {0: 0, t: t, **dict(zip(range(1, t), interior, strict=True))}
    return [(label[u], label[v], cap) for u, v, cap in edges], t


def test_a_column_through_a_merge_of_unequal_hop_counts():
    # H splits over H->A->X and H->C->B->X; X->t (capacity 5) carries both halves.
    edges = [(0, 1, 10), (1, 2, 10), (1, 3, 10), (2, 4, 10), (3, 5, 10), (4, 6, 5)]
    g = native_graph([*edges, (5, 4, 10)])
    rows = {1: [(1, 1), (2, 1)], 2: [(3, 1)], 3: [(4, 1)], 5: [(6, 1)], 4: [(5, 1)]}
    column, alone = member_column(g, rows, 0, 6)
    half = Fraction(1, 2)
    assert column == {0: 1, 1: half, 2: half, 3: half, 4: half, 5: 1, 6: half}
    assert alone == 5
    # End to end, S's member through H carries 5 alone beside S->Y's 10.
    links = [
        ("S", "H", 100),
        ("S", "Y", 100),
        ("H", "A", 100),
        ("H", "C", 100),
        ("A", "X", 100, 2),
        ("C", "B", 100),
        ("B", "X", 100),
        ("X", "T", 5),
        ("Y", "T", 10),
    ]
    prep = prepared(
        links, "^(H|A|B|C|X|Y)$", "^(S|T)$", [demand("^S$", "^T$", 30, id="s")]
    )
    assert row(prep, "T", "S") == [("S|H|0", "forward", 1), ("S|Y|0", "forward", 2)]
    assert delivered(prep)[0]["s|0"] == 15


def test_propagation_is_exact_for_an_integer_injection():
    g = native_graph([(0, 1, 1), (0, 2, 1), (0, 3, 1)])
    _, held, load = propagate(g, {0: [(0, 1), (1, 1), (2, 1)]}, {0: 1})
    third = Fraction(1, 3)
    assert load == {0: third, 1: third, 2: third}
    assert all(isinstance(v, Fraction) for v in (*load.values(), *held[1:]))


def test_column_twin_against_unclipped_native_forwarding():
    rng = random.Random(7)
    live = dead = 0
    for _ in range(300):
        edges, t = random_dag(rng)
        g = native_graph(edges)
        sources, targets = g.edge_sources(), g.edge_destinations()
        caps = g.edge_capacity_units()
        members = {}
        for e in range(g.num_edges()):
            members.setdefault(int(sources[e]), []).append(e)
        programmed = {u for u in members if u and rng.random() < 0.3}
        rows = {
            u: [(e, rng.randint(0, 3) if u in programmed else 1) for e in out]
            for u, out in members.items()
        }
        rows = {u: [(e, w) for e, w in out if w > 0] for u, out in rows.items()}
        router = 0
        for start in members[router]:
            column, alone = member_column(g, rows, start, t)
            heads = {e: int(targets[e]) for e in range(g.num_edges())}
            capacity = {e: int(c) for e, c in enumerate(caps)}
            assert fluid_column(rows, heads, capacity, start, t) == (column, alone)
            if alone == 0:
                dead += 1
                continue
            # Live: no zero-capacity edge on the column. Unclipped copy: every positive
            # capacity raised to at least the offer; zero capacities stay zero.
            offer = lcm(*(a.denominator for a in column.values()))
            unclipped = ngc.Graph(
                g.num_nodes(),
                [int(s) for s in sources],
                [int(d) for d in targets],
                [0 if c == 0 else max(int(c), offer) for c in caps],
                [1] * g.num_edges(),
                1.0,
            )
            assert list(unclipped.edge_sources()) == list(sources)
            dag_edges = [
                e
                for u, out in rows.items()
                for e, _ in out
                if u != router or e == start
            ]
            offsets, parents, via = [0], [], []
            for v in range(g.num_nodes()):
                for e in sorted(e for e in dag_edges if int(targets[e]) == v):
                    parents.append(int(sources[e]))
                    via.append(e)
                offsets.append(len(via))
            dag = ngc.PredecessorDAG.from_csr(unclipped, offsets, parents, via)
            weights = [0] * g.num_edges()
            for out in rows.values():
                for e, w in out:
                    weights[e] = w
            program = ngc.ForwardingProgram.from_dag(
                unclipped,
                [router],
                [t],
                dag,
                allocation=ngc.RouteAllocation.WEIGHTED,
                weight_basis=ngc.WeightBasis.EXPLICIT,
                edge_weights=weights,
            )
            result = ngc.evaluate_demand(
                unclipped,
                [router],
                [t],
                ngc.EvaluationOptions(
                    ngc.FlowPolicyConfig(
                        routing=ngc.Pinned(program), admission=ngc.Admission.LOSSY
                    ),
                    outputs=ngc.OutputOptions(edge_flows=True),
                    offer=offer,
                ),
            )
            carried = {e: int(u) for e, u in enumerate(result.edge_flows) if u}
            assert carried == {e: int(offer * a) for e, a in column.items()}
            live += 1
    assert live > 100 and dead > 50


def test_the_column_twin_mechanism_on_two_hand_witnesses():
    # Congestion: R->V 1, V->A, V->B, A->t, B->t 10; D = 2. Congested forwarding drops one
    # unit on R->V, so carried + dropped cannot give D*a; the unclipped copy can.
    edges = [(0, 1, 1), (1, 2, 10), (1, 3, 10), (2, 4, 10), (3, 4, 10)]
    g = native_graph(edges)
    rows = {1: [(1, 1), (2, 1)], 2: [(3, 1)], 3: [(4, 1)]}
    column, alone = member_column(g, rows, 0, 4)
    assert [2 * column[e] for e in range(5)] == [2, 1, 1, 1, 1] and alone == 1
    # A zero link downstream: S->U 10; U->Z 0 and U->T 10 at an unprogrammed U; Z->T 10. The column
    # halves onto the zero link: a dead column, checked against its zero.
    g = native_graph([(0, 1, 10), (1, 2, 0), (1, 3, 10), (2, 3, 10)])
    column, alone = member_column(g, {1: [(1, 1), (2, 1)], 2: [(3, 1)]}, 0, 3)
    assert column[3] == Fraction(1, 2) and alone == 0


def test_filling_on_the_hand_witness_is_fair_not_maximal():
    # a uses L1 (100) alone; b splits evenly over L1 and L2 (50).
    columns = [{"L1": Fraction(1)}, {"L1": Fraction(1, 2), "L2": Fraction(1, 2)}]
    capacity = {"L1": 100, "L2": 50}
    alone = [alone_of(c, capacity) for c in columns]
    x = fill(columns, alone, capacity)
    assert (
        x == [Fraction(200, 3), Fraction(200, 3)] == filling_oracle(columns, capacity)
    )
    assert integer_weights(x) == ([1, 1], None)
    # The same witness on a domain: exits Z1 (100) and Z2 (50) behind Q.
    links = [
        ("R", "Z1", 1000, 2),
        ("R", "Q", 1000),
        ("Q", "Z1", 1000),
        ("Q", "Z2", 1000),
        ("Z1", "T", 100),
        ("Z2", "T", 50),
    ]
    prep = prepared(links, "^(Q|Z1|Z2)$", "^(R|T)$", [demand("^R$", "^T$", 1)])
    assert {link: w for link, _, w in row(prep, "T", "R")} == {"R|Q|0": 1, "R|Z1|0": 1}


def test_filling_events_continue_for_members_not_yet_frozen():
    columns = [
        {"L1": Fraction(1)},
        {"L2": Fraction(1)},
        {"L2": Fraction(1, 2), "L3": Fraction(1, 2)},
    ]
    capacity = {"L1": 10, "L2": 40, "L3": 100}
    alone = [alone_of(c, capacity) for c in columns]
    assert alone == [10, 40, 80]
    x = fill(columns, alone, capacity)
    assert x == [10, 20, 40] == filling_oracle(columns, capacity)
    assert integer_weights(x) == ([1, 2, 4], None)
    links = [
        ("R", "E1", 1000, 2),
        ("R", "E2", 1000, 2),
        ("R", "C", 1000),
        ("C", "E2", 1000),
        ("C", "E3", 1000),
        ("E1", "T", 10),
        ("E2", "T", 40),
        ("E3", "T", 100),
    ]
    prep = prepared(links, "^(C|E1|E2|E3)$", "^(R|T)$", [demand("^R$", "^T$", 1)])
    assert {link: w for link, _, w in row(prep, "T", "R")} == {
        "R|E1|0": 1,
        "R|E2|0": 2,
        "R|C|0": 4,
    }


def test_members_that_carry_nothing_alone_get_zero():
    links = [
        ("R", "X1", 0),
        ("R", "X2", 10),
        ("R", "Y", 10),
        ("R", "W", 10),
        ("X1", "T", 10),
        ("X2", "T", 0),
        ("X2", "T", 10),
        ("Y", "T", 0),
        ("W", "T", 10),
    ]
    prep = prepared(
        links,
        "^(X1|X2|Y|W)$",
        "^(R|T)$",
        # Y is a programmed source whose only member carries nothing: an all-zero row.
        [demand("^R$", "^T$", 1), demand("^Y$", "^T$", 1, id="y", priority=1)],
    )
    assert row(prep, "T", "Y") == [("Y|T|0", "forward", 0)]
    assert {link: w for link, _, w in row(prep, "T", "R")} == {
        "R|X1|0": 0,
        "R|X2|0": 0,
        "R|Y|0": 0,
        "R|W|0": 1,
    }


def test_independent_components_need_no_special_path():
    columns = [
        {"a": Fraction(1)},
        {"a": Fraction(1, 2), "b": Fraction(1, 2)},
        {"c": Fraction(1)},
        {"d": Fraction(1)},
        {"d": Fraction(1, 2), "e": Fraction(1, 2)},
    ]
    capacity = {"a": 100, "b": 50, "c": 10, "d": 40, "e": 100}
    alone = [alone_of(c, capacity) for c in columns]
    x = fill(columns, alone, capacity)
    assert x == filling_oracle(columns, capacity)
    assert integer_weights(x) == ([20, 20, 3, 6, 12], None)


def test_filling_matches_the_event_by_event_reference():
    rng = random.Random(11)
    for case in range(500):
        n = rng.randint(1, 32)
        edges = [f"e{i}" for i in range(rng.randint(1, 16))]
        big = case % 5 == 0
        capacity = {
            e: (
                0
                if rng.random() < 0.1
                else rng.randint(1, (1 << 61) - 1 if big else 50)
            )
            for e in edges
        }
        columns = []
        for _ in range(n):
            chosen = rng.sample(edges, rng.randint(1, min(4, len(edges))))
            columns.append(
                {
                    e: Fraction(rng.randint(1, 6), rng.choice((1, 2, 3, 7)))
                    for e in chosen
                }
            )
        alone = [alone_of(c, capacity) for c in columns]
        assert fill(columns, alone, capacity) == filling_oracle(columns, capacity), case


def test_wide_routers_reduce_exactly():
    s1 = ebb_next_hop(None)
    assert {w for _, _, w in row(s1, "DC_B", "DC_A")} == {1}
    s3 = ebb_next_hop((0, 0))
    weights = {link: w for link, _, w in row(s3, "DC_B", "DC_A")}
    assert weights.pop("DC_A|A00|0") == 1 and set(weights.values()) == {4}
    # Fluid 3125 is exact in whole units: H(3125, [1, 4, ...]) = [25, 100, ...].
    assert delivered(s3)[0] == {"d|0|0": 3125}


def ebb_next_hop(degraded):
    links = []
    for p in range(8):
        for i in range(4):
            a, b = f"A{p}{i}", f"B{p}{i}"
            cap = 25 if (p, i) == degraded else 100
            links += [("DC_A", a, cap), (a, b, cap), (b, "DC_B", cap)]
    return prepared(
        links,
        r"^(A|B)\d\d$",
        "^DC_",
        [demand("^DC_A$", "^DC_B$", 3200 if degraded is None else 3125)],
    )


@pytest.mark.parametrize(
    ("shares", "weights"),
    [
        ([Fraction(1, 2), Fraction(1, 3)], [3, 2]),
        ([Fraction(0), Fraction(2, 3), Fraction(4, 3)], [0, 1, 2]),
        ([Fraction(1, 1 << 65), Fraction(1, 3 << 65)], [3, 1]),
        ([Fraction(0), Fraction(0)], [0, 0]),
    ],
)
def test_integer_weights_reduce_exactly(shares, weights):
    assert integer_weights(shares) == (weights, None)


def test_weights_at_the_native_bound_are_apportioned_with_a_reserved_unit():
    m = (L - 1) // 3
    weights, error = integer_weights(
        [Fraction(1), Fraction(L - 1, L), Fraction(L - 3, L)]
    )
    assert weights == [m + 1, m, m - 1]
    assert error == Fraction(960767920505705813, 2658455991569831745231153368257265664)
    g = native_graph([(0, 1, m + 1), (0, 1, m), (0, 1, m - 1)])

    def bound(w):
        dag = ngc.PredecessorDAG.from_csr(g, [0, 0, 3], [0, 0, 0], [0, 1, 2])
        program = ngc.ForwardingProgram.from_dag(
            g,
            [0],
            [1],
            dag,
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights=w,
        )
        return ngc.evaluate_demand(
            g,
            [0],
            [1],
            ngc.EvaluationOptions(ngc.FlowPolicyConfig(routing=ngc.Pinned(program))),
        ).delivered

    assert bound(weights) == L - 1
    # The fallback [m, m, m] loses one unit.
    assert bound([m, m, m]) == L - 2
    tiny, error = integer_weights([Fraction(1), Fraction(1, 1 << 70)])
    # Every positive share keeps a unit; flooring would give [L - 1, 0].
    assert tiny == [L - 2, 1]
    assert error == Fraction((1 << 70) - L + 2, L - 1)


def test_next_hop_tables_never_need_a_refusal_and_forward_as_the_oracle_says():
    rng = random.Random(3)
    checked = 0
    for _ in range(60):
        edges, t = random_dag(rng, layers=4, width=3, zero=0.2)
        names = {v: f"n{v}" for e in edges for v in e[:2]}
        names[0], names[t] = "S", "T"
        links = [(names[u], names[v], cap) for u, v, cap in edges]
        if not any(u == "S" for u, _, _ in links):
            continue
        domain = "^n\\d+$"
        prep = prepared(links, domain, "^(S|T)$", [demand("^S$", "^T$", 1000)])
        topology = prep.topology
        graph = topology.graph
        sources, targets = graph.edge_sources(), graph.edge_destinations()
        value = table(prep, "T")
        dag = [
            (int(e), int(sources[e]), int(targets[e]))
            for e in sorted(value.dag.via_edges())
        ]
        capacity = {e: int(graph.edge_capacity_units()[e]) for e, _, _ in dag}
        weights = None if value.encoding == ngc.RouteAllocation.EQUAL else value.weights
        expected = lossless_oracle(
            dag,
            capacity,
            topology.node_id_by_name["S"],
            topology.node_id_by_name["T"],
            weights,
        )
        assert delivered(prep)[0]["d|0|0"] == min(1000, expected)
        checked += 1
    assert checked > 40


def test_the_apportionment_equals_the_unit_by_unit_rule():
    from ngraph.analysis.controller import apportion

    def unit_by_unit(weights, total):
        held = [1 if w else 0 for w in weights]
        for _ in range(total - sum(held)):
            best = None
            for i, w in enumerate(weights):
                if w and (
                    best is None or w * (held[best] + 1) > weights[best] * (held[i] + 1)
                ):
                    best = i
            held[best] += 1
        return held

    rng = random.Random(5)
    for _ in range(3000):
        weights = [rng.randint(0, 40) for _ in range(rng.randint(1, 6))]
        positive = sum(1 for w in weights if w)
        if not positive:
            continue
        total = rng.randint(positive, 60)
        assert apportion(weights, total) == unit_by_unit(weights, total), (
            weights,
            total,
        )


def test_highest_averages_lower_quota_oracle_keeps_unit_priority_and_ties():
    from tests.controller.helpers import highest_averages

    # Independent one-unit construction controls the accelerated test oracle.
    for weights in ([1, 1, 1], [2, 1], [0, 7, 2, 0, 1], [1, 1000, 1], [0, 0]):
        allocated = [0] * len(weights)
        for total in range(31):
            assert highest_averages(total, weights) == allocated
            if any(weights):
                index = max(
                    (i for i, w in enumerate(weights) if w),
                    key=lambda i: (Fraction(weights[i], allocated[i] + 1), -i),
                )
                allocated[index] += 1
