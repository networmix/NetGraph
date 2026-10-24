"""The owner's reference figures, re-derived on the port at the q its recipe chooses.

Fluid figures are derived by hand (each first hop's chain minimum, the fixed plane
caps); integer lossless bounds are checked against the independent no-drop oracle.
"""

from dataclasses import replace
from pathlib import Path

import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    FlowPolicyPreset,
    RoutingDomain,
    Scenario,
    Selector,
    UnitsSettings,
    WCMPController,
    prepare,
)
from tests.controller.helpers import (
    delivered,
    demand,
    lossless_oracle,
    network,
    prepared,
    row,
    table,
    tree,
)
from tests.controller.test_tables import WCMP_SCOPE, wcmp_scope_tree

ECMP = FlowPolicyPreset.SHORTEST_PATHS_ECMP


def ebb_links(name, plane7_cost=1):
    """Eight planes of four devices: DC_A -> A -> B (1:1) -> DC_B, links of 100."""
    links = []
    for p in range(8):
        for i in range(4):
            up = mid = down = 100
            if name in ("S2", "S6") and p >= 4:
                up = mid = down = 50
            if name in ("S3", "S6") and (p, i) == (0, 0):
                up = mid = down = 25
            if name == "S4" and (p, i) == (1, 2):
                up = mid = down = 0
            if name in ("S5", "S6") and p == 2:
                mid = 50
            a, b = f"A{p}{i}", f"B{p}{i}"
            links += [
                ("DC_A", a, up),
                (a, b, mid, plane7_cost if p == 7 else 1),
                (b, "DC_B", down),
            ]
    return links


def planes(shares=None):
    shares = shares or [1] * 8
    return tree(
        "DC_A",
        *[(shares[p], [(1, f"DC_A|A{p}{i}|0") for i in range(4)]) for p in range(8)],
    )


def ebb(name, scope="next_hop", volume=10000, q="auto", **kwargs):
    return prepared(
        ebb_links(name, **kwargs.pop("links", {})),
        r"^(A|B)\d\d$",
        "^DC_",
        [demand("^DC_A$", "^DC_B$", volume)],
        scope=scope,
        q=q,
        **kwargs,
    )


def bound(prep):
    """The native lossless bound in units, checked against the independent oracle."""
    topology = prep.topology
    graph = topology.graph
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    value = table(prep, "DC_B")
    edges = [
        (int(e), int(sources[e]), int(targets[e]))
        for e in sorted(value.dag.via_edges())
    ]
    capacity = {e: int(graph.edge_capacity_units()[e]) for e, _, _ in edges}
    weights = None if value.encoding == ngc.RouteAllocation.EQUAL else value.weights
    expected = lossless_oracle(
        edges,
        capacity,
        topology.node_id_by_name["DC_A"],
        topology.node_id_by_name["DC_B"],
        weights,
    )
    native = delivered(prep)[0]["d|0|0"]
    assert native == expected
    return native, topology.q


@pytest.mark.parametrize(
    ("name", "figure"),
    [
        ("S1", 3200),
        ("S2", 2400),
        ("S3", 3125),
        ("S4", 3100),
        ("S5", 3000),
        ("S6", 2125),
    ],
)
def test_ebb_next_hop(name, figure):
    units, q = bound(ebb(name))
    # The figures divide exactly at the chosen q: whole units lose nothing.
    assert units * q == figure


@pytest.mark.parametrize(
    ("name", "figure", "extra"),
    [
        ("S1", 3200, 0),
        ("S2", 1600, 16),
        ("S3", 800, 0),
        ("S4", 2400, 0),
        ("S5", 1600, 8),
        ("S6", 800, 0),
    ],
)
def test_ebb_groups_with_equal_fixed_plane_caps(name, figure, extra):
    prep = ebb(name, scope="group", trees={"planes": planes()})
    units, q = bound(prep)
    # Equal plane caps split by round robin over the 32 uplinks in EdgeId order: the
    # first x mod 32 members get one unit more, so the bound is 32 times the weakest
    # member plus the strong members ahead of the first weak one (16 in S2, 8 in S5).
    assert units == figure / q + extra


def test_ebb_bgp_domain_versus_igp_end_to_end():
    links = ebb_links("S1", plane7_cost=2)
    units, q = bound(ebb("S1", links={"plane7_cost": 2}))
    assert units * q == 3200
    # Native ECMP end to end skips the longer plane 7: 28 devices.
    plain = prepare(
        Scenario(
            network(links),
            demand_sets={
                "d": DemandSet("d", (demand("^DC_A$", "^DC_B$", 10000, ECMP),))
            },
        ),
        demand_sets=("d",),
    )
    assert delivered(plain)[0]["d|0|0"] * plain.topology.q == 2800


def wcmp_scope(scope, **kwargs):
    return prepared(
        WCMP_SCOPE,
        "^(P|Q)(A|B)[12]$",
        "^DC",
        [demand("^DC$", "^DCB$", 10000)],
        scope=scope,
        q="auto",
        **kwargs,
    )


def test_wcmp_scope_scopes():
    for scope, figure, kwargs in (
        ("next_hop", 640, {}),
        ("all_routers", 720, {}),
    ):
        prep = wcmp_scope(scope, **kwargs)
        units = delivered(prep)[0]["d|0|0"]
        assert units * prep.topology.q == figure
    group = wcmp_scope("group", trees={"g": wcmp_scope_tree()})
    units = delivered(group)[0]["d|0|0"]
    # Fluid 160. Whole units: Q-A1 (third uplink) halves its a units onto the 20-link,
    # a <= 2 * 20/q + 1; round robin gives it x // 4 + [x % 4 > 2]: x = 160/q + 6.
    assert units == 160 / group.topology.q + 6
    assert [w for _, _, w in row(group, "DCB", "DC")] == [1, 1, 1, 1]


@pytest.mark.parametrize(("q", "units"), [(1, 166), (1 / 4096, 655366)])
def test_wcmp_scope_native_ecmp_without_a_controller(q, units):
    prep = prepare(
        Scenario(
            network(WCMP_SCOPE),
            demand_sets={"d": DemandSet("d", (demand("^DC$", "^DCB$", 10000, ECMP),))},
            units=UnitsSettings(q),
        ),
        demand_sets=("d",),
    )
    # Fluid 160; at q=1/4096 160.00146484375.
    assert delivered(prep)[0]["d|0|0"] == units


def test_s5_ecmp_versus_controller_and_s4_native_ecmp_at_q_1():
    def native(name, preset, volume):
        prep = prepare(
            Scenario(
                network(ebb_links(name)),
                demand_sets={
                    "d": DemandSet("d", (demand("^DC_A$", "^DC_B$", volume, preset),))
                },
                units=UnitsSettings(1),
            ),
            demand_sets=("d",),
        )
        return delivered(prep)[0]["d|0|0"]

    assert native("S5", ECMP, 10000) == 1608
    assert delivered(ebb("S5", q=1))[0]["d|0|0"] == 3000
    assert native("S4", ECMP, 10000) == 6
    assert native("S4", FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY, 3100) == 3003


def test_groups_b_flattens_one_group_against_ten():
    links = [("S", "X", 10)] * 11 + [("X", "T", 200)]
    prep = prepared(
        links,
        "^X$",
        "^(S|T)$",
        [demand("^S$", "^T$", 10)],
        scope="group",
        trees={
            "g": tree(
                "S", (1, [(1, "S|X|0")]), (1, [(1, f"S|X|{i}") for i in range(1, 11)])
            )
        },
    )
    _, analysis = delivered(prep, outputs=ngc.OutputOptions(edge_flows=True))
    flows = analysis.cases[0].states["converged"].rows[0].result.edge_flows
    carried = [
        int(flows[prep.topology.edges_by_link[f"S|X|{i}"][0]]) for i in range(11)
    ]
    # Flattened weights 10:1:...:1 send all 10 units to the single member (nested: 5/1/1/1/1/1/0...).
    assert carried == [10] + [0] * 10


def test_groups_c_and_d_at_q_1_over_4096():
    # C: planes 4 x 400 and 4 x 200 declared 2:1; offer 2400 is exact in flattened units.
    c = ebb(
        "S2",
        scope="group",
        trees={"planes": planes([2] * 4 + [1] * 4)},
        volume=2400,
        q=1 / 4096,
    )
    assert delivered(c)[0]["d|0|0"] == 9830400
    # D: S4 with the plane caps kept: flattened lossless 9830400 units (nested would be 9830401).
    d = ebb("S4", scope="group", trees={"planes": planes()}, q=1 / 4096)
    assert delivered(d)[0]["d|0|0"] == 9830400


def test_the_backbone_with_its_dcs_as_bgp_edge_carries_the_whole_baseline_matrix():
    path = Path(__file__).resolve().parents[2] / "scenarios/backbone_clos.yml"
    value = Scenario.from_yaml(path.read_text())
    matrix = value.demand_sets["baseline_traffic_matrix"]
    wcmp = DemandSet(
        matrix.name,
        tuple(
            replace(d, policy=FlowPolicyPreset.SHORTEST_PATHS_WCMP)
            for d in matrix.demands
        ),
    )
    value = replace(
        value,
        workflow=(),
        demand_sets={matrix.name: wcmp},
        routing=RoutingDomain(Selector("^(?!.*/dc1/)"), Selector(".*/dc1/")),
        wcmp_controller=WCMPController(),
    )
    prep = prepare(value, demand_sets=(matrix.name,))
    rows, analysis = delivered(prep, matrix.name, alpha=1.6875)
    # Six ordered DC pairs of 25,312.5 each fit (25,312.5 x 6 = 151,875).
    totals = analysis.cases[0].states["converged"].totals
    assert totals.delivered_units * prep.topology.q == 151875
