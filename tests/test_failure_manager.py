"""Tests for the FailureManager class."""

from typing import List
from unittest.mock import MagicMock

import pytest

from ngraph.failure_manager import FailureManager
from ngraph.failure_policy import FailurePolicy
from ngraph.network import Network
from ngraph.traffic_demand import TrafficDemand
from ngraph.traffic_manager import TrafficResult


@pytest.fixture
def mock_network() -> Network:
    """Fixture returning a mock Network with a node1 and link1."""
    mock_net = MagicMock(spec=Network)
    # Populate these so that 'node1' and 'link1' are found in membership tests.
    mock_net.nodes = {"node1": MagicMock()}
    mock_net.links = {"link1": MagicMock()}
    mock_net.risk_groups = {}  # Add risk_groups attribute
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
    from ngraph.results_artifacts import FailurePolicySet, TrafficMatrixSet

    matrix_set = TrafficMatrixSet()
    matrix_set.add("default", mock_demands)

    policy_set = FailurePolicySet()
    policy_set.add("default", mock_failure_policy)

    return FailureManager(
        network=mock_network,
        traffic_matrix_set=matrix_set,
        matrix_name=None,
        failure_policy_set=policy_set,
        policy_name="default",
        default_flow_policy_config=None,
    )


def test_get_failed_entities_no_policy(mock_network, mock_demands):
    """Test get_failed_entities returns empty lists if there is no failure_policy."""
    from ngraph.results_artifacts import FailurePolicySet, TrafficMatrixSet

    matrix_set = TrafficMatrixSet()
    matrix_set.add("default", mock_demands)

    # Create empty policy set
    policy_set = FailurePolicySet()

    fmgr = FailureManager(
        network=mock_network,
        traffic_matrix_set=matrix_set,
        matrix_name=None,
        failure_policy_set=policy_set,
        policy_name=None,
    )
    failed_nodes, failed_links = fmgr.get_failed_entities()

    assert failed_nodes == []
    assert failed_links == []


def test_get_failed_entities_with_policy(failure_manager, mock_network):
    """
    Test get_failed_entities returns the correct lists of failed nodes and links.
    """
    failed_nodes, failed_links = failure_manager.get_failed_entities()

    # We expect one node and one link based on the mock policy
    assert "node1" in failed_nodes
    assert "link1" in failed_links


def test_run_single_failure_scenario(
    failure_manager, mock_network, mock_traffic_manager_class, monkeypatch
):
    """
    Test run_single_failure_scenario uses NetworkView and returns traffic results.
    """
    # Patch TrafficManager constructor in the 'ngraph.failure_manager' namespace
    monkeypatch.setattr(
        "ngraph.failure_manager.TrafficManager", mock_traffic_manager_class
    )

    results = failure_manager.run_single_failure_scenario()
    assert len(results) == 2  # We expect two mock results

    # Verify network was NOT modified (NetworkView is used instead)
    mock_network.enable_all.assert_not_called()
    mock_network.disable_node.assert_not_called()
    mock_network.disable_link.assert_not_called()


def test_run_monte_carlo_failures_zero_iterations(failure_manager):
    """
    Test run_monte_carlo_failures(0) returns an empty list of results.
    """
    results = failure_manager.run_monte_carlo_failures(iterations=0, parallelism=1)

    # Should return a dictionary with an empty list of raw results
    assert results == {"raw_results": []}


def test_run_monte_carlo_failures_single_thread(
    failure_manager, mock_network, mock_traffic_manager_class, monkeypatch
):
    """Test run_monte_carlo_failures with single-thread (parallelism=1)."""
    monkeypatch.setattr(
        "ngraph.failure_manager.TrafficManager", mock_traffic_manager_class
    )
    results = failure_manager.run_monte_carlo_failures(iterations=2, parallelism=1)

    # Validate structure of returned dictionary
    assert "raw_results" in results
    assert isinstance(results["raw_results"], list)
    assert len(results["raw_results"]) == 2
    assert isinstance(
        results["raw_results"][0], list
    )  # Each item is a list of TrafficResult


def test_run_monte_carlo_failures_multi_thread(
    failure_manager, mock_network, mock_traffic_manager_class, monkeypatch
):
    """Test run_monte_carlo_failures with parallelism > 1."""
    monkeypatch.setattr(
        "ngraph.failure_manager.TrafficManager", mock_traffic_manager_class
    )
    results = failure_manager.run_monte_carlo_failures(iterations=2, parallelism=2)

    # Verify the structure is still as expected
    assert "raw_results" in results
    assert isinstance(results["raw_results"], list)
    assert len(results["raw_results"]) == 2
    assert isinstance(results["raw_results"][0], list)
