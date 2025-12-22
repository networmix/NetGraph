"""High-value tests for `FailureManager` public behavior and APIs.

Focus on functional outcomes and API semantics. Tests core functionality,
policy management, exclusion computation, and convenience methods.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ngraph.analysis.failure_manager import FailureManager
from ngraph.model.failure.policy import (
    FailureCondition,
    FailureMode,
    FailurePolicy,
    FailureRule,
)
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node


@pytest.fixture
def simple_network() -> Network:
    """Create a simple test network."""
    network = Network()
    network.attrs["name"] = "test_network"
    network.add_node(Node("node1", attrs={"type": "server"}))
    network.add_node(Node("node2", attrs={"type": "router"}))
    network.add_node(Node("node3", attrs={"type": "router"}))
    network.add_link(Link("node1", "node2", capacity=100.0))
    network.add_link(Link("node2", "node3", capacity=200.0))
    return network


@pytest.fixture
def failure_policy() -> FailurePolicy:
    """Create a simple failure policy for testing."""
    rule = FailureRule(entity_scope="node", rule_type="choice", count=1)
    return FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])


@pytest.fixture
def failure_policy_set(failure_policy: FailurePolicy) -> FailurePolicySet:
    """Create a failure policy set for testing."""
    policy_set = FailurePolicySet()
    policy_set.policies["test_policy"] = failure_policy
    return policy_set


@pytest.fixture
def failure_manager(
    simple_network: Network, failure_policy_set: FailurePolicySet
) -> FailureManager:
    """Create a FailureManager instance for testing."""
    return FailureManager(
        network=simple_network,
        failure_policy_set=failure_policy_set,
        policy_name="test_policy",
    )


class TestFailureManagerInitialization:
    """Test FailureManager initialization and basic properties."""

    def test_initialization(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test basic initialization."""
        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name="test_policy",
        )

        assert fm.network is simple_network
        assert fm.failure_policy_set is failure_policy_set
        assert fm.policy_name == "test_policy"

    def test_initialization_without_policy_name(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test initialization with no policy name."""
        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name=None,
        )

        assert fm.network is simple_network
        assert fm.failure_policy_set is failure_policy_set
        assert fm.policy_name is None


class TestFailureManagerPolicyRetrieval:
    """Test failure policy retrieval and management."""

    def test_get_failure_policy_with_named_policy(
        self, failure_manager: FailureManager
    ) -> None:
        """Test retrieving a named policy."""
        policy = failure_manager.get_failure_policy()
        assert policy is not None
        assert isinstance(policy, FailurePolicy)

    def test_get_failure_policy_with_default_policy(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test that None policy_name returns None."""
        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name=None,
        )

        policy = fm.get_failure_policy()
        assert policy is None

    def test_get_failure_policy_not_found(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test error handling when policy not found."""
        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name="nonexistent_policy",
        )

        with pytest.raises(ValueError, match="not found in scenario"):
            fm.get_failure_policy()


class TestFailureManagerExclusionComputation:
    """Test compute_exclusions method."""

    def test_compute_exclusions_no_policy(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test exclusion computation with no policy."""
        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions()
        assert excluded_nodes == set()
        assert excluded_links == set()

    def test_compute_exclusions_with_policy(
        self, failure_manager: FailureManager
    ) -> None:
        """Test exclusion computation with a policy."""
        excluded_nodes, excluded_links = failure_manager.compute_exclusions(
            seed_offset=42
        )

        # Should have some exclusions based on the policy
        assert len(excluded_nodes) > 0 or len(excluded_links) > 0

    def test_compute_exclusions_deterministic(
        self, failure_manager: FailureManager
    ) -> None:
        """Test that exclusions are deterministic with same seed."""
        excluded1_nodes, excluded1_links = failure_manager.compute_exclusions(
            seed_offset=42
        )
        excluded2_nodes, excluded2_links = failure_manager.compute_exclusions(
            seed_offset=42
        )

        assert excluded1_nodes == excluded2_nodes
        assert excluded1_links == excluded2_links


class TestFailureManagerTopLevelMatching:
    """Test compute_exclusions merged attribute view correctness."""

    def test_node_matching_on_disabled_attribute(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test node matching on disabled attribute."""
        # Mark one node as disabled
        simple_network.nodes["node1"].disabled = True

        rule = FailureRule(
            entity_scope="node",
            conditions=[FailureCondition(attr="disabled", operator="==", value=True)],
            logic="and",
            rule_type="all",
        )
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        assert "node1" in excluded_nodes
        assert "node2" not in excluded_nodes
        assert "node3" not in excluded_nodes
        assert excluded_links == set()

    def test_link_matching_on_capacity_attribute(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test link matching on capacity attribute."""
        rule = FailureRule(
            entity_scope="link",
            conditions=[FailureCondition(attr="capacity", operator=">", value=150.0)],
            logic="and",
            rule_type="all",
        )
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        # Link with capacity 200.0 should be excluded
        assert len(excluded_links) == 1
        assert excluded_nodes == set()


class TestFailureManagerMonteCarloValidation:
    """Test validation logic for Monte Carlo parameters."""

    def test_iterations_without_policy_runs_baseline_only(
        self, simple_network: Network, failure_policy_set: FailurePolicySet
    ) -> None:
        """Test that iterations > 0 without policy runs baseline only."""
        fm = FailureManager(
            network=simple_network,
            failure_policy_set=failure_policy_set,
            policy_name=None,
        )

        # Mock analysis function
        def mock_analysis_func(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"result": "mock"}

        # Without policy, iterations are ignored and only baseline runs
        result = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func, iterations=10
        )
        # Baseline is always run
        assert "baseline" in result
        # No failure iterations without a policy
        assert len(result["results"]) == 0

    def test_baseline_always_present(self, failure_manager: FailureManager) -> None:
        """Test that baseline is always present in results."""

        # Mock analysis function
        def mock_analysis_func(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"result": "mock"}

        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func, iterations=3
        )
        # Baseline should always be present as separate field
        assert "baseline" in result
        assert result["baseline"] is not None


class TestFailureManagerConvenienceMethods:
    """Test convenience methods for specific analysis types."""

    @patch("ngraph.analysis.failure_manager.FailureManager.run_monte_carlo_analysis")
    def test_run_max_flow_monte_carlo_delegates(
        self, mock_mc_analysis: MagicMock, failure_manager: FailureManager
    ) -> None:
        """Test run_max_flow_monte_carlo delegates to run_monte_carlo_analysis."""
        mock_mc_analysis.return_value = {
            "results": [],
            "metadata": {"iterations": 2},
        }

        result = failure_manager.run_max_flow_monte_carlo(
            source="datacenter.*",
            sink="edge.*",
            mode="combine",
            iterations=2,
            parallelism=1,
        )

        assert mock_mc_analysis.called
        assert result == mock_mc_analysis.return_value

    @patch("ngraph.analysis.failure_manager.FailureManager.run_monte_carlo_analysis")
    def test_run_demand_placement_monte_carlo_delegates(
        self, mock_mc_analysis: MagicMock, failure_manager: FailureManager
    ) -> None:
        """Test run_demand_placement_monte_carlo delegates correctly."""
        mock_mc_analysis.return_value = {
            "results": [],
            "metadata": {"iterations": 1},
        }

        mock_demands = MagicMock()
        result = failure_manager.run_demand_placement_monte_carlo(
            demands_config=mock_demands, iterations=1, parallelism=1
        )

        assert mock_mc_analysis.called
        assert result == mock_mc_analysis.return_value

    def test_flow_placement_string_conversion_max_flow(
        self, failure_manager: FailureManager
    ) -> None:
        """Test string to FlowPlacement enum conversion."""
        from ngraph.types.base import FlowPlacement

        with patch.object(failure_manager, "run_monte_carlo_analysis") as mock_mc:
            mock_mc.return_value = {"results": [], "metadata": {}}

            failure_manager.run_max_flow_monte_carlo(
                source="src.*",
                sink="dst.*",
                flow_placement="EQUAL_BALANCED",
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            assert call_kwargs["flow_placement"] == FlowPlacement.EQUAL_BALANCED

    def test_invalid_flow_placement_string_raises_error(
        self, failure_manager: FailureManager
    ) -> None:
        """Test that invalid flow_placement string raises clear error."""
        with pytest.raises(ValueError) as exc_info:
            failure_manager.run_max_flow_monte_carlo(
                source="src.*",
                sink="dst.*",
                flow_placement="INVALID_OPTION",
                iterations=1,
            )

        error_msg = str(exc_info.value)
        assert "Invalid flow_placement 'INVALID_OPTION'" in error_msg
        assert "Valid values are" in error_msg

    def test_case_insensitive_flow_placement_conversion(
        self, failure_manager: FailureManager
    ) -> None:
        """Test case-insensitive flow_placement string conversion."""
        from ngraph.types.base import FlowPlacement

        with patch.object(failure_manager, "run_monte_carlo_analysis") as mock_mc:
            mock_mc.return_value = {"results": [], "metadata": {}}

            failure_manager.run_max_flow_monte_carlo(
                source="src.*",
                sink="dst.*",
                flow_placement="proportional",  # lowercase
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            assert call_kwargs["flow_placement"] == FlowPlacement.PROPORTIONAL


class TestFailureManagerErrorHandling:
    """Test error handling and edge cases."""

    @patch("ngraph.analysis.failure_manager.ThreadPoolExecutor")
    def test_parallel_execution_error_propagation(
        self, mock_pool_executor: MagicMock, failure_manager: FailureManager
    ) -> None:
        """Test that parallel execution errors propagate correctly."""
        mock_pool = MagicMock()
        mock_pool_executor.return_value.__enter__.return_value = mock_pool
        mock_pool.map.side_effect = RuntimeError("Parallel execution failed")

        # Mock analysis function
        def mock_analysis_func(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"result": "mock"}

        # Note: ThreadPoolExecutor shares the network by reference (no pickling needed)
        with patch.object(
            failure_manager,
            "compute_exclusions",
            side_effect=[({"n1"}, set()), ({"n2"}, set())],
        ):
            with pytest.raises(RuntimeError, match="Parallel execution failed"):
                failure_manager.run_monte_carlo_analysis(
                    analysis_func=mock_analysis_func, iterations=2, parallelism=2
                )


class TestSensitivityResultsProcessing:
    """Test sensitivity results processing with occurrence_count weighting."""

    def test_process_sensitivity_results_weights_by_occurrence_count(
        self, failure_manager: FailureManager
    ) -> None:
        """Verify weighted statistics calculation uses occurrence_count correctly."""
        from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary

        # Pattern A: score=0.8, occurred 5 times
        # Pattern B: score=0.2, occurred 1 time
        # Correct weighted mean = (0.8*5 + 0.2*1) / 6 = 4.2/6 = 0.7
        # Incorrect unweighted mean = (0.8 + 0.2) / 2 = 0.5

        summary = FlowSummary(
            total_demand=100.0,
            total_placed=100.0,
            overall_ratio=1.0,
            dropped_flows=0,
            num_flows=1,
        )

        entry_a = FlowEntry(
            source="A",
            destination="B",
            priority=0,
            demand=100.0,
            placed=100.0,
            dropped=0.0,
            data={"sensitivity": {"link1": 0.8}},
        )
        result_a = FlowIterationResult(
            flows=[entry_a],
            summary=summary,
            occurrence_count=5,
        )

        entry_b = FlowEntry(
            source="A",
            destination="B",
            priority=0,
            demand=100.0,
            placed=100.0,
            dropped=0.0,
            data={"sensitivity": {"link1": 0.2}},
        )
        result_b = FlowIterationResult(
            flows=[entry_b],
            summary=summary,
            occurrence_count=1,
        )

        processed = failure_manager._process_sensitivity_results([result_a, result_b])

        stats = processed["A->B"]["link1"]
        assert stats["count"] == 6.0  # 5 + 1
        assert stats["mean"] == pytest.approx(0.7)  # weighted mean
        assert stats["min"] == 0.2
        assert stats["max"] == 0.8

    def test_process_sensitivity_results_single_pattern(
        self, failure_manager: FailureManager
    ) -> None:
        """Single pattern with occurrence_count > 1 should have correct count."""
        from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary

        summary = FlowSummary(
            total_demand=50.0,
            total_placed=50.0,
            overall_ratio=1.0,
            dropped_flows=0,
            num_flows=1,
        )

        entry = FlowEntry(
            source="X",
            destination="Y",
            priority=0,
            demand=50.0,
            placed=50.0,
            dropped=0.0,
            data={"sensitivity": {"node1": 0.5}},
        )
        result = FlowIterationResult(
            flows=[entry],
            summary=summary,
            occurrence_count=10,
        )

        processed = failure_manager._process_sensitivity_results([result])

        stats = processed["X->Y"]["node1"]
        assert stats["count"] == 10.0
        assert stats["mean"] == 0.5
        assert stats["min"] == 0.5
        assert stats["max"] == 0.5
