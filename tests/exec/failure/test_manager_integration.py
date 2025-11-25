"""Tests for FailureManager core functionality and integration."""

import pytest

from ngraph.exec.analysis.flow import max_flow_analysis
from ngraph.exec.failure.manager import FailureManager
from ngraph.model.failure.policy import FailurePolicy, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Network
from ngraph.results.flow import FlowIterationResult


class TestFailureManagerCore:
    """Test core FailureManager functionality."""

    @pytest.fixture
    def simple_network(self):
        """Create a simple test network."""
        from ngraph.model.network import Link, Node

        network = Network()
        network.attrs["name"] = "test_network"
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_node(Node("C"))
        network.add_link(Link("A", "B", capacity=10.0, cost=1))
        network.add_link(Link("B", "C", capacity=10.0, cost=1))
        network.add_link(Link("A", "C", capacity=5.0, cost=1))
        return network

    @pytest.fixture
    def failure_policy_set(self):
        """Create test failure policies."""
        policy_set = FailurePolicySet()

        # Single link failure policy
        rule = FailureRule(
            entity_scope="link",
            rule_type="choice",
            count=1,
        )
        from ngraph.model.failure.policy import FailureMode

        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])
        policy_set.policies["single_failures"] = policy

        # No failure policy
        from ngraph.model.failure.policy import FailureMode

        no_fail_policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[])])
        policy_set.policies["no_failures"] = no_fail_policy

        return policy_set

    def test_failure_manager_initialization(self, simple_network, failure_policy_set):
        """Test FailureManager initialization."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        assert manager.network == simple_network
        assert manager.failure_policy_set == failure_policy_set
        assert manager.policy_name == "single_failures"

    def test_get_failure_policy_by_name(self, simple_network, failure_policy_set):
        """Test retrieving specific failure policy."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        policy = manager.get_failure_policy()
        assert policy is not None

    def test_get_no_failure_policy(self, simple_network, failure_policy_set):
        """Test that policy_name=None returns None (no default policy behavior)."""
        # Add a named policy (but no default behavior)
        failure_policy_set.policies["default"] = failure_policy_set.policies[
            "single_failures"
        ]

        manager = FailureManager(simple_network, failure_policy_set, None)
        policy = manager.get_failure_policy()
        assert policy is None  # No implicit default policy behavior

    def test_invalid_policy_name_error(self, simple_network, failure_policy_set):
        """Test error handling for invalid policy name."""
        manager = FailureManager(simple_network, failure_policy_set, "nonexistent")

        with pytest.raises(ValueError, match="Failure policy 'nonexistent' not found"):
            manager.get_failure_policy()

    def test_compute_exclusions_no_failures(self, simple_network, failure_policy_set):
        """Test exclusion computation with no-failure policy."""
        manager = FailureManager(simple_network, failure_policy_set, "no_failures")

        excluded_nodes, excluded_links = manager.compute_exclusions()
        assert len(excluded_nodes) == 0
        assert len(excluded_links) == 0

    def test_compute_exclusions_with_failures(self, simple_network, failure_policy_set):
        """Test exclusion computation with failure policy."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        # Use fixed seed for deterministic testing
        excluded_nodes, excluded_links = manager.compute_exclusions(seed_offset=42)

        # Should exclude exactly one link based on policy
        assert len(excluded_nodes) == 0  # Policy targets links, not nodes
        assert len(excluded_links) == 1

        # Excluded link should be from the network
        network_link_ids = set(simple_network.links)  # links property returns link IDs
        assert excluded_links.issubset(network_link_ids)

    def test_run_monte_carlo_analysis(self, simple_network, failure_policy_set):
        """Test Monte Carlo analysis execution."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        # Run analysis with max flow function
        results = manager.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=5,  # Small number for testing
            parallelism=1,  # Serial execution for deterministic testing
            seed=42,
            # Pass analysis parameters directly as kwargs
            source_regex="A",
            sink_regex="C",
            mode="combine",
        )

        assert "results" in results
        assert "metadata" in results
        assert len(results["results"]) == 5

        # Each item is a FlowIterationResult; compute placed capacity
        capacities = [
            float(iter_res.summary.total_placed)
            for iter_res in results["results"]
            if isinstance(iter_res, FlowIterationResult)
        ]
        # With the network topology (A->B->C and A->C), max flow is 15.0 without failures
        # (10.0 through B + 5.0 direct)
        # With single link failures (policy always fails 1 link):
        # - Exclude A->B or B->C: capacity is 5.0 (only direct path)
        # - Exclude A->C: capacity is 10.0 (only via B)
        # The test runs 5 iterations with failures, so we see a mix of 5.0 and 10.0
        assert max(capacities) == 10.0  # Best case with 1 failure
        assert min(capacities) == 5.0  # Worst case with 1 failure
        assert 5.0 in capacities  # Should see some 5.0 results
        assert 10.0 in capacities  # Should see some 10.0 results

    def test_analysis_with_parallel_execution(self, simple_network, failure_policy_set):
        """Test parallel execution of Monte Carlo analysis."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        # Run with multiple workers
        results = manager.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=4,
            parallelism=2,  # Multiple workers
            seed=42,
            source_regex="A",
            sink_regex="C",
            mode="combine",
        )

        assert len(results["results"]) == 4
        assert "metadata" in results

    def test_baseline_iteration_handling(self, simple_network, failure_policy_set):
        """Test baseline iteration (no failures) behavior."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        results = manager.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=3,
            parallelism=1,
            baseline=True,  # Include baseline
            seed=42,
            source_regex="A",
            sink_regex="C",
            mode="combine",
        )

        # Should have results from baseline + regular iterations
        assert len(results["results"]) == 3
        assert "metadata" in results

        # Baseline should be included (enabled with baseline=True)
        metadata = results["metadata"]
        assert metadata["baseline"]

    def test_failure_pattern_storage(self, simple_network, failure_policy_set):
        """Test storage of failure patterns in results."""
        manager = FailureManager(simple_network, failure_policy_set, "single_failures")

        results = manager.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=5,
            parallelism=1,
            store_failure_patterns=True,
            seed=42,
            source_regex="A",
            sink_regex="C",
            mode="combine",
        )

        assert "failure_patterns" in results
        failure_patterns = results["failure_patterns"]

        # Should have recorded failure patterns (may be empty list in this simple case)
        assert isinstance(failure_patterns, list)


class TestFailureManagerIntegration:
    """Test FailureManager integration with workflow systems."""

    def test_capacity_envelope_analysis_integration(self):
        """Test integration with capacity analysis workflow producing FlowIterationResult."""
        # Create larger network for meaningful analysis
        from ngraph.model.network import Link, Node

        network = Network()
        network.attrs["name"] = "spine_leaf"

        # Add spine nodes
        network.add_node(Node("spine1"))
        network.add_node(Node("spine2"))

        # Add leaf nodes
        network.add_node(Node("leaf1"))
        network.add_node(Node("leaf2"))
        network.add_node(Node("leaf3"))

        # Add spine-leaf connections
        for spine in ["spine1", "spine2"]:
            for leaf in ["leaf1", "leaf2", "leaf3"]:
                network.add_link(Link(spine, leaf, capacity=10.0, cost=1))

        # Create failure policy
        policy_set = FailurePolicySet()
        rule = FailureRule(
            entity_scope="link",
            rule_type="choice",
            count=2,
        )
        from ngraph.model.failure.policy import FailureMode

        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])
        policy_set.policies["dual_link_failures"] = policy

        manager = FailureManager(network, policy_set, "dual_link_failures")

        # Run capacity analysis
        results = manager.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=10,
            parallelism=1,
            seed=123,
            source_regex="spine.*",
            sink_regex="leaf.*",
            mode="pairwise",
        )

        # Verify meaningful results
        assert "results" in results
        assert "metadata" in results

        # Should have results for each iteration
        assert len(results["results"]) == 10

        # Each result is a FlowIterationResult; ensure flows present
        for iter_res in results["results"]:
            assert isinstance(iter_res, FlowIterationResult)
            assert hasattr(iter_res, "summary")
            assert isinstance(iter_res.flows, list)

    def test_error_handling_in_analysis(self):
        """Test error handling during analysis execution."""
        # Create test network
        from ngraph.model.network import Link, Node

        network = Network()
        network.attrs["name"] = "test_network"
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B", capacity=10.0, cost=1))

        def failing_analysis_func(*args, **kwargs):
            raise ValueError("Simulated analysis failure")

        # Policy that excludes nothing
        policy_set = FailurePolicySet()
        from ngraph.model.failure.policy import FailureMode

        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[])])
        policy_set.policies["no_failures"] = policy

        manager = FailureManager(network, policy_set, "no_failures")

        # Analysis should handle worker errors gracefully
        with pytest.raises(ValueError):  # Should propagate the specific error
            manager.run_monte_carlo_analysis(
                analysis_func=failing_analysis_func,
                iterations=3,
                parallelism=1,
                seed=42,
            )
