from unittest.mock import MagicMock

import pytest

from ngraph.network import Link, Network, Node
from ngraph.workflow.network_stats import NetworkStats


@pytest.fixture
def mock_scenario():
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()

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
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()

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

    step.run(mock_scenario)

    # Should collect node_count, link_count, capacity stats, cost stats, and degree stats
    assert mock_scenario.results.put.call_count >= 10  # At least 10 different metrics

    # Check that key statistics are collected
    calls = {
        call.args[1]: call.args[2] for call in mock_scenario.results.put.call_args_list
    }

    # Node statistics
    assert calls["node_count"] == 3

    # Link statistics
    assert calls["link_count"] == 3
    assert calls["total_capacity"] == 22.0  # 10 + 5 + 7
    assert calls["mean_capacity"] == pytest.approx(22.0 / 3)
    assert calls["min_capacity"] == 5.0
    assert calls["max_capacity"] == 10.0

    # Cost statistics
    assert calls["mean_cost"] == pytest.approx((1.0 + 2.0 + 1.5) / 3)
    assert calls["min_cost"] == 1.0
    assert calls["max_cost"] == 2.0

    # Degree statistics should be present
    assert "mean_degree" in calls
    assert "min_degree" in calls
    assert "max_degree" in calls


def test_network_stats_excludes_disabled_by_default(mock_scenario_with_disabled):
    """Test that disabled nodes and links are excluded by default."""
    step = NetworkStats(name="stats")

    step.run(mock_scenario_with_disabled)

    # Get the collected data
    calls = {
        call.args[1]: call.args[2]
        for call in mock_scenario_with_disabled.results.put.call_args_list
    }

    # Should exclude disabled node C and disabled link B->D
    assert calls["node_count"] == 3  # A, B, D (excluding C)
    assert (
        calls["link_count"] == 2
    )  # A->B and D->B are enabled and between enabled nodes

    # Link statistics (A->B with capacity 10, D->B with capacity 20)
    assert calls["total_capacity"] == 30.0  # 10 + 20
    assert calls["mean_capacity"] == 15.0  # (10 + 20) / 2
    assert calls["min_capacity"] == 10.0
    assert calls["max_capacity"] == 20.0

    # Cost statistics (A->B with cost 1.0, D->B with cost 0.5)
    assert calls["mean_cost"] == 0.75  # (1.0 + 0.5) / 2
    assert calls["min_cost"] == 0.5
    assert calls["max_cost"] == 1.0


def test_network_stats_includes_disabled_when_enabled(mock_scenario_with_disabled):
    """Test that disabled nodes and links are included when include_disabled=True."""
    step = NetworkStats(name="stats", include_disabled=True)

    step.run(mock_scenario_with_disabled)

    # Get the collected data
    calls = {
        call.args[1]: call.args[2]
        for call in mock_scenario_with_disabled.results.put.call_args_list
    }

    # Should include all nodes and links
    assert calls["node_count"] == 4  # A, B, C, D
    assert calls["link_count"] == 5  # All 5 links

    # Link statistics (all links: 10, 5, 7, 15, 20)
    assert calls["total_capacity"] == 57.0  # 10 + 5 + 7 + 15 + 20
    assert calls["mean_capacity"] == pytest.approx(57.0 / 5)
    assert calls["min_capacity"] == 5.0
    assert calls["max_capacity"] == 20.0

    # Cost statistics (costs: 1.0, 2.0, 1.5, 3.0, 0.5)
    assert calls["mean_cost"] == pytest.approx((1.0 + 2.0 + 1.5 + 3.0 + 0.5) / 5)
    assert calls["min_cost"] == 0.5
    assert calls["max_cost"] == 3.0


def test_network_stats_with_exclusions(mock_scenario):
    """Test NetworkStats with excluded nodes and links."""
    step = NetworkStats(name="stats", excluded_nodes=["A"], excluded_links=[])

    step.run(mock_scenario)

    calls = {
        call.args[1]: call.args[2] for call in mock_scenario.results.put.call_args_list
    }

    # Should exclude node A and its links
    assert calls["node_count"] == 2  # B, C (excluding A)
    assert calls["link_count"] == 0  # All links connect to A, so none remain


def test_network_stats_parameter_backward_compatibility(mock_scenario):
    """Test that the new parameter maintains backward compatibility."""
    # Test with explicit default
    step_explicit = NetworkStats(name="stats", include_disabled=False)
    step_explicit.run(mock_scenario)

    # Capture results from explicit test
    explicit_calls = {
        call.args[1]: call.args[2] for call in mock_scenario.results.put.call_args_list
    }

    # Reset mock for second test
    mock_scenario.results.put.reset_mock()

    # Test with implicit default
    step_implicit = NetworkStats(name="stats")
    step_implicit.run(mock_scenario)

    # Capture results from implicit test
    implicit_calls = {
        call.args[1]: call.args[2] for call in mock_scenario.results.put.call_args_list
    }

    # Results should be identical
    assert explicit_calls.keys() == implicit_calls.keys()
    for key in explicit_calls:
        assert explicit_calls[key] == implicit_calls[key]
