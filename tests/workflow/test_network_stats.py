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

    scenario.network.add_link(Link("A", "B", capacity=10))
    scenario.network.add_link(Link("A", "C", capacity=5))
    scenario.network.add_link(Link("C", "A", capacity=7))
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
    scenario.network.add_link(Link("A", "B", capacity=10))  # enabled
    scenario.network.add_link(Link("A", "C", capacity=5))  # enabled (to disabled node)
    scenario.network.add_link(
        Link("C", "A", capacity=7)
    )  # enabled (from disabled node)
    scenario.network.add_link(Link("B", "D", capacity=15, disabled=True))  # disabled
    scenario.network.add_link(Link("D", "B", capacity=20))  # enabled
    return scenario


def test_network_stats_collects_statistics(mock_scenario):
    step = NetworkStats(name="stats")

    step.run(mock_scenario)

    assert mock_scenario.results.put.call_count == 4

    keys = {call.args[1] for call in mock_scenario.results.put.call_args_list}
    assert keys == {"link_capacity", "node_capacity", "node_degree", "per_node"}

    link_data = next(
        call.args[2]
        for call in mock_scenario.results.put.call_args_list
        if call.args[1] == "link_capacity"
    )
    assert link_data["values"] == [5, 7, 10]
    assert link_data["min"] == 5
    assert link_data["max"] == 10
    assert link_data["median"] == 7
    assert link_data["mean"] == pytest.approx((5 + 7 + 10) / 3)

    per_node = next(
        call.args[2]
        for call in mock_scenario.results.put.call_args_list
        if call.args[1] == "per_node"
    )
    assert set(per_node.keys()) == {"A", "B", "C"}


def test_network_stats_excludes_disabled_by_default(mock_scenario_with_disabled):
    """Test that disabled nodes and links are excluded by default."""
    step = NetworkStats(name="stats")

    step.run(mock_scenario_with_disabled)

    # Get the collected data
    calls = {
        call.args[1]: call.args[2]
        for call in mock_scenario_with_disabled.results.put.call_args_list
    }

    # Link capacity should exclude disabled link (capacity=15)
    link_data = calls["link_capacity"]
    # Should include capacities: 10, 5, 7, 20 (excluding disabled link with capacity=15)
    assert sorted(link_data["values"]) == [5, 7, 10, 20]
    assert link_data["min"] == 5
    assert link_data["max"] == 20
    assert link_data["mean"] == pytest.approx((5 + 7 + 10 + 20) / 4)

    # Per-node stats should exclude disabled node C
    per_node = calls["per_node"]
    # Should only include enabled nodes: A, B, D (excluding disabled node C)
    assert set(per_node.keys()) == {"A", "B", "D"}

    # Node A should have degree 2 (links to B and C, both enabled)
    assert per_node["A"]["degree"] == 2
    assert per_node["A"]["capacity_sum"] == 15  # 10 + 5

    # Node B should have degree 0 (link to D is disabled)
    assert per_node["B"]["degree"] == 0
    assert per_node["B"]["capacity_sum"] == 0

    # Node D should have degree 1 (link to B is enabled)
    assert per_node["D"]["degree"] == 1
    assert per_node["D"]["capacity_sum"] == 20


def test_network_stats_includes_disabled_when_enabled(mock_scenario_with_disabled):
    """Test that disabled nodes and links are included when include_disabled=True."""
    step = NetworkStats(name="stats", include_disabled=True)

    step.run(mock_scenario_with_disabled)

    # Get the collected data
    calls = {
        call.args[1]: call.args[2]
        for call in mock_scenario_with_disabled.results.put.call_args_list
    }

    # Link capacity should include all links including disabled one
    link_data = calls["link_capacity"]
    # Should include all capacities: 10, 5, 7, 15, 20
    assert sorted(link_data["values"]) == [5, 7, 10, 15, 20]
    assert link_data["min"] == 5
    assert link_data["max"] == 20
    assert link_data["mean"] == pytest.approx((5 + 7 + 10 + 15 + 20) / 5)

    # Per-node stats should include disabled node C
    per_node = calls["per_node"]
    # Should include all nodes: A, B, C, D
    assert set(per_node.keys()) == {"A", "B", "C", "D"}

    # Node A should have degree 2 (links to B and C)
    assert per_node["A"]["degree"] == 2
    assert per_node["A"]["capacity_sum"] == 15  # 10 + 5

    # Node B should have degree 1 (link to D, now included)
    assert per_node["B"]["degree"] == 1
    assert per_node["B"]["capacity_sum"] == 15  # disabled link now included

    # Node C should have degree 1 (link to A)
    assert per_node["C"]["degree"] == 1
    assert per_node["C"]["capacity_sum"] == 7

    # Node D should have degree 1 (link to B)
    assert per_node["D"]["degree"] == 1
    assert per_node["D"]["capacity_sum"] == 20


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
