import pytest
import networkx as nx
from unittest.mock import MagicMock

from ngraph.workflow.build_graph import BuildGraph


class MockNode:
    """
    A simple mock Node to simulate scenario.network.nodes[node_name].
    """

    def __init__(self, attrs=None):
        self.attrs = attrs or {}


class MockLink:
    """
    A simple mock Link to simulate scenario.network.links[link_id].
    """

    def __init__(self, link_id, source, target, capacity, cost, attrs=None):
        self.id = link_id
        self.source = source
        self.target = target
        self.capacity = capacity
        self.cost = cost
        self.attrs = attrs or {}


@pytest.fixture
def mock_scenario():
    """
    Provides a mock Scenario object for testing.
    """
    scenario = MagicMock()
    scenario.network = MagicMock()

    # Sample data:
    scenario.network.nodes = {
        "A": MockNode(attrs={"type": "router", "location": "rack1"}),
        "B": MockNode(attrs={"type": "router", "location": "rack2"}),
    }
    scenario.network.links = {
        "L1": MockLink(
            link_id="L1",
            source="A",
            target="B",
            capacity=100,
            cost=5,
            attrs={"fiber": True},
        ),
        "L2": MockLink(
            link_id="L2",
            source="B",
            target="A",
            capacity=50,
            cost=2,
            attrs={"copper": True},
        ),
    }

    # Mock results object with a MagicMocked put method
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()
    return scenario


def test_build_graph_stores_multidigraph_in_results(mock_scenario):
    """
    Ensure BuildGraph creates a MultiDiGraph, adds all nodes/edges,
    and stores it in scenario.results with the key (step_name, "graph").
    """
    step = BuildGraph(name="MyBuildStep")

    step.run(mock_scenario)

    # Check scenario.results.put was called exactly once
    mock_scenario.results.put.assert_called_once()

    # Extract the arguments from the .put call
    call_args = mock_scenario.results.put.call_args
    # Should look like ("MyBuildStep", "graph", <MultiDiGraph>)
    assert call_args[0][0] == "MyBuildStep"
    assert call_args[0][1] == "graph"
    created_graph = call_args[0][2]
    assert isinstance(
        created_graph, nx.MultiDiGraph
    ), "Resulting object must be a MultiDiGraph."

    # Verify the correct nodes were added
    assert set(created_graph.nodes()) == {
        "A",
        "B",
    }, "MultiDiGraph should contain the correct node set."
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
    edge_data = created_graph.get_edge_data("A", "B", key="L1")
    assert edge_data is not None, "Forward edge 'L1' should exist from A to B."
    assert edge_data["capacity"] == 100
    assert edge_data["cost"] == 5
    assert "fiber" in edge_data

    # Check reverse edge from link 'L1'
    rev_edge_data = created_graph.get_edge_data("B", "A", key="L1_rev")
    assert rev_edge_data is not None, "Reverse edge 'L1_rev' should exist from B to A."
    assert (
        rev_edge_data["capacity"] == 100
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
