import pytest
from ngraph.network import Network, Node, Link
from ngraph.traffic_demand import TrafficDemand
from ngraph.lib.flow_policy import FlowPolicyConfig
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.base import MIN_FLOW

from ngraph.traffic_manager import TrafficManager


@pytest.fixture
def small_network() -> Network:
    """
    Build a small test network with 3 nodes and 2 directed links:
      A -> B, B -> C.
    Link capacities are large enough so we can place all demands easily.
    """
    net = Network()

    # Add nodes
    net.add_node(Node(name="A"))
    net.add_node(Node(name="B"))
    net.add_node(Node(name="C"))

    # Add links
    link_ab = Link(source="A", target="B", capacity=100.0, cost=1.0)
    link_bc = Link(source="B", target="C", capacity=100.0, cost=1.0)
    net.add_link(link_ab)
    net.add_link(link_bc)

    return net


@pytest.fixture
def small_network_with_loop() -> Network:
    """
    Builds a small network with a loop: A -> B, B -> C, C -> A.
    This can help test re-optimization more interestingly.
    """
    net = Network()

    # Add nodes
    net.add_node(Node(name="A"))
    net.add_node(Node(name="B"))
    net.add_node(Node(name="C"))

    # Add links forming a loop
    net.add_link(Link(source="A", target="B", capacity=10.0, cost=1.0))
    net.add_link(Link(source="B", target="C", capacity=10.0, cost=1.0))
    net.add_link(Link(source="C", target="A", capacity=10.0, cost=1.0))

    return net


def test_build_graph_not_built_error(small_network):
    """
    Verify that calling place_all_demands before build_graph
    raises a RuntimeError.
    """
    tm = TrafficManager(network=small_network, traffic_demands=[])
    # no build_graph call here
    with pytest.raises(RuntimeError):
        tm.place_all_demands()


def test_basic_build_and_expand(small_network):
    """
    Test the ability to build the graph and expand demands.
    """
    demands = [
        TrafficDemand(source_path="A", sink_path="B", demand=10.0),
        TrafficDemand(source_path="A", sink_path="C", demand=20.0),
    ]
    tm = TrafficManager(
        network=small_network,
        traffic_demands=demands,
        default_flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )

    tm.build_graph()
    assert isinstance(tm.graph, StrictMultiDiGraph), "Graph should be built"
    assert len(tm.graph.get_nodes()) == 3, "Should have 3 nodes in graph"
    assert len(tm.graph.get_edges()) == 4, "Should have 4 edges in graph"

    tm.expand_demands()
    assert len(tm.demands) == 2, "Expected 2 expanded demands"


def test_place_all_demands_simple(small_network):
    """
    Place demands on a simple A->B->C network.
    We expect all to be placed because capacity = 100 is large.
    """
    demands = [
        TrafficDemand(source_path="A", sink_path="C", demand=50.0),
        TrafficDemand(source_path="B", sink_path="C", demand=20.0),
    ]
    tm = TrafficManager(network=small_network, traffic_demands=demands)

    tm.build_graph()
    tm.expand_demands()

    total_placed = tm.place_all_demands()
    assert total_placed == 70.0, "All traffic should be placed without issues"

    # Check final placed_demand on each Demand
    for d in tm.demands:
        assert (
            abs(d.placed_demand - d.volume) < MIN_FLOW
        ), "Each demand should be fully placed"

    # Summarize link usage
    usage = tm.summarize_link_usage()
    # For A->B->C route, we expect 50 flow to pass A->B, and 50 + 20 = 70 on B->C
    # However, the B->C link capacity is 100, so it can carry 70 total
    ab_key = None
    bc_key = None
    for k, (src, dst, _, _) in tm.graph.get_edges().items():
        if src == "A" and dst == "B":
            ab_key = k
        elif src == "B" and dst == "C":
            bc_key = k

    # usage[...] is how much capacity is used, i.e. used_capacity
    assert abs(usage[ab_key] - 50.0) < MIN_FLOW, "A->B should carry 50"
    assert abs(usage[bc_key] - 70.0) < MIN_FLOW, "B->C should carry 70"


def test_priority_fairness(small_network):
    """
    Test that multiple demands with different priorities
    are handled in ascending priority order (lowest numeric = highest priority).
    For demonstration, we set small link capacities that will cause partial placement.
    """
    # Reduce link capacity to 30 to test partial usage
    small_network.links[next(iter(small_network.links))].capacity = 30.0  # A->B
    small_network.links[list(small_network.links.keys())[1]].capacity = 30.0  # B->C

    # High priority demand: A->C with volume=40
    # Low priority demand: B->C with volume=40
    # Expect: The higher priority (A->C) saturates B->C first.
    # Then the lower priority (B->C) might get leftover capacity (if any).
    demands = [
        TrafficDemand(
            source_path="A", sink_path="C", demand=40.0, priority=0
        ),  # higher priority
        TrafficDemand(
            source_path="B", sink_path="C", demand=40.0, priority=1
        ),  # lower priority
    ]
    tm = TrafficManager(network=small_network, traffic_demands=demands)

    tm.build_graph()
    tm.expand_demands()
    total_placed = tm.place_all_demands(placement_rounds=1)  # single pass for clarity

    # The link B->C capacity is 30, so the first (priority=0) can fully use it
    # or saturate it. Actually we have A->B->C route for the first demand, so
    # the capacity from A->B->C is 30 end-to-end.
    # The second demand (B->C direct) sees the same link capacity but it's
    # already used up by the higher priority. So it gets 0.
    assert total_placed == 30.0, "Expected only 30 placed in total"

    # Check each demand's placed
    high_prio_placed = tm.demands[0].placed_demand
    low_prio_placed = tm.demands[1].placed_demand
    assert high_prio_placed == 30.0, "High priority demand should saturate capacity"
    assert low_prio_placed == 0.0, "Low priority got no leftover capacity"


def test_reset_flow_usages(small_network):
    """
    Test that reset_all_flow_usages zeroes out placed demand.
    """
    demands = [TrafficDemand(source_path="A", sink_path="C", demand=10.0)]
    tm = TrafficManager(network=small_network, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()
    placed_before = tm.place_all_demands()
    assert placed_before == 10.0

    # Now reset all flows
    tm.reset_all_flow_usages()
    for d in tm.demands:
        assert d.placed_demand == 0.0, "Demand placed_demand should be reset to 0"
    usage = tm.summarize_link_usage()
    for k in usage:
        assert usage[k] == 0.0, "Link usage should be reset to 0"


def test_reoptimize_flows(small_network_with_loop):
    """
    Test that re-optimization logic is triggered in place_all_demands
    when reoptimize_after_each_round=True.
    We'll set the capacity on one link to be quite low so the flow might
    switch to a loop path under re-optimization, if feasible.
    """
    # Example: capacity A->B=10, B->C=1, C->A=10
    # Demand from A->C is 5, so if direct path A->B->C is tried first,
    # it sees only capacity=1 for B->C. Then re-optimization might try A->B->C->A->B->C
    # (though that is cyclical and might or might not help, depending on your path alg).
    # This test just ensures we call the reopt method, not necessarily that it
    # finds a truly cyclical route. Implementation depends on path selection logic.
    # We'll do a small check that the reopt code doesn't crash and usage is consistent.
    demands = [TrafficDemand(source_path="A", sink_path="C", demand=5.0)]
    tm = TrafficManager(
        network=small_network_with_loop,
        traffic_demands=demands,
        default_flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )
    tm.build_graph()
    tm.expand_demands()

    # place with reoptimize
    total_placed = tm.place_all_demands(
        placement_rounds=2,
        reoptimize_after_each_round=True,
    )
    # We do not strictly assert a certain path is used,
    # only that a nonzero amount is placed (some path is feasible).
    assert total_placed > 0.0, "Should place some flow even if B->C is small"

    # Summarize flows
    flow_details = tm.get_flow_details()
    # We only had 1 demand => index=0
    # We should have at least 1 flow (or more if it tries multiple splits)
    assert len(flow_details) >= 1
    # No crash means re-optimization was invoked

    # The final usage on B->C might be at most 1.0 if it uses direct path,
    # or it might use partial flows if there's a different path approach.
    # We'll just assert we placed something, and capacity usage isn't insane.
    usage = tm.summarize_link_usage()
    for k in usage:
        assert usage[k] <= 10.0, "No link usage should exceed capacity"
