from unittest.mock import MagicMock

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.results.store import Results
from ngraph.workflow.network_stats import NetworkStats


@pytest.fixture
def mock_scenario():
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = Results()

    scenario.network.add_node(Node("A"))
    scenario.network.add_node(Node("B"))
    scenario.network.add_node(Node("C"))

    scenario.network.add_link(Link("A", "B", capacity=10, cost=1.0))
    scenario.network.add_link(Link("A", "C", capacity=5, cost=2.0))
    scenario.network.add_link(Link("C", "A", capacity=7, cost=1.5))
    return scenario


@pytest.fixture
def mock_scenario_with_disabled():
    """Scenario with disabled nodes and links for testing include_disabled parameter."""
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = Results()

    # Add nodes - some enabled, some disabled
    scenario.network.add_node(Node("A"))  # enabled
    scenario.network.add_node(Node("B"))  # enabled
    scenario.network.add_node(Node("C", disabled=True))  # disabled
    scenario.network.add_node(Node("D"))  # enabled

    # Add links - some enabled, some disabled
    scenario.network.add_link(Link("A", "B", capacity=10, cost=1.0))  # enabled
    scenario.network.add_link(
        Link("A", "C", capacity=5, cost=2.0)
    )  # enabled (to disabled node)
    scenario.network.add_link(
        Link("C", "A", capacity=7, cost=1.5)
    )  # enabled (from disabled node)
    scenario.network.add_link(
        Link("B", "D", capacity=15, cost=3.0, disabled=True)
    )  # disabled
    scenario.network.add_link(Link("D", "B", capacity=20, cost=0.5))  # enabled
    return scenario


def test_network_stats_collects_statistics(mock_scenario):
    step = NetworkStats(name="stats")

    step.execute(mock_scenario)

    data = mock_scenario.results.to_dict()["steps"]["stats"]["data"]

    # Node statistics
    assert data["node_count"] == 3

    # Link statistics
    assert data["link_count"] == 3
    assert data["total_capacity"] == 22.0  # 10 + 5 + 7
    assert data["mean_capacity"] == pytest.approx(22.0 / 3)
    assert data["min_capacity"] == 5.0
    assert data["max_capacity"] == 10.0

    # Cost statistics
    assert data["mean_cost"] == pytest.approx((1.0 + 2.0 + 1.5) / 3)
    assert data["min_cost"] == 1.0
    assert data["max_cost"] == 2.0

    # Degree statistics should be present
    assert "mean_degree" in data
    assert "min_degree" in data
    assert "max_degree" in data


def test_network_stats_excludes_disabled_by_default(mock_scenario_with_disabled):
    """Test that disabled nodes and links are excluded by default."""
    step = NetworkStats(name="stats")

    step.execute(mock_scenario_with_disabled)

    data = mock_scenario_with_disabled.results.to_dict()["steps"]["stats"]["data"]

    # Should exclude disabled node C and disabled link B->D
    assert data["node_count"] == 3  # A, B, D (excluding C)
    assert (
        data["link_count"] == 2
    )  # A->B and D->B are enabled and between enabled nodes

    # Link statistics (A->B with capacity 10, D->B with capacity 20)
    assert data["total_capacity"] == 30.0  # 10 + 20
    assert data["mean_capacity"] == 15.0  # (10 + 20) / 2
    assert data["min_capacity"] == 10.0
    assert data["max_capacity"] == 20.0

    # Cost statistics (A->B with cost 1.0, D->B with cost 0.5)
    assert data["mean_cost"] == 0.75  # (1.0 + 0.5) / 2
    assert data["min_cost"] == 0.5
    assert data["max_cost"] == 1.0


def test_network_stats_includes_disabled_when_enabled(mock_scenario_with_disabled):
    """Test that disabled nodes and links are included when include_disabled=True."""
    step = NetworkStats(name="stats", include_disabled=True)

    step.execute(mock_scenario_with_disabled)

    data = mock_scenario_with_disabled.results.to_dict()["steps"]["stats"]["data"]

    # Should include all nodes and links
    assert data["node_count"] == 4  # A, B, C, D
    assert data["link_count"] == 5  # All 5 links

    # Link statistics (all links: 10, 5, 7, 15, 20)
    assert data["total_capacity"] == 57.0  # 10 + 5 + 7 + 15 + 20
    assert data["mean_capacity"] == pytest.approx(57.0 / 5)
    assert data["min_capacity"] == 5.0
    assert data["max_capacity"] == 20.0

    # Cost statistics (costs: 1.0, 2.0, 1.5, 3.0, 0.5)
    assert data["mean_cost"] == pytest.approx((1.0 + 2.0 + 1.5 + 3.0 + 0.5) / 5)
    assert data["min_cost"] == 0.5
    assert data["max_cost"] == 3.0


def test_network_stats_with_exclusions(mock_scenario):
    """Test NetworkStats with excluded nodes and links."""
    step = NetworkStats(name="stats", excluded_nodes=["A"], excluded_links=[])

    step.execute(mock_scenario)

    data = mock_scenario.results.to_dict()["steps"]["stats"]["data"]

    # Should exclude node A and its links
    assert data["node_count"] == 2  # B, C (excluding A)
    assert data["link_count"] == 0  # All links connect to A, so none remain


# (Removed backward-compatibility param duplication; covered by explicit
# include_disabled default behavior in other tests.)
