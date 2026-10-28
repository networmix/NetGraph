"""Destination tables: who is programmed, in what order, by which rule, and how they forward."""

import json
from fractions import Fraction
from io import StringIO

import netgraph_core as ngc
import pytest

from ngraph import (
    FlowPolicyPreset,
    MSDQuery,
    PlacementQuery,
    maximum_supported_demand,
    place,
    prepare,
    write_json,
)
from ngraph.model.demand import PRESETS
from tests.controller.helpers import (
    delivered,
    demand,
    lossless_oracle,
    prepared,
    row,
    scenario,
    table,
    tree,
)
from tests.results.test_report_field_plants import exact

# Stacked sources: S (BGP) with uplinks S-U 30 and S-C 10; U, a programmed source inside the domain,
# splits U-A 10 and U-B 20; A, B and C are exits to T.
STACKED = [
    ("S", "U", 30),
    ("S", "C", 10),
    ("U", "A", 10),
    ("U", "B", 20),
    ("A", "T", 10),
    ("B", "T", 20),
    ("C", "T", 10),
]
STACKED_DOMAIN, STACKED_EDGE = "^(U|A|B|C)$", "^(S|T)$"


def stacked(*demands, **kwargs):
    return prepared(STACKED, STACKED_DOMAIN, STACKED_EDGE, list(demands), **kwargs)


S_DEMAND = demand("^S$", "^T$", 40, id="s")
U_DEMAND = demand("^U$", "^T$", 1, id="u", priority=1)


def test_downstream_rows_are_finalized_before_upstream_columns():
    prep = stacked(S_DEMAND, U_DEMAND)
    assert row(prep, "T", "U") == [("U|A|0", "forward", 1), ("U|B|0", "forward", 2)]
    # S's member through U carries U's finalized 1:2: alone 30 (not 20 with ECMP at U).
    assert row(prep, "T", "S") == [("S|C|0", "forward", 1), ("S|U|0", "forward", 3)]
    assert table(prep, "T").programmed == tuple(
        prep.topology.node_id_by_name[n] for n in ("U", "S")
    )
    rows, _ = delivered(prep)
    assert rows["s|0"] == 40
    over = stacked(demand("^S$", "^T$", 41, id="s"), U_DEMAND)
    # 41 units need 31 on S-U.
    assert delivered(over)[0]["s|0"] == 40


def test_one_table_per_destination_shared_by_every_demand_of_the_set():
    prep = stacked(S_DEMAND, U_DEMAND)
    tables = prep.demand_sets["d"].controller_tables
    assert [name for name, _ in tables] == ["T"]
    programs = [d.config.routing.program for d in prep.demand_sets["d"].demands]
    # Each demand has its own program on its own endpoints, from the one table.
    assert [p.sources for p in programs] == [
        (prep.topology.node_id_by_name["S"],),
        (prep.topology.node_id_by_name["U"],),
    ]


def test_each_demand_set_is_its_own_invocation():
    prep = stacked(
        S_DEMAND, U_DEMAND, sets={"alone": [demand("^S$", "^T$", 40, id="s2")]}
    )
    assert row(prep, "T", "S") == [("S|C|0", "forward", 1), ("S|U|0", "forward", 3)]
    # Without U's demand U splits by ECMP, so S's member through U carries 20 alone.
    assert row(prep, "T", "S", "alone") == [
        ("S|C|0", "forward", 1),
        ("S|U|0", "forward", 2),
    ]


def test_a_zero_volume_demand_programs_nothing_and_changes_nothing():
    zero = demand("^U$", "^T$", 0, id="u", priority=1)
    prep = stacked(S_DEMAND, zero, sets={"alone": [demand("^S$", "^T$", 40, id="s2")]})
    assert row(prep, "T", "U") is None
    assert table(prep, "T").weights == table(prep, "T", "alone").weights
    assert table(prep, "T").programmed == table(prep, "T", "alone").programmed
    assert delivered(prep)[0]["s|0"] == delivered(prep, "alone")[0]["s2|0"] == 30


def test_faithful_ecmp_and_weighted_comparators_without_a_controller():
    from ngraph import DemandSet, Scenario, UnitsSettings
    from tests.controller.helpers import network

    links = [("S", "T", 0), ("S", "T", 10)]
    value = Scenario(
        network(links),
        demand_sets={
            "d": DemandSet(
                "d",
                (
                    demand(
                        "^S$",
                        "^T$",
                        10,
                        FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
                        id="ecmp",
                    ),
                    demand(
                        "^S$",
                        "^T$",
                        10,
                        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
                        id="wcmp",
                        priority=1,
                    ),
                ),
            )
        },
        units=UnitsSettings(1),
    )
    prep = prepare(value, demand_sets=("d",))
    # Separate ledgers: ECMP keeps the zero member (5), capacity WCMP prunes it (10).
    ecmp = prepare(
        Scenario(
            value.network,
            demand_sets={"d": DemandSet("d", value.demand_sets["d"].demands[:1])},
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )
    assert delivered(ecmp)[0] == {"ecmp|0": 5}
    wcmp = prepare(
        Scenario(
            value.network,
            demand_sets={"d": DemandSet("d", value.demand_sets["d"].demands[1:])},
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )
    assert delivered(wcmp)[0] == {"wcmp|0": 10}
    assert prep.demand_sets["d"].controller is None


def test_a_root_group_that_meets_a_zero_downstream_is_refused():
    links = [
        ("s", "a", 10),
        ("s", "b", 10),
        ("a", "m", 10),
        ("m", "t", 0),
        ("m", "t", 10),
        ("b", "t", 10),
    ]
    # m splits equally onto its zero member, so s|a carries nothing alone.
    with pytest.raises(
        ValueError,
        match=r"forwarding_groups\.g\.groups\[0\]: no member can carry traffic "
        "from router s toward t",
    ):
        prepared(
            links,
            "^(a|b|m)$",
            "^(s|t)$",
            [demand("^s$", "^t$", 4)],
            scope="group",
            trees={"g": tree("s", (1, [(1, "s|a|0")]), (1, [(1, "s|b|0")]))},
        )


def test_a_zero_member_no_traffic_reaches_is_accepted():
    links = [
        ("s", "a", 4),
        ("s", "b", 4),
        ("s", "c", 4),
        ("a", "t", 4),
        ("b", "n", 4),
        ("n", "t", 0),
        ("n", "t", 4),
        ("c", "t", 4),
    ]
    prep = prepared(
        links,
        "^(a|b|c|n)$",
        "^(s|t)$",
        [demand("^s$", "^t$", 8)],
        scope="group",
        trees={"g": tree("s", (1, [(1, "s|a|0"), (1, "s|b|0")]), (1, [(1, "s|c|0")]))},
    )
    # s->b carries nothing alone (n halves a unit onto its zero link): weight 0, and
    # its group re-flattens over s->a within the group's cap.
    assert row(prep, "t", "s") == [
        ("s|a|0", "forward", 1),
        ("s|b|0", "forward", 0),
        ("s|c|0", "forward", 1),
    ]
    assert table(prep, "t").encoding == ngc.RouteAllocation.WEIGHTED
    assert delivered(prep)[0] == {"d|0|0": 8}


FOUR = [
    ("s", "x1", 1),
    ("s", "x2", 100),
    ("s", "x3", 100),
    ("s", "x4", 100),
    ("x1", "t", 100),
    ("x2", "t", 100),
    ("x3", "t", 100),
    ("x4", "t", 100),
]


def four(*groups):
    return prepared(
        FOUR,
        "^x[1-4]$",
        "^(s|t)$",
        [demand("^s$", "^t$", 1)],
        scope="group",
        trees={"g": tree("s", *groups)},
    )


def weights_of(prep):
    return [w for _, _, w in row(prep, "t", "s")]


def test_root_shares_normalize_once_independent_of_capacity():
    prep = four(
        (2, [(1, "s|x1|0")]), (1, [(1, "s|x2|0")]), (1, [(1, "s|x3|0"), (0, "s|x4|0")])
    )
    assert weights_of(prep) == [2, 1, 1, 0]


def test_children_flatten_within_their_root_cap():
    prep = four(
        (1, [(1, "s|x1|0"), (1, "s|x2|0")]), (1, [(1, "s|x3|0"), (0, "s|x4|0")])
    )
    assert weights_of(prep) == [1, 1, 2, 0]


def test_nested_trees_flatten_exactly():
    prep = four(
        (1, [(1, [(1, "s|x1|0"), (3, "s|x2|0")]), (1, "s|x3|0")]),
        (2, [(1, "s|x4|0")]),
    )
    assert weights_of(prep) == [1, 3, 4, 16]


def test_the_flattened_whole_unit_rule():
    links = [("s", "x", 10), ("s", "x", 10), ("s", "x", 10), ("x", "t", 30)]
    prep = prepared(
        links,
        "^x$",
        "^(s|t)$",
        [demand("^s$", "^t$", 2)],
        scope="group",
        trees={"g": tree("s", (1, [(1, "s|x|0")]), (1, [(1, "s|x|1"), (1, "s|x|2")]))},
    )
    assert [w for _, _, w in row(prep, "t", "s")] == [2, 1, 1]
    _, analysis = delivered(prep, outputs=ngc.OutputOptions(edge_flows=True))
    flows = analysis.cases[0].states["converged"].rows[0].result.edge_flows
    topology = prep.topology
    carried = [int(flows[topology.edges_by_link[f"s|x|{i}"][0]]) for i in range(3)]
    # H(2, [2, 1, 1]) = [2, 0, 0]; nested splitting would give [1, 1, 0].
    assert carried == [2, 0, 0]


def ebb(zero):
    links = []
    for p in range(8):
        for i in range(4):
            a, b = f"A{p}{i}", f"B{p}{i}"
            cap = {"up": 100, "mid": 100}
            if (p, i) == (1, 2):
                cap[zero] = 0
            links += [("DC_A", a, cap["up"]), (a, b, cap["mid"]), (b, "DC_B", 100)]
    planes = [(1, [(1, f"DC_A|A{p}{i}|0") for i in range(4)]) for p in range(8)]
    return prepared(
        links,
        r"^(A|B)\d\d$",
        "^DC_",
        [demand("^DC_A$", "^DC_B$", 3200)],
        scope="group",
        trees={"planes": tree("DC_A", *planes)},
    )


@pytest.mark.parametrize("zero", ["up", "mid"])
def test_a_member_that_carries_nothing_alone_gets_zero_within_its_cap(zero):
    prep = ebb(zero)
    weights = {link: w for link, _, w in row(prep, "DC_B", "DC_A")}
    assert weights["DC_A|A12|0"] == 0
    # Plane 1's three live devices share its 1/8: each x/24 <= 100.
    assert delivered(prep)[0] == {"d|0|0": 2400}


def test_own_zero_link_reflattens_within_the_group():
    links = [
        ("s", "x1", 0),
        ("s", "x2", 10),
        ("s", "x3", 10),
        ("x1", "t", 10),
        ("x2", "t", 10),
        ("x3", "t", 10),
    ]
    prep = prepared(
        links,
        "^x[1-3]$",
        "^(s|t)$",
        [demand("^s$", "^t$", 1)],
        scope="group",
        trees={
            "g": tree("s", (1, [(1, "s|x1|0"), (1, "s|x2|0")]), (1, [(1, "s|x3|0")]))
        },
    )
    assert [w for _, _, w in row(prep, "t", "s")] == [0, 1, 1]


@pytest.mark.parametrize("shares", [(1, 1), (2, 1)])
def test_a_root_group_with_no_live_member_is_refused(shares):
    links = [("S", "T", 0), ("S", "T", 10)]
    trees = {"g": tree("S", (shares[0], [(1, "S|T|0")]), (shares[1], [(1, "S|T|1")]))}
    with pytest.raises(
        ValueError,
        match=r"forwarding_groups\.g\.groups\[0\]: no member can carry traffic "
        "from router S toward T",
    ):
        prepared(
            links, "^S$", "^T$", [demand("^S$", "^T$", 10)], scope="group", trees=trees
        )


@pytest.mark.parametrize(("dead", "expected"), [(0, 0), (3, 3)])
def test_equal_forwarding_onto_a_dead_member_stops_lossless_admission(dead, expected):
    # Why a dead root group is refused: four equal groups, one of capacity 0, under
    # EQUAL. Losing only the dead cap would deliver 22.5 of 30; the preset's lossless
    # admission stops at the first unit the round robin sends to the dead member.
    links = [("S", "T", 0 if i == dead else 10) for i in range(4)]
    prep = prepared(links, "^S$", "^T$", [demand("^S$", "^T$", 30)])
    topology = prep.topology
    endpoints = ([topology.node_id_by_name["S"]], [topology.node_id_by_name["T"]])
    program = ngc.ForwardingProgram.from_dag(
        topology.graph, *endpoints, table(prep, "T").dag
    )
    result = ngc.evaluate_demand(
        topology.graph,
        *endpoints,
        ngc.EvaluationOptions(
            ngc.FlowPolicyConfig(
                routing=ngc.Pinned(program),
                admission=PRESETS[FlowPolicyPreset.SHORTEST_PATHS_WCMP].admission,
            ),
            offer=30,
        ),
    )
    assert result.delivered == expected


WCMP_SCOPE = (
    [("DC", f"{pl}A{i}", 200) for pl in "PQ" for i in (1, 2)]
    + [
        (f"{pl}A{i}", f"{pl}B{j}", 20 if (pl, i, j) == ("Q", 1, 2) else 100)
        for pl in "PQ"
        for i in (1, 2)
        for j in (1, 2)
    ]
    + [(f"{pl}B{j}", "DCB", 200) for pl in "PQ" for j in (1, 2)]
)


def wcmp_scope_tree():
    return tree(
        "DC",
        (1, [(1, "DC|PA1|0"), (1, "DC|PA2|0")]),
        (1, [(1, "DC|QA1|0"), (1, "DC|QA2|0")]),
    )


def test_wcmp_scope_next_hop_and_group():
    def run(scope, volume, **kwargs):
        prep = prepared(
            WCMP_SCOPE,
            "^(P|Q)(A|B)[12]$",
            "^DC",
            [demand("^DC$", "^DCB$", volume)],
            scope=scope,
            **kwargs,
        )
        return prep, delivered(prep)[0]["d|0|0"]

    # next_hop: alone 200, 200, 40, 200 fit together (fluid 640); exact at q=1.
    prep, value = run("next_hop", 640)
    assert [w for _, _, w in row(prep, "DCB", "DC")] == [5, 5, 1, 5]
    assert value == 640
    # Equal plane caps: each uplink x/4, half of Q-A1's on the 20-link (fluid 160);
    # whole units admit 166 (the RR remainders).
    prep, value = run("group", 200, trees={"g": wcmp_scope_tree()})
    assert table(prep, "DCB").encoding == ngc.RouteAllocation.EQUAL
    topology = prep.topology
    graph = topology.graph
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    edges = [
        (int(e), int(sources[e]), int(targets[e]))
        for e in sorted(table(prep, "DCB").dag.via_edges())
    ]
    capacity = {e: int(graph.edge_capacity_units()[e]) for e, _, _ in edges}
    expected = lossless_oracle(
        edges, capacity, topology.node_id_by_name["DC"], topology.node_id_by_name["DCB"]
    )
    assert expected == 166
    assert value == 166


def test_precision_describes_programmed_rows_with_exact_downstream_amounts():
    links = [
        ("S", "P", 100),
        ("S", "Q", 100),
        ("P", "A", 100),
        ("P", "B", 100),
        ("A", "T", 100),
        ("B", "T", 100),
        ("Q", "T", 100),
    ]
    prep = prepared(
        links,
        "^(P|Q|A|B)$",
        "^(S|T)$",
        [demand("^S$", "^T$", 40)],
        scope="group",
        trees={"g": tree("S", (1, [(1, "S|P|0")]), (3, [(1, "S|Q|0")]))},
        q=2,
        precision=0.1,
    )
    splits = {c.label: c for c in prep.units_report.nominal_splits}
    at_p = splits["demand.d|0|0.router.P"]
    # S sends 40 * 1/4 to P, which splits it in two: bound 0.1 * 10 / 1, below q=2.
    assert at_p.incoming_physical == 10
    assert at_p.q_upper_bound == Fraction(0.1) * 10
    assert at_p.met is False
    assert splits["demand.d|0|0.router.S"].incoming_physical == 40


def controller_json(prep):
    _, analysis = delivered(prep)
    output = StringIO()
    write_json(analysis, output)
    return json.loads(output.getvalue())["analysis"]


FIXTURE_LINKS = [
    ("DC_A", "A1", 100),
    ("DC_A", "A2", 50),
    ("A1", "B1", 100),
    ("A2", "B2", 50),
    ("B1", "DC_B", 100),
    ("B2", "DC_B", 50),
]


def fixture(scope, volume=150):
    trees = {"ingress": tree("DC_A", (1, [(1, "DC_A|A1|0")]), (1, [(1, "DC_A|A2|0")]))}
    return prepared(
        FIXTURE_LINKS,
        "^(A|B)[12]$",
        "^DC_",
        [demand("^DC_A$", "^DC_B$", volume, id="dc")],
        scope=scope,
        trees=trees,
        q=1 / 64,
    )


def expected_key(first, second):
    return [
        {
            "destination": "DC_B",
            "programmed": [
                {
                    "router": "DC_A",
                    "members": [
                        {
                            "edge": {"link": "DC_A|A1|0", "direction": "forward"},
                            "weight": first,
                        },
                        {
                            "edge": {"link": "DC_A|A2|0", "direction": "forward"},
                            "weight": second,
                        },
                    ],
                }
            ],
            "source_weights": None,
        }
    ]


@pytest.mark.parametrize(
    ("scope", "weights"), [("next_hop", (2, 1)), ("group", (1, 1))]
)
def test_the_controller_key_reports_the_table_and_every_field_is_checked(
    scope, weights
):
    prep = fixture(scope)
    expected = expected_key(*weights)
    exact(controller_json(prep)["controller"], expected)
    exact(msd_json(prep)["controller"], expected)


def test_the_fixture_at_its_lossless_bound_tells_the_scopes_apart():
    assert delivered(fixture("next_hop"))[0] == {"dc|0": 9600}
    assert delivered(fixture("group"))[0] == {"dc|0": 6401}


def test_an_empty_table_is_reported_with_no_programmed_router():
    links = [("S", "U", 10), ("U", "B2", 10), ("B2", "T", 10)]
    prep = prepared(links, "^U$", "^(S|T|B2)$", [demand("^S$", "^T$", 1)])
    assert controller_json(prep)["controller"] == [
        {"destination": "T", "programmed": [], "source_weights": None}
    ]


def test_another_set_has_no_controller_key():
    prep = fixture("next_hop")
    other = prepare(
        scenario(
            FIXTURE_LINKS,
            "^(A|B)[12]$",
            "^DC_",
            [demand("^DC_A$", "^DC_B$", 1, id="dc")],
            sets={
                "plain": [
                    demand(
                        "^DC_A$",
                        "^DC_B$",
                        1,
                        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
                        id="e",
                    )
                ]
            },
        ),
        demand_sets=("d", "plain"),
    )
    assert "controller" in controller_json(prep)
    _, analysis = delivered(other, "plain")
    output = StringIO()
    write_json(analysis, output)
    assert "controller" not in json.loads(output.getvalue())["analysis"]
    # Demand sets and queries stay hashable, with and without a controller.
    for demands in (prep.demand_sets["d"], other.demand_sets["plain"]):
        assert hash(demands) == hash(PlacementQuery(demands).demands)
        hash(PlacementQuery(demands))


def test_a_cost_distribution_on_a_programmed_row_is_absent_with_its_reason():
    prep = fixture("next_hop")
    analysis = place(
        prep,
        PlacementQuery(prep.demand_sets["d"], workers=1, export_cost_distribution=True),
    )
    result = analysis.cases[0].states["converged"].rows[0]
    assert result.cost_distribution is None
    assert dict(result.unavailable_outputs) == {"cost_distribution": "controller_table"}


def test_a_te_demand_beside_a_consumer_keeps_its_native_model():
    # routing constrains the controller only: the TE demand may transit B.
    links = [
        ("S", "U", 20),
        ("U", "X", 1),
        ("U", "V", 10, 2),
        ("V", "X", 10, 2),
        ("X", "T", 11),
        ("U", "B", 20),
        ("B", "T", 20),
    ]
    prep = prepared(
        links,
        "^(U|V|X)$",
        "^(S|B|T)$",
        [
            demand("^S$", "^T$", 20, FlowPolicyPreset.TE_MAXFLOW_UNLIM, id="te"),
            demand("^S$", "^T$", 1, id="w", priority=1),
        ],
    )
    configs = {d.id: d.config.routing for d in prep.demand_sets["d"].demands}
    assert isinstance(configs["te|0"], ngc.CentralizedTE)
    assert delivered(prep)[0] == {"te|0": 20, "w|0": 0}


def test_an_all_zero_programmed_row_is_not_an_equal_row():
    # S's only member reaches U, which keeps a zero-capacity member: S carries nothing
    # alone, its row is [0], and native weighted forwarding loses S's traffic at S.
    links = [("S", "U", 10), ("U", "T", 0), ("U", "T", 10)]
    prep = prepared(links, "^U$", "^(S|T)$", [demand("^S$", "^T$", 10)])
    assert row(prep, "T", "S") == [("S|U|0", "forward", 0)]
    assert table(prep, "T").encoding == ngc.RouteAllocation.WEIGHTED
    program = prep.demand_sets["d"].demands[0].config.routing.program
    lossy = ngc.evaluate_demand(
        prep.topology.graph,
        [prep.topology.node_id_by_name["S"]],
        [prep.topology.node_id_by_name["T"]],
        ngc.EvaluationOptions(
            ngc.FlowPolicyConfig(
                routing=ngc.Pinned(program), admission=ngc.Admission.LOSSY
            ),
            offer=10,
        ),
    )
    # Equal splitting would forward it and deliver 5 through U's live link.
    assert (lossy.delivered, lossy.source_drops) == (0, 10)


# Nested liveness: S's members x1 (capacity 0), x2, x3, x4, each with a link to T.
NESTED = [("S", "X1", 0), ("S", "X2", 10), ("S", "X3", 10), ("S", "X4", 10)] + [
    (f"X{i}", "T", 10) for i in range(1, 5)
]


@pytest.mark.parametrize(
    ("inner", "weights"),
    [
        # One dead and one live member: the inner group is live and x2 takes its share.
        ([(1, "S|X1|0"), (1, "S|X2|0")], [0, 1, 1, 2]),
        # Its only positive member is dead; a zero-share live member does not revive it.
        ([(1, "S|X1|0"), (0, "S|X2|0")], [0, 0, 1, 1]),
    ],
)
def test_a_nested_child_is_live_when_a_positive_member_below_it_is(inner, weights):
    trees = {"g": tree("S", (1, [(1, inner), (1, "S|X3|0")]), (1, [(1, "S|X4|0")]))}
    prep = prepared(
        NESTED,
        "^X[1-4]$",
        "^(S|T)$",
        [demand("^S$", "^T$", 4)],
        scope="group",
        trees=trees,
    )
    assert [w for _, _, w in row(prep, "T", "S")] == weights


def test_each_destination_table_is_built_from_its_own_leaves():
    prep = prepared(
        [*STACKED, ("A", "T2", 10)],
        STACKED_DOMAIN,
        "^(S|T|T2)$",
        [S_DEMAND, demand("^U$", "^T2$", 1, id="u", priority=1)],
    )
    # Toward T only S is programmed; U splits equally, so S-U carries 20 alone.
    assert row(prep, "T", "S") == [("S|C|0", "forward", 1), ("S|U|0", "forward", 2)]
    assert row(prep, "T", "U") is None
    assert row(prep, "T2", "U") == [("U|A|0", "forward", 1)]


def test_the_controller_key_lists_routers_in_node_order():
    prep = stacked(S_DEMAND, U_DEMAND)
    assert [r.router for r in prep.demand_sets["d"].controller[0].programmed] == [
        "S",
        "U",
    ]


def test_precision_of_a_multi_source_programmed_demand():
    links = [
        ("S0", "P", 100),
        ("S1", "P", 100),
        ("P", "A", 100),
        ("P", "B", 100),
        ("A", "T", 100),
        ("B", "T", 100),
    ]
    prep = prepared(
        links,
        "^(P|A|B)$",
        "^(S0|S1|T)$",
        [demand("^(S0|S1)$", "^T$", 40)],
        q=2,
        precision=0.1,
    )
    splits = {c.label: c for c in prep.units_report.nominal_splits}
    # 40 splits equally over S0 and S1; their 20 + 20 meet at P, which splits in two.
    assert set(splits) == {"demand.d|0|0.sources", "demand.d|0|0.router.P"}
    for label in splits:
        assert (splits[label].incoming_physical, splits[label].members) == (40, 2)


def test_a_positive_amount_below_q_programs_its_source():
    u = demand("^U$", "^T$", 0.25, id="u", priority=1)
    prep = stacked(S_DEMAND, u, q=1)
    assert [
        d.nominal_units for d in prep.demand_sets["d"].demands if d.id == "u|0"
    ] == [0]
    assert row(prep, "T", "U") == [("U|A|0", "forward", 1), ("U|B|0", "forward", 2)]
    assert row(prep, "T", "S") == [("S|C|0", "forward", 1), ("S|U|0", "forward", 3)]
    assert delivered(prep)[0] == {"s|0": 40, "u|0": 0}
    # Under group U's tree is used; an unprogrammed U would leave it ignored (refused).
    trees = {
        "s": tree("S", (1, [(1, "S|C|0")]), (1, [(1, "S|U|0")])),
        "u": tree("U", (1, [(1, "U|A|0")]), (2, [(1, "U|B|0")])),
    }
    group = stacked(S_DEMAND, u, q=1, scope="group", trees=trees)
    assert row(group, "T", "U") == [("U|A|0", "forward", 1), ("U|B|0", "forward", 2)]
    assert row(group, "T", "S") == [("S|C|0", "forward", 1), ("S|U|0", "forward", 1)]


def msd_json(prep):
    output = StringIO()
    write_json(maximum_supported_demand(prep, MSDQuery(prep.demand_sets["d"])), output)
    return json.loads(output.getvalue())["analysis"]


def _member(link, weight):
    return {"edge": {"link": link, "direction": "forward"}, "weight": weight}


# Weighted-source report: H(16, [2, 1]) = [11, 5].
ALL_ROUTERS_KEY = [
    {
        "destination": "t",
        "programmed": [
            {"router": "A", "members": [_member("A|M|0", 11)]},
            {"router": "B", "members": [_member("B|M|0", 0), _member("B|X|0", 5)]},
            {"router": "M", "members": [_member("M|X|0", 3), _member("M|Y|0", 8)]},
            {"router": "X", "members": [_member("X|t|0", 8)]},
            {"router": "Y", "members": [_member("Y|t|0", 8)]},
        ],
        "source_weights": [
            {
                "source": "A",
                "nominal_physical": {"numerator": 2, "denominator": 1},
                "weight": 2,
            },
            {
                "source": "B",
                "nominal_physical": {"numerator": 1, "denominator": 1},
                "weight": 1,
            },
        ],
    }
]


def test_the_all_routers_key_in_placement_and_msd():
    from tests.controller.test_all_routers import A2, B1, merge_at_m

    prep = merge_at_m(A2, B1)
    exact(controller_json(prep)["controller"], ALL_ROUTERS_KEY)
    exact(msd_json(prep)["controller"], ALL_ROUTERS_KEY)


@pytest.mark.parametrize("scope", ["next_hop", "group", "all_routers"])
def test_the_question_names_the_declared_scope(scope):
    model = controller_json(fixture(scope))["query"]["demands"][0]["model"]
    assert model["controller"] == scope
    assert msd_json(fixture(scope))["query"]["demands"][0]["model"] == model


def test_a_router_with_parallel_members_waits_for_every_child():
    # U has two parallel members to the exit X and one to V->W->T (W->T 4), so its
    # height is 3 and it is programmed before S, whose S->Y side has height 2.
    links = [
        ("S", "U", 100),
        ("S", "Y", 100),
        ("U", "V", 10),
        ("V", "W", 10),
        ("W", "T", 4),
        ("U", "X", 10, 2),
        ("U", "X", 10, 2),
        ("X", "T", 100),
        ("Y", "T", 24),
    ]
    prep = prepared(
        links,
        "^(U|V|W|X|Y)$",
        "^(S|T)$",
        [demand("^S$", "^T$", 48, id="s"), demand("^U$", "^T$", 1, id="u", priority=1)],
    )
    order = table(prep, "T").programmed
    assert [prep.topology.node_names[r] for r in order] == ["U", "S"]
    assert row(prep, "T", "U") == [
        ("U|V|0", "forward", 2),
        ("U|X|0", "forward", 5),
        ("U|X|1", "forward", 5),
    ]
    assert row(prep, "T", "S") == [("S|U|0", "forward", 1), ("S|Y|0", "forward", 1)]


def test_the_longest_child_orders_routers_even_when_it_finishes_first():
    links = [
        ("S0", "n10", 9, 1),
        ("S0", "n12", 0, 1),
        ("S0", "n12", 7, 2),
        ("S1", "n11", 6, 2),
        ("n10", "n21", 3, 3),
        ("n10", "n22", 5, 2),
        ("n10", "n22", 8, 1),
        ("n11", "n21", 3, 1),
        ("n11", "n20", 7, 2),
        ("n11", "n22", 5, 3),
        ("n12", "n22", 12, 3),
        ("n12", "n21", 5, 3),
        ("n12", "n20", 6, 2),
        ("n20", "n30", 6, 2),
        ("n21", "n30", 3, 1),
        ("n21", "n30", 2, 3),
        ("n22", "n30", 4, 3),
        ("n30", "T", 11, 1),
        ("n10", "n11", 0, 1),
    ]
    demands = [
        demand("^S0$", "^T$", 10, id="d0"),
        demand("^S1$", "^T$", 10, id="d1", priority=1),
        demand("^n12$", "^T$", 5, id="d2", priority=2),
        demand("^n30$", "^T$", 5, id="d3", priority=3),
    ]
    prep = prepared(links, r"^n\d+$", "^(S0|S1|T)$", demands)
    order = table(prep, "T").programmed
    # Heights n30 1, n12 3, S1 4, S0 5 (through n10->n11; its child n12 gives only 4).
    assert [prep.topology.node_names[r] for r in order] == ["n30", "n12", "S1", "S0"]


def test_precision_reads_each_demand_s_own_destination_table():
    prep = prepared(
        [*STACKED, ("A", "T2", 10), ("B", "T2", 10)],
        STACKED_DOMAIN,
        "^(S|T|T2)$",
        [S_DEMAND, demand("^U$", "^T2$", 1, id="u", priority=1)],
        precision=0.1,
    )
    splits = sorted((c.label, c.members) for c in prep.units_report.nominal_splits)
    # U's demand splits over U-A and U-B toward T2; toward T only S and U programmed.
    assert splits == [
        ("demand.s|0.router.S", 2),
        ("demand.s|0.router.U", 2),
        ("demand.u|0.router.U", 2),
    ]


def test_an_unknown_destination_table_is_a_labelled_key_error():
    prep = stacked(S_DEMAND)
    with pytest.raises(
        KeyError, match="demand set d: the WCMP controller has no table toward Z"
    ):
        prep.demand_sets["d"].controller_table("Z")
