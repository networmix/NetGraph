"""Placement and capacity questions split the same traffic by the same rules."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    EdgeWeight,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    PinnedRoutes,
    PlacementQuery,
    RouteSpec,
    Scenario,
    Selector,
    SupportSpec,
    UnitsSettings,
    WeightSpec,
    capacity,
    place,
    prepare,
)
from ngraph.model.demand import FlowPolicyPreset
from ngraph.model.network import DirectedLink
from ngraph.results import SplitConstraint
from ngraph.workflow.max_flow_step import MaxFlow

PLACED = "demand.load|0|0"
ASKED = "workflow.ask.pair[0]"


def diamond(sources=("s",)):
    network = Network(nodes={name: Node(name) for name in (*sources, "a", "b", "t")})
    for source in sources:
        network.add_link(Link(source, "a", 10, 1))
        network.add_link(Link(source, "b", 10, 1))
    network.add_link(Link("a", "t", 10, 1))
    network.add_link(Link("b", "t", 10, 1))
    return network


def splits(policy, network, design=None, **declared):
    """The nominal splits of one placed demand and of one capacity question."""
    source = Selector("^s")
    scenario = Scenario(
        network,
        [
            MaxFlow(
                name="ask",
                source=source,
                target=Selector("^t$"),
                offer=8,
                design_demand=design,
                **policy,
            )
        ],
        demand_sets={
            "load": DemandSet(
                "load",
                (DemandSpec(source, Selector("^t$"), 8, next(iter(policy.values()))),),
            )
        },
        units=UnitsSettings(1, 0.5),
        **declared,
    )
    report = prepare(scenario, demand_sets=("load",)).units_report
    found = {}
    for prefix in (PLACED, ASKED):
        found[prefix] = {
            (c.kind, c.label.removeprefix(prefix), c.incoming_physical, c.members)
            for c in report.nominal_splits
            if c.label.startswith(prefix)
        }
    return found[PLACED], found[ASKED]


def test_shortest_paths_router_split_is_the_same_for_both_questions():
    placed, asked = splits({"preset": FlowPolicyPreset.SHORTEST_PATHS_ECMP}, diamond())
    assert placed == asked == {("router", ".router.s", Fraction(8), 2)}


def test_weighted_pinned_dag_split_is_the_same_for_both_questions():
    network = diamond()
    links = {(link.source, link.target): link.id for link in network.links.values()}
    edges = tuple(
        DirectedLink(links[pair], "forward")
        for pair in (("s", "a"), ("s", "b"), ("a", "t"), ("b", "t"))
    )
    weights = WeightSpec(tuple(EdgeWeight(edge, 1) for edge in edges))
    declaration = PinnedRoutes(
        ("dag",),
        allocation=ngc.RouteAllocation.WEIGHTED,
        weight_basis=ngc.WeightBasis.EXPLICIT,
        edge_weights="w",
    )
    placed, asked = splits(
        {"model": declaration},
        network,
        routes={"dag": RouteSpec("s", support="d")},
        supports={"d": SupportSpec(edges)},
        weights={"w": weights},
    )
    assert placed == asked == {("router", ".entry[0].router.s", Fraction(8), 2)}


@pytest.mark.parametrize(
    "routing",
    [
        ngc.DistributedTE(ngc.TunnelCount(2)),
        ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(2),
        ),
    ],
)
def test_tunnel_source_and_head_splits_are_the_same_for_both_questions(routing):
    network = diamond(("s1", "s2"))
    heads = sorted(network.nodes).index("s1"), sorted(network.nodes).index("s2")
    placed, asked = splits(
        {"model": ngc.FlowPolicyConfig(routing=routing)}, network, design=8
    )
    assert (
        placed
        == asked
        == {
            ("source", ".sources", Fraction(8), 2),
            *(("tunnel", f".head[{head}]", Fraction(4), 2) for head in heads),
        }
    )


def failed_route_splits(routes, declaration, supports=None):
    """Split constraints of the case that fails node a, for both questions."""
    network = Network(nodes={name: Node(name) for name in ("s", "a", "b", "c", "t")})
    for middle in ("a", "b", "c"):
        network.add_link(Link("s", middle, 20, 1))
        network.add_link(Link(middle, "t", 20, 1))
    demand = DemandSpec(Selector("^s$"), Selector("^t$"), 12, declaration)
    prepared = prepare(
        Scenario(
            network,
            demand_sets={"d": DemandSet("d", (demand,))},
            routes=routes,
            supports=supports or {},
            units=UnitsSettings(1, 0.01),
        ),
        demand_sets=("d",),
    )
    policy = FailurePolicy(modes=(FailureMode(1, (FailureRule("node", path="^a$"),)),))
    request = FailureRequest(policy, 1, 1)
    placed = place(
        prepared, PlacementQuery(prepared.demand_sets["d"], failures=request, workers=1)
    )
    asked = capacity(
        prepared,
        CapacityQuery(
            Selector("^s$"),
            Selector("^t$"),
            prepared.demand_sets["d"].demands[0].config,
            offer=12,
            failures=request,
            workers=1,
            declaration=declaration,
        ),
    )
    assert placed.cases[1].states["converged"].rows[0].result.delivered == 12

    def failed(analysis):
        return {
            (c.kind, c.incoming_physical, c.members)
            for miss in analysis.misses
            if miss.location.case_id == "failure-000001"
            for c in miss.constraints
            if isinstance(c, SplitConstraint)
        }

    return failed(placed), failed(asked)


def test_a_failed_fixed_route_is_not_a_live_split_for_either_question():
    routes = {
        "a": RouteSpec("s", nodes=("s", "a", "t")),
        "b": RouteSpec("s", nodes=("s", "b", "t")),
    }
    placed, asked = failed_route_splits(routes, PinnedRoutes(("a", "b")))
    # Only route b survives the case, so the 12 units do not split.
    assert placed == asked == set()


def test_a_failed_weighted_dag_sibling_leaves_the_whole_amount_to_the_live_dag():
    network_edges = (("s", "b"), ("b", "t"), ("s", "c"), ("c", "t"))
    routes = {
        "a": RouteSpec("s", nodes=("s", "a", "t"), weight=1),
        "dag": RouteSpec("s", support="d", weight=2),
    }

    def edge(source, target):
        return DirectedLink(f"{source}|{target}|0", "forward")

    supports = {"d": SupportSpec(tuple(edge(*pair) for pair in network_edges))}
    placed, asked = failed_route_splits(routes, PinnedRoutes(("a", "dag")), supports)
    # Route a fails: the DAG gets 12 * 2/2, not 12 * 2/3, and splits it at s.
    assert placed == asked == {("router", Fraction(12), 2)}
