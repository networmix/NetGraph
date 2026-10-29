"""The backbone's six DC demands in one simultaneous list, baseline and one failure.

The question: backbone_clos.yml with all non-DC routers as the IGP domain and the
three DC routers as the BGP edge, the six ordered DC pairs on SHORTEST_PATHS_WCMP
at 25,312.5 each (alpha 1.6875), forwarded together as fixed programs. The failure
is the three metro1/pop2 leaf uplinks of metro1's DC. At q = 1/4096 the deliveries
are those of an independent prototype (separate filling solver, one weighted
program per demand); at a declared coarse q the test checks the exact native identities
(conservation, capacity, losses) and the figures at that q.
"""

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import netgraph_core as ngc
import pytest

from ngraph import (
    ControllerGroup,
    DemandSet,
    DirectedLink,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    FlowPolicyPreset,
    ForwardingGroup,
    GroupChild,
    PlacementQuery,
    RoutingDomain,
    Scenario,
    Selector,
    UnitsSettings,
    WCMPController,
    place,
    prepare,
)

PATH = Path(__file__).resolve().parents[2] / "scenarios/backbone_clos.yml"
FAILURE = FailureRequest(
    FailurePolicy(
        modes=[
            FailureMode(
                1,
                [
                    FailureRule(
                        "link",
                        mode="all",
                        path="^metro1/pop2/leaf/leaf(1|5|15)\\|metro1/dc1/dc/dc$",
                    )
                ],
            )
        ]
    ),
    1,
    1,
)


def backbone(scope, q=None):
    value = Scenario.from_yaml(PATH.read_text())
    matrix = value.demand_sets["baseline_traffic_matrix"]
    wcmp = DemandSet(
        matrix.name,
        tuple(
            replace(d, policy=FlowPolicyPreset.SHORTEST_PATHS_WCMP)
            for d in matrix.demands
        ),
    )
    trees = {}
    if scope == "group":
        # Each DC router: its uplinks into pop1 and into pop2, equal declared shares.
        for router in sorted(n for n in value.network.nodes if "/dc1/" in n):
            groups = {}
            for link_id, link in sorted(value.network.links.items()):
                if router in (link.source, link.target):
                    other = link.target if link.source == router else link.source
                    direction = "forward" if link.source == router else "reverse"
                    groups.setdefault(other.split("/")[1], []).append(
                        DirectedLink(link_id, direction)
                    )
            trees[router] = ForwardingGroup(
                router,
                tuple(
                    ControllerGroup(tuple(GroupChild(1, edge) for edge in members), 1)
                    for _, members in sorted(groups.items())
                ),
            )
    value = replace(
        value,
        workflow=(),
        demand_sets={matrix.name: wcmp},
        routing=RoutingDomain(Selector("^(?!.*/dc1/)"), Selector(".*/dc1/")),
        wcmp_controller=WCMPController(scope),
        forwarding_groups=trees,
        units=value.units if q is None else UnitsSettings(q),
    )
    return prepare(value, demand_sets=(matrix.name,))


def matrix(prep):
    analysis = place(
        prep,
        PlacementQuery(
            prep.demand_sets["baseline_traffic_matrix"],
            alpha=1.6875,
            interaction="simultaneous",
            states=("converged",),
            failures=FAILURE,
            outputs=ngc.OutputOptions(edge_flows=True),
        ),
    )
    assert [case.case.pattern.excluded_links for case in analysis.cases] == [
        (),
        (
            "metro1/pop2/leaf/leaf15|metro1/dc1/dc/dc|0",
            "metro1/pop2/leaf/leaf1|metro1/dc1/dc/dc|0",
            "metro1/pop2/leaf/leaf5|metro1/dc1/dc/dc|0",
        ),
    ]
    return [case.states["converged"] for case in analysis.cases]


def check_identities(topology, state):
    """Offered = delivered + drops; per-edge capacity; node conservation of carried loads."""
    assert state.failure is None
    graph = topology.graph
    caps = graph.edge_capacity_units()
    src, dst = graph.edge_sources(), graph.edge_destinations()
    total = [0] * graph.num_edges()
    for row in state.rows:
        result = row.result
        drops = dict(result.edge_drops)
        assert result.offered == result.delivered + result.source_drops + sum(
            drops.values()
        )
        balance = {}
        for edge in range(graph.num_edges()):
            carried = int(result.edge_flows[edge])
            total[edge] += carried
            tail, head = int(src[edge]), int(dst[edge])
            balance[tail] = balance.get(tail, 0) - carried - drops.get(edge, 0)
            balance[head] = balance.get(head, 0) + carried
        (source,) = [topology.node_id_by_name[n] for n in row.endpoints.sources]
        (target,) = [topology.node_id_by_name[n] for n in row.endpoints.destinations]
        for node, value in balance.items():
            if node == target:
                assert value == result.delivered
            elif node == source:
                assert value == -(result.offered - result.source_drops)
            else:
                assert value == 0
    assert all(total[e] <= int(caps[e]) for e in range(graph.num_edges()))


def deliveries(prep, state):
    q = Fraction(prep.topology.q)
    return [Fraction(row.result.delivered) * q for row in state.rows]


BASELINE = [Fraction(50625, 2)] * 6


@pytest.mark.parametrize(
    ("scope", "witness"),
    [
        (
            "next_hop",
            [
                23200,
                Fraction(98990695, 4096),
                23200,
                Fraction(98990695, 4096),
                Fraction(51816861, 2048),
                Fraction(51816861, 2048),
            ],
        ),
        (
            "all_routers",
            [23200, Fraction(50625, 2), 23200, Fraction(50625, 2), 23200, 23200],
        ),
    ],
)
@pytest.mark.parametrize("declared_q", [None, 1 / 4096], ids=["auto", "manual"])
def test_at_q_1_over_4096_the_matrix_matches_the_independent_prototype(
    scope, witness, declared_q
):
    prep = backbone(scope, q=declared_q)
    # L=physical nodes+2*links and c_min=100 give the static bound q=2^-12.
    assert prep.topology.q == 1 / 4096
    baseline, failed = matrix(prep)
    for state in (baseline, failed):
        check_identities(prep.topology, state)
    assert deliveries(prep, baseline) == BASELINE
    assert deliveries(prep, failed) == witness


@pytest.mark.parametrize(
    ("scope", "witness", "drops"),
    [
        (
            "next_hop",
            [
                23200,
                Fraction(48335, 2),
                23200,
                Fraction(48335, 2),
                Fraction(50601, 2),
                Fraction(50601, 2),
            ],
            6539,
        ),
        (
            "all_routers",
            [23200, Fraction(50625, 2), 23200, Fraction(50625, 2), 23200, 23200],
            8450,
        ),
        (
            "group",
            [
                23056,
                Fraction(47061, 2),
                23056,
                Fraction(47061, 2),
                Fraction(50625, 2),
                Fraction(50625, 2),
            ],
            8077,
        ),
    ],
)
def test_at_declared_coarse_q_the_matrix_keeps_its_identities(scope, witness, drops):
    prep = backbone(scope, q=0.25)
    assert prep.topology.q == 0.25
    baseline, failed = matrix(prep)
    for state in (baseline, failed):
        check_identities(prep.topology, state)
    assert deliveries(prep, baseline) == BASELINE
    assert deliveries(prep, failed) == witness
    lost = sum(units for row in failed.rows for _, units in row.result.edge_drops)
    assert Fraction(lost) * Fraction(prep.topology.q) == drops
