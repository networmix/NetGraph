from unittest.mock import MagicMock

import pytest

from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.model.network import Link, Network, Node
from ngraph.results.store import Results
from ngraph.workflow.build_graph import BuildGraph


@pytest.fixture
def mock_scenario():
    """
    Provides a mock Scenario object for testing, including:
      - A Network object with two nodes (A, B).
      - Two links (L1, L2), each of which is auto-created via Link
        but we override their IDs to maintain the naming expected by the tests.
      - A real Results object for storage assertions.
    """
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = Results()

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

    return scenario


def test_build_graph_stores_multidigraph_in_results(mock_scenario):
    """
    Ensure BuildGraph creates a StrictMultiDiGraph, adds all nodes/edges,
    and stores it in scenario.results under steps[name]["data"]["graph"].
    """
    step = BuildGraph(name="MyBuildStep")

    step.execute(mock_scenario)

    exported = mock_scenario.results.to_dict()
    step_data = exported["steps"]["MyBuildStep"]["data"]
    created_graph = step_data.get("graph")

    # Allow either in-memory object or serialized dict (after to_dict conversion)
    if isinstance(created_graph, StrictMultiDiGraph):
        graph_obj = created_graph
        # Verify the correct nodes were added
        assert set(graph_obj.nodes()) == {"A", "B"}
        # Check node attributes
        assert graph_obj.nodes["A"]["type"] == "router"
        assert graph_obj.nodes["B"]["location"] == "rack2"
        # Verify edges (two edges per link: forward and reverse)
        assert graph_obj.number_of_edges() == 4
        assert graph_obj.get_edge_data("A", "B", key="L1")["capacity"] == 100
        assert graph_obj.get_edge_data("B", "A", key="L1_rev") is not None
        assert graph_obj.get_edge_data("B", "A", key="L2")["capacity"] == 50
        assert graph_obj.get_edge_data("A", "B", key="L2_rev") is not None
    else:
        # Serialized representation: expect dict with nodes/links lists
        assert isinstance(created_graph, dict)
        nodes = created_graph.get("nodes", [])
        links = created_graph.get("links", [])
        # Basic shape checks
        assert isinstance(nodes, list) and isinstance(links, list)
        # Verify nodes content
        names = {n.get("id") for n in nodes}
        assert names == {"A", "B"}
        # Verify at least forward/reverse edges exist for each link id
        keys = {lk.get("key") for lk in links}
        assert {"L1", "L1_rev", "L2", "L2_rev"}.issubset(keys)
        # Spot-check a link attributes
        l1 = next(lk for lk in links if lk.get("key") == "L1")
        assert l1.get("source") in ("A", 0)
        assert l1.get("target") in ("B", 1)
