"""Tests for the FailureManager class."""

import pytest
from unittest.mock import MagicMock
from typing import List

from ngraph.network import Network
from ngraph.traffic_demand import TrafficDemand
from ngraph.traffic_manager import TrafficManager, TrafficResult
from ngraph.failure_policy import FailurePolicy
from ngraph.failure_manager import FailureManager


@pytest.fixture
def mock_network() -> Network:
    """Fixture returning a mock Network with a node1 and link1."""
    mock_net = MagicMock(spec=Network)
    # Populate these so that 'node1' and 'link1' are found in membership tests.
    mock_net.nodes = {"node1": MagicMock()}
    mock_net.links = {"link1": MagicMock()}
    return mock_net


@pytest.fixture
def mock_demands() -> List[TrafficDemand]:
    """Fixture returning a list of mock TrafficDemands."""
    return [MagicMock(spec=TrafficDemand), MagicMock(spec=TrafficDemand)]


@pytest.fixture
def mock_failure_policy() -> FailurePolicy:
    """Fixture returning a mock FailurePolicy."""
    policy = MagicMock(spec=FailurePolicy)
    # By default, pretend both "node1" and "link1" fail.
    policy.apply_failures.return_value = ["node1", "link1"]
    return policy


@pytest.fixture
def mock_traffic_manager_results() -> List[TrafficResult]:
    """Fixture returning mock traffic results."""
    result1 = MagicMock(spec=TrafficResult)
    result1.src = "A"
    result1.dst = "B"
    result1.priority = 1
    result1.placed_volume = 50.0
    result1.total_volume = 100.0
    result1.unplaced_volume = 50.0

    result2 = MagicMock(spec=TrafficResult)
    result2.src = "C"
    result2.dst = "D"
    result2.priority = 2
    result2.placed_volume = 30.0
    result2.total_volume = 30.0
    result2.unplaced_volume = 0.0

    return [result1, result2]


@pytest.fixture
def mock_traffic_manager_class(mock_traffic_manager_results):
    """Mock TrafficManager class."""

    class MockTrafficManager(MagicMock):
        def build_graph(self):
            pass

        def expand_demands(self):
            pass

        def place_all_demands(self):
            pass

        def get_traffic_results(self, detailed: bool = True):
            return mock_traffic_manager_results

    return MockTrafficManager


@pytest.fixture
def failure_manager(
    mock_network,
    mock_demands,
    mock_failure_policy,
):
    """Factory fixture to create a FailureManager with default mocks."""
    return FailureManager(
        network=mock_network,
        traffic_demands=mock_demands,
        failure_policy=mock_failure_policy,
        default_flow_policy_config=None,
    )


def test_apply_failures_no_policy(mock_network, mock_demands):
    """Test apply_failures does nothing if there is no failure_policy."""
    fmgr = FailureManager(
        network=mock_network, traffic_demands=mock_demands, failure_policy=None
    )
    fmgr.apply_failures()

    mock_network.disable_node.assert_not_called()
    mock_network.disable_link.assert_not_called()


def test_apply_failures_with_policy(failure_manager, mock_network):
    """
    Test apply_failures applies the policy's returned list of failed IDs
    to disable_node/disable_link on the network.
    """
    failure_manager.apply_failures()

    # We expect that one node and one link are disabled
    mock_network.disable_node.assert_called_once_with("node1")
    mock_network.disable_link.assert_called_once_with("link1")


def test_run_single_failure_scenario(
    failure_manager, mock_network, mock_traffic_manager_class, monkeypatch
):
    """
    Test run_single_failure_scenario applies failures, builds TrafficManager,
    and returns traffic results.
    """
    # Patch TrafficManager constructor in the 'ngraph.failure_manager' namespace
    monkeypatch.setattr(
        "ngraph.failure_manager.TrafficManager", mock_traffic_manager_class
    )

    results = failure_manager.run_single_failure_scenario()
    assert len(results) == 2  # We expect two mock results

    # Verify network was re-enabled before applying failures
    mock_network.enable_all.assert_called_once()
    # Verify that apply_failures was indeed called
    mock_network.disable_node.assert_called_once_with("node1")
    mock_network.disable_link.assert_called_once_with("link1")


def test_run_monte_carlo_failures_zero_iterations(failure_manager):
    """
    Test run_monte_carlo_failures(0) returns zeroed stats.
    """
    stats = failure_manager.run_monte_carlo_failures(iterations=0, parallelism=1)

    # Overall stats should be zeroed out
    assert stats["overall_stats"]["mean"] == 0.0
    assert stats["overall_stats"]["stdev"] == 0.0
    assert stats["overall_stats"]["min"] == 0.0
    assert stats["overall_stats"]["max"] == 0.0
    assert stats["by_src_dst"] == {}


def test_run_monte_carlo_failures_single_thread(
    failure_manager, mock_network, mock_traffic_manager_class, monkeypatch
):
    """Test run_monte_carlo_failures with single-thread (parallelism=1)."""
    monkeypatch.setattr(
        "ngraph.failure_manager.TrafficManager", mock_traffic_manager_class
    )
    stats = failure_manager.run_monte_carlo_failures(iterations=2, parallelism=1)

    # Validate structure of returned dictionary
    assert "overall_stats" in stats
    assert "by_src_dst" in stats
    assert len(stats["by_src_dst"]) > 0

    overall_stats = stats["overall_stats"]
    assert overall_stats["min"] <= overall_stats["mean"] <= overall_stats["max"]

    # We expect at least one entry for each iteration for (A,B,1) and (C,D,2)
    key1 = ("A", "B", 1)
    key2 = ("C", "D", 2)
    assert key1 in stats["by_src_dst"]
    assert key2 in stats["by_src_dst"]
    assert len(stats["by_src_dst"][key1]) == 2
    assert len(stats["by_src_dst"][key2]) == 2


def test_run_monte_carlo_failures_multi_thread(
    failure_manager, mock_network, mock_traffic_manager_class, monkeypatch
):
    """Test run_monte_carlo_failures with parallelism > 1."""
    monkeypatch.setattr(
        "ngraph.failure_manager.TrafficManager", mock_traffic_manager_class
    )
    stats = failure_manager.run_monte_carlo_failures(iterations=2, parallelism=2)

    # Verify the structure is still as expected
    assert "overall_stats" in stats
    assert "by_src_dst" in stats

    overall_stats = stats["overall_stats"]
    assert overall_stats["mean"] > 0
    assert overall_stats["max"] >= overall_stats["min"]
