import pytest
from unittest.mock import MagicMock

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.workflow.build_graph import BuildGraph
from ngraph.network import Network, Node, Link


@pytest.fixture
def mock_scenario():
    """
    Provides a mock Scenario object for testing, including:
      - A Network object with two nodes (A, B).
      - Two links (L1, L2), each of which is auto-created via Link
        but we override their IDs to maintain the naming expected by the tests.
      - A MagicMock-based results object for verifying output.
    """
    scenario = MagicMock()
    scenario.network = Network()

    # Create real Node objects and add them to the network
    node_a = Node(name="A", attrs={"type": "router", "location": "rack1"})
    node_b = Node(name="B", attrs={"type": "router", "location": "rack2"})
    scenario.network.add_node(node_a)
    scenario.network.add_node(node_b)

    # Create real Link objects, then override their ID to match the original test expectations.
    link1 = Link(source="A", target="B", capacity=100, cost=5, attrs={"fiber": True})
    link1.id = "L1"  # Force the ID so the test can look up "L1"
    scenario.network.links[link1.id] = link1  # Insert directly

    link2 = Link(source="B", target="A", capacity=50, cost=2, attrs={"copper": True})
    link2.id = "L2"
    scenario.network.links[link2.id] = link2

    # Mock results object
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()
    return scenario


def test_build_graph_stores_multidigraph_in_results(mock_scenario):
    """
    Ensure BuildGraph creates a StrictMultiDiGraph, adds all nodes/edges,
    and stores it in scenario.results with the key (step_name, "graph").
    """
    step = BuildGraph(name="MyBuildStep")

    step.run(mock_scenario)

    # Check scenario.results.put was called exactly once
    mock_scenario.results.put.assert_called_once()

    # Extract the arguments from the .put call
    call_args = mock_scenario.results.put.call_args
    # Should look like ("MyBuildStep", "graph", <StrictMultiDiGraph>)
    assert call_args[0][0] == "MyBuildStep"
    assert call_args[0][1] == "graph"
    created_graph = call_args[0][2]
    assert isinstance(
        created_graph, StrictMultiDiGraph
    ), "Resulting object must be a StrictMultiDiGraph."

    # Verify the correct nodes were added
    assert set(created_graph.nodes()) == {
        "A",
        "B",
    }, "StrictMultiDiGraph should contain the correct node set."
    # Check node attributes
    assert created_graph.nodes["A"]["type"] == "router"
    assert created_graph.nodes["B"]["location"] == "rack2"

    # Verify edges
    # We expect two edges for each link: forward ("L1") and reverse ("L1_rev"), etc.
    # So we should have 4 edges in total (2 from L1, 2 from L2).
    assert (
        created_graph.number_of_edges() == 4
    ), "Should have two edges (forward/reverse) for each link."

    # Check forward edge from link 'L1'
    edge_data_l1 = created_graph.get_edge_data("A", "B", key="L1")
    assert edge_data_l1 is not None, "Forward edge 'L1' should exist from A to B."
    assert edge_data_l1["capacity"] == 100
    assert edge_data_l1["cost"] == 5
    assert "fiber" in edge_data_l1

    # Check reverse edge from link 'L1'
    rev_edge_data_l1 = created_graph.get_edge_data("B", "A", key="L1_rev")
    assert (
        rev_edge_data_l1 is not None
    ), "Reverse edge 'L1_rev' should exist from B to A."
    assert (
        rev_edge_data_l1["capacity"] == 100
    ), "Reverse edge should share the same capacity."

    # Check forward edge from link 'L2'
    edge_data_l2 = created_graph.get_edge_data("B", "A", key="L2")
    assert edge_data_l2 is not None, "Forward edge 'L2' should exist from B to A."
    assert edge_data_l2["capacity"] == 50
    assert edge_data_l2["cost"] == 2
    assert "copper" in edge_data_l2

    # Check reverse edge from link 'L2'
    rev_edge_data_l2 = created_graph.get_edge_data("A", "B", key="L2_rev")
    assert (
        rev_edge_data_l2 is not None
    ), "Reverse edge 'L2_rev' should exist from A to B."
    assert (
        rev_edge_data_l2["capacity"] == 50
    ), "Reverse edge should share the same capacity."
