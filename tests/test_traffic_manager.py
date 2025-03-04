import pytest

from ngraph.network import Network, Node, Link
from ngraph.traffic_demand import TrafficDemand
from ngraph.lib.flow_policy import FlowPolicyConfig
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.base import MIN_FLOW
from ngraph.lib.demand import Demand

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
    This can help test re-optimization logic in place_all_demands.
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
    # No build_graph call here, so we expect an error
    with pytest.raises(RuntimeError):
        tm.place_all_demands()


def test_basic_build_and_expand(small_network):
    """
    Test the ability to build the graph and expand demands using the default mode.
    By default, we assume it's "combine" if not specified otherwise in TrafficDemand.
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
    assert len(tm.graph.get_nodes()) == 3, "Should have the original 3 nodes"
    # 2 directed links => with add_reverse=True => we expect 4 edges total
    assert len(tm.graph.get_edges()) == 4, "Should have 4 edges in the graph"

    tm.expand_demands()
    # Each TrafficDemand uses default "combine" => 1 Demand each
    assert len(tm.demands) == 2, "Expected 2 expanded demands"


def test_place_all_demands_simple(small_network):
    """
    Place demands on a simple A->B->C network.
    We expect all to be placed because capacity = 100 is large enough.
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
        ), "Demand should be fully placed"

    # Summarize link usage
    usage = tm.summarize_link_usage()
    # We expect 50 flow on A->B, then 70 total on B->C
    ab_key = None
    bc_key = None
    for k, (src, dst, _, _) in tm.graph.get_edges().items():
        if src == "A" and dst == "B":
            ab_key = k
        elif src == "B" and dst == "C":
            bc_key = k

    assert abs(usage[ab_key] - 50.0) < MIN_FLOW, "A->B should carry 50"
    assert abs(usage[bc_key] - 70.0) < MIN_FLOW, "B->C should carry 70"


def test_priority_fairness(small_network):
    """
    Test that multiple demands with different priorities
    are handled in ascending priority order (priority=0 means highest).
    This test uses smaller link capacities to force partial placement.
    """
    # Adjust capacities to 30
    link_ids = list(small_network.links.keys())
    small_network.links[link_ids[0]].capacity = 30.0  # A->B
    small_network.links[link_ids[1]].capacity = 30.0  # B->C

    # Higher priority (0) vs lower priority (1)
    demands = [
        TrafficDemand(source_path="A", sink_path="C", demand=40.0, priority=0),
        TrafficDemand(source_path="B", sink_path="C", demand=40.0, priority=1),
    ]
    tm = TrafficManager(network=small_network, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()

    total_placed = tm.place_all_demands(placement_rounds=1)
    assert total_placed == 30.0, "Expected only 30 placed in total"

    high_prio_placed = tm.demands[0].placed_demand
    low_prio_placed = tm.demands[1].placed_demand
    assert high_prio_placed == 30.0, "High priority saturates capacity"
    assert low_prio_placed == 0.0, "No capacity left for lower priority"


def test_reset_flow_usages(small_network):
    """
    Test that reset_all_flow_usages() zeroes out placed flow usage on edges
    and sets all demands' placed_demand to 0.
    """
    demands = [TrafficDemand(source_path="A", sink_path="C", demand=10.0)]
    tm = TrafficManager(network=small_network, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()
    placed_before = tm.place_all_demands()
    assert placed_before == 10.0

    # Now reset
    tm.reset_all_flow_usages()
    for d in tm.demands:
        assert d.placed_demand == 0.0, "Demand placed_demand should be reset"
    usage = tm.summarize_link_usage()
    for flow_val in usage.values():
        assert flow_val == 0.0, "All link usage should be reset to 0"


def test_reoptimize_flows(small_network_with_loop):
    """
    Test that re-optimization logic is triggered in place_all_demands
    when reoptimize_after_each_round=True. This forces flows to be
    removed and re-placed each round.
    """
    demands = [TrafficDemand(source_path="A", sink_path="C", demand=5.0)]
    tm = TrafficManager(
        network=small_network_with_loop,
        traffic_demands=demands,
        default_flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )
    tm.build_graph()
    tm.expand_demands()

    # Place with reoptimize
    total_placed = tm.place_all_demands(
        placement_rounds=2, reoptimize_after_each_round=True
    )
    assert total_placed > 0.0, "We should place some flow"

    # Summarize flows
    flow_details = tm.get_flow_details()
    # We only had 1 demand => index=0
    assert len(flow_details) >= 1, "Expect at least one flow object"

    # Ensure no link usage exceeds capacity
    usage = tm.summarize_link_usage()
    for val in usage.values():
        assert val <= 10.0, "No link usage should exceed capacity of 10.0"


def test_unknown_mode_raises_value_error(small_network):
    """
    Ensure that an invalid mode raises a ValueError during expand_demands.
    """
    demands = [
        TrafficDemand(source_path="A", sink_path="B", demand=10.0, mode="invalid_mode")
    ]
    tm = TrafficManager(network=small_network, traffic_demands=demands)
    tm.build_graph()
    with pytest.raises(ValueError, match="Unknown mode: invalid_mode"):
        tm.expand_demands()


def test_place_all_demands_auto_rounds(small_network):
    """
    Test the 'auto' logic for placement rounds. Even though the network has
    high capacity, we verify it doesn't crash and places demands correctly.
    """
    demands = [TrafficDemand(source_path="A", sink_path="C", demand=25.0)]
    tm = TrafficManager(network=small_network, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()

    total_placed = tm.place_all_demands(placement_rounds="auto")
    assert total_placed == 25.0, "Should place all traffic under auto rounds"
    for d in tm.demands:
        assert (
            abs(d.placed_demand - d.volume) < MIN_FLOW
        ), "Demand should be fully placed"


def test_combine_mode_multi_source_sink():
    """
    Test 'combine' mode with multiple source/sink matches to ensure a single
    pseudo-source and pseudo-sink are created, and that infinite-capacity edges
    are added properly.
    """
    net = Network()
    net.add_node(Node(name="S1"))
    net.add_node(Node(name="S2"))
    net.add_node(Node(name="T1"))
    net.add_node(Node(name="T2"))

    # Just one link to confirm it's recognized, capacity is large
    net.add_link(Link(source="S1", target="T1", capacity=1000, cost=1.0))

    # Suppose the 'source_path' matches both S1 and S2, and 'sink_path' matches T1 and T2
    demands = [
        TrafficDemand(source_path="S", sink_path="T", demand=100.0, mode="combine")
    ]
    tm = TrafficManager(network=net, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()

    assert len(tm.demands) == 1, "Only one Demand in combine mode"
    d = tm.demands[0]
    assert d.src_node.startswith("combine_src::"), "Pseudo-source name mismatch"
    assert d.dst_node.startswith("combine_snk::"), "Pseudo-sink name mismatch"
    # Check that the graph has the pseudo-nodes
    pseudo_src_exists = f"combine_src::{demands[0].id}" in tm.graph.get_nodes()
    pseudo_snk_exists = f"combine_snk::{demands[0].id}" in tm.graph.get_nodes()
    assert pseudo_src_exists, "Pseudo-source node should exist in the graph"
    assert pseudo_snk_exists, "Pseudo-sink node should exist in the graph"

    # There should be edges from the pseudo-source to S1, S2, and from T1, T2 to the pseudo-sink
    edges_out_of_pseudo_src = [
        (src, dst)
        for _, (src, dst, _, data) in tm.graph.get_edges().items()
        if src == d.src_node
    ]
    assert (
        len(edges_out_of_pseudo_src) == 2
    ), "2 edges from pseudo-source to real sources"

    edges_into_pseudo_snk = [
        (src, dst)
        for _, (src, dst, _, data) in tm.graph.get_edges().items()
        if dst == d.dst_node
    ]
    assert len(edges_into_pseudo_snk) == 2, "2 edges from real sinks to pseudo-sink"


def test_full_mesh_mode_multi_source_sink():
    """
    Test 'full_mesh' mode with multiple sources and sinks. Each (src, dst) pair
    should get its own Demand, skipping any self-pairs. The total volume is split
    evenly among pairs.
    """
    net = Network()
    net.add_node(Node(name="S1"))
    net.add_node(Node(name="S2"))
    net.add_node(Node(name="T1"))
    net.add_node(Node(name="T2"))

    # For clarity, do not add links here. We just want to confirm expansions.
    demands = [
        TrafficDemand(source_path="S", sink_path="T", demand=80.0, mode="full_mesh")
    ]
    tm = TrafficManager(network=net, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()

    # We expect pairs: (S1->T1), (S1->T2), (S2->T1), (S2->T2), so 4 demands
    # Each gets 80/4 = 20 volume
    assert len(tm.demands) == 4, "4 demands in full mesh"
    for d in tm.demands:
        assert abs(d.volume - 20.0) < MIN_FLOW, "Each demand should have 20 volume"


def test_combine_mode_no_nodes():
    """
    Test that if the source or sink match returns no valid nodes, no Demand is created.
    """
    net = Network()
    net.add_node(Node(name="X"))  # does not match "A" or "B"

    demands = [
        TrafficDemand(source_path="A", sink_path="B", demand=10.0, mode="combine"),
    ]
    tm = TrafficManager(network=net, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()
    assert len(tm.demands) == 0, "No demands created if source/sink matching fails"


def test_full_mesh_mode_no_nodes():
    """
    Test that in full_mesh mode, if source or sink match returns no valid nodes,
    no Demand is created.
    """
    net = Network()
    net.add_node(Node(name="X"))  # does not match "A" or "B"

    demands = [
        TrafficDemand(source_path="A", sink_path="B", demand=10.0, mode="full_mesh"),
    ]
    tm = TrafficManager(network=net, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()
    assert len(tm.demands) == 0, "No demands created if source/sink matching fails"


def test_full_mesh_mode_self_pairs():
    """
    Test that in full_mesh mode, demands skip self-pairs (i.e., src==dst).
    We'll create a scenario where source and sink might match the same node.
    """
    net = Network()
    net.add_node(Node(name="N1"))
    net.add_node(Node(name="N2"))

    demands = [
        # source_path="N", sink_path="N" => matches N1, N2 for both source and sink
        TrafficDemand(source_path="N", sink_path="N", demand=20.0, mode="full_mesh"),
    ]
    tm = TrafficManager(network=net, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()

    # Pairs would be (N1->N1), (N1->N2), (N2->N1), (N2->N2).
    # Self pairs (N1->N1) and (N2->N2) are skipped => 2 valid pairs
    # So we expect 2 demands, each with 10.0
    assert len(tm.demands) == 2, "Only N1->N2 and N2->N1 should be created"
    for d in tm.demands:
        assert (
            abs(d.volume - 10.0) < MIN_FLOW
        ), "Volume should be evenly split among 2 pairs"


def test_estimate_rounds_no_demands(small_network):
    """
    Test that _estimate_rounds returns a default (5) if no demands exist.
    """
    tm = TrafficManager(network=small_network, traffic_demands=[])
    tm.build_graph()
    # place_all_demands calls _estimate_rounds if placement_rounds="auto"
    # With no demands, we expect no error, just zero placed and default rounds chosen.
    total_placed = tm.place_all_demands(placement_rounds="auto")
    assert total_placed == 0.0, "No demands => no placement"


def test_estimate_rounds_no_capacities():
    """
    Test that _estimate_rounds returns a default (5) if no edges have capacity.
    """
    net = Network()
    net.add_node(Node(name="A"))
    net.add_node(Node(name="B"))
    # Link with capacity=0
    net.add_link(Link(source="A", target="B", capacity=0.0, cost=1.0))

    demands = [TrafficDemand(source_path="A", sink_path="B", demand=50.0)]
    tm = TrafficManager(network=net, traffic_demands=demands)
    tm.build_graph()
    tm.expand_demands()

    # We expect auto => fallback to default rounds => partial or no placement
    total_placed = tm.place_all_demands(placement_rounds="auto")
    # The link has 0 capacity, so no actual flow can be placed.
    assert total_placed == 0.0, "No capacity => no flow placed"
