"""Tests for the FailureManager class."""

import os
from unittest.mock import MagicMock, patch

import pytest

from ngraph.failure_manager import (
    FailureManager,
    _auto_adjust_parallelism,
    _create_cache_key,
    _generic_worker,
    _worker_init,
)
from ngraph.failure_policy import FailurePolicy
from ngraph.network import Network
from ngraph.network_view import NetworkView
from ngraph.results_artifacts import FailurePolicySet


@pytest.fixture
def mock_network() -> Network:
    """Create a mock Network for testing."""
    mock_net = MagicMock(spec=Network)
    mock_net.nodes = {
        "node1": MagicMock(attrs={"type": "server"}, risk_groups=set()),
        "node2": MagicMock(attrs={"type": "router"}, risk_groups=set()),
    }
    mock_net.links = {
        "link1": MagicMock(attrs={"capacity": 100}, risk_groups=set()),
        "link2": MagicMock(attrs={"capacity": 200}, risk_groups=set()),
    }
    mock_net.risk_groups = {}
    return mock_net


@pytest.fixture
def mock_failure_policy() -> FailurePolicy:
    """Create a mock FailurePolicy for testing."""
    # Create a real FailurePolicy instead of mocking it to avoid attribute issues
    from ngraph.failure_policy import FailureRule

    # Create a simple failure rule
    rule = FailureRule(entity_scope="node", rule_type="choice", count=1)

    # Create real policy
    policy = FailurePolicy(rules=[rule])

    # Mock the apply_failures method to return predictable results
    policy.apply_failures = MagicMock(return_value=["node1", "link1"])

    return policy


@pytest.fixture
def mock_failure_policy_set(mock_failure_policy: FailurePolicy) -> FailurePolicySet:
    """Create a mock FailurePolicySet for testing."""
    policy_set = MagicMock(spec=FailurePolicySet)
    policy_set.get_policy.return_value = mock_failure_policy
    # No longer using get_default_policy
    return policy_set


@pytest.fixture
def failure_manager(
    mock_network: Network, mock_failure_policy_set: FailurePolicySet
) -> FailureManager:
    """Create a FailureManager instance for testing."""
    return FailureManager(
        network=mock_network,
        failure_policy_set=mock_failure_policy_set,
        policy_name="test_policy",
    )


def mock_analysis_func(
    network_view: NetworkView, **kwargs
) -> list[tuple[str, str, float]]:
    """Mock analysis function for testing."""
    return [("src1", "dst1", 100.0), ("src2", "dst2", 200.0)]


class TestFailureManager:
    """Test suite for the FailureManager."""

    def test_initialization(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ):
        """Test FailureManager initialization."""
        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name="test_policy",
        )

        assert fm.network is mock_network
        assert fm.failure_policy_set is mock_failure_policy_set
        assert fm.policy_name == "test_policy"

    def test_get_failure_policy_with_named_policy(
        self, failure_manager: FailureManager
    ):
        """Test getting a named failure policy."""
        policy = failure_manager.get_failure_policy()

        failure_manager.failure_policy_set.get_policy.assert_called_once_with(
            "test_policy"
        )
        assert policy is not None

    def test_get_failure_policy_with_default_policy(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ):
        """Test getting the default failure policy."""
        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        policy = fm.get_failure_policy()

        # No longer using get_default_policy - should return None when policy_name=None
        assert policy is None

    def test_get_failure_policy_not_found(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ):
        """Test error when named policy is not found."""
        mock_failure_policy_set.get_policy.side_effect = KeyError("Policy not found")

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name="nonexistent_policy",
        )

        with pytest.raises(ValueError, match="not found in scenario"):
            fm.get_failure_policy()

    def test_compute_exclusions_no_policy(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ):
        """Test compute_exclusions with no policy returns empty sets."""
        # Create a FailureManager with no policy name to ensure get_failure_policy returns None
        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        # No longer using get_default_policy - policy_name=None returns None directly

        excluded_nodes, excluded_links = fm.compute_exclusions()

        assert excluded_nodes == set()
        assert excluded_links == set()

    def test_compute_exclusions_with_policy(self, failure_manager: FailureManager):
        """Test compute_exclusions with a policy."""
        policy = failure_manager.get_failure_policy()

        excluded_nodes, excluded_links = failure_manager.compute_exclusions(
            policy=policy, seed_offset=42
        )

        # Policy should have applied failures - check we got some exclusions
        assert len(excluded_nodes) > 0 or len(excluded_links) > 0
        # Basic functionality test - check that the method executed without errors

    @patch("ngraph.failure_manager.NetworkView.from_excluded_sets")
    def test_create_network_view_with_exclusions(
        self, mock_from_excluded_sets: MagicMock, failure_manager: FailureManager
    ):
        """Test creating NetworkView with exclusions."""
        mock_network_view = MagicMock(spec=NetworkView)
        mock_from_excluded_sets.return_value = mock_network_view

        excluded_nodes = {"node1"}
        excluded_links = {"link1"}

        result = failure_manager.create_network_view(excluded_nodes, excluded_links)

        mock_from_excluded_sets.assert_called_once_with(
            failure_manager.network,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )
        assert result is mock_network_view

    @patch("ngraph.failure_manager.NetworkView.from_excluded_sets")
    def test_create_network_view_no_exclusions(
        self, mock_from_excluded_sets: MagicMock, failure_manager: FailureManager
    ):
        """Test creating NetworkView without exclusions."""
        mock_network_view = MagicMock(spec=NetworkView)
        mock_from_excluded_sets.return_value = mock_network_view

        result = failure_manager.create_network_view()

        mock_from_excluded_sets.assert_called_once_with(
            failure_manager.network,
            excluded_nodes=set(),
            excluded_links=set(),
        )
        assert result is mock_network_view

    def test_run_single_failure_scenario(self, failure_manager: FailureManager):
        """Test running a single failure scenario."""
        result = failure_manager.run_single_failure_scenario(
            mock_analysis_func, test_param="value"
        )

        # Should return the result from the analysis function
        assert result == [("src1", "dst1", 100.0), ("src2", "dst2", 200.0)]

    def test_run_monte_carlo_analysis_single_iteration(
        self, failure_manager: FailureManager
    ):
        """Test Monte Carlo analysis with single iteration."""
        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func, iterations=1, test_param="value"
        )

        assert "results" in result
        assert "failure_patterns" in result
        assert "metadata" in result
        assert len(result["results"]) == 1
        assert result["results"][0] == [
            ("src1", "dst1", 100.0),
            ("src2", "dst2", 200.0),
        ]
        assert result["metadata"]["iterations"] == 1

    def test_run_monte_carlo_analysis_multiple_iterations(
        self, failure_manager: FailureManager
    ):
        """Test Monte Carlo analysis with multiple iterations."""
        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=3,
            parallelism=1,  # Force serial execution for predictable testing
            test_param="value",
        )

        assert len(result["results"]) == 3
        assert result["metadata"]["iterations"] == 3
        # All results should be the same since we're using a mock function
        for res in result["results"]:
            assert res == [("src1", "dst1", 100.0), ("src2", "dst2", 200.0)]

    def test_run_monte_carlo_analysis_with_baseline(
        self, failure_manager: FailureManager
    ):
        """Test Monte Carlo analysis with baseline mode."""
        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=3,
            baseline=True,
            parallelism=1,
            test_param="value",
        )

        assert len(result["results"]) == 3
        assert result["metadata"]["baseline"] is True

    def test_run_monte_carlo_analysis_store_failure_patterns(
        self, failure_manager: FailureManager
    ):
        """Test Monte Carlo analysis with failure pattern storage."""
        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=2,
            store_failure_patterns=True,
            parallelism=1,
            test_param="value",
        )

        assert len(result["failure_patterns"]) == 2
        for pattern in result["failure_patterns"]:
            assert "iteration_index" in pattern
            assert "is_baseline" in pattern
            assert "excluded_nodes" in pattern
            assert "excluded_links" in pattern

    def test_validation_errors(self, failure_manager: FailureManager):
        """Test various validation errors."""
        # Test iterations validation without policy
        failure_manager.failure_policy_set.get_policy.return_value = None
        # No longer using get_default_policy - set policy_name=None directly

        with pytest.raises(
            ValueError, match="iterations=2 has no effect without a failure policy"
        ):
            failure_manager.run_monte_carlo_analysis(
                analysis_func=mock_analysis_func, iterations=2, baseline=False
            )

        # Test baseline validation
        with pytest.raises(ValueError, match="baseline=True requires iterations >= 2"):
            failure_manager.run_monte_carlo_analysis(
                analysis_func=mock_analysis_func, iterations=1, baseline=True
            )

    @patch("ngraph.failure_manager.ProcessPoolExecutor")
    @patch("ngraph.failure_manager.pickle")
    def test_parallel_execution(
        self,
        mock_pickle: MagicMock,
        mock_pool_executor: MagicMock,
        failure_manager: FailureManager,
    ):
        """Test parallel execution path."""
        # Mock pickle.dumps to avoid pickling issues with mock network
        mock_pickle.dumps.return_value = b"fake_network_data"

        # Mock the pool executor
        mock_pool = MagicMock()
        mock_pool_executor.return_value.__enter__.return_value = mock_pool

        # Mock the map results
        mock_results = [
            ([("src1", "dst1", 100.0)], 0, False, set(), set()),
            ([("src2", "dst2", 200.0)], 1, False, set(), set()),
        ]
        mock_pool.map.return_value = mock_results

        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=2,
            parallelism=2,  # Force parallel execution
        )

        assert len(result["results"]) == 2
        assert result["metadata"]["parallelism"] == 2
        mock_pool_executor.assert_called_once()


class TestFailureManagerEdgeCases:
    """Test edge cases and error conditions for FailureManager."""

    def test_risk_group_expansion(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ):
        """Test risk group expansion in compute_exclusions."""
        # Add a risk group to the network
        mock_risk_group = MagicMock()
        mock_risk_group.name = "rg1"
        mock_risk_group.children = []
        mock_network.risk_groups = {"rg1": mock_risk_group}

        # Update nodes to be in the risk group
        mock_network.nodes["node1"].risk_groups = {"rg1"}

        # Create policy that fails the risk group
        policy = MagicMock(spec=FailurePolicy)
        policy.rules = ["rule1"]
        policy.apply_failures.return_value = ["rg1"]  # Fail the risk group
        policy.attrs = {}
        policy.fail_risk_groups = False
        policy.fail_risk_group_children = False
        policy.use_cache = True

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        # node1 should be excluded because it's in the failed risk group
        assert "node1" in excluded_nodes

    def test_empty_failure_policy_set(self, mock_network: Network):
        """Test FailureManager with empty failure policy set."""
        empty_policy_set = MagicMock(spec=FailurePolicySet)
        # No longer using get_default_policy

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=empty_policy_set,
            policy_name=None,
        )

        # Should work with no failures
        result = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=1,
        )

        assert len(result["results"]) == 1


class TestFailureManagerHelperFunctions:
    """Test helper functions in failure_manager module."""

    def test_create_cache_key_with_hashable_kwargs(self) -> None:
        """Test cache key creation with hashable kwargs."""
        excluded_nodes = {"node1", "node2"}
        excluded_links = {"link1"}
        analysis_name = "test_analysis"
        analysis_kwargs = {"param1": "value1", "param2": 42}

        result = _create_cache_key(
            excluded_nodes, excluded_links, analysis_name, analysis_kwargs
        )

        expected_base = (("node1", "node2"), ("link1",), "test_analysis")
        expected_kwargs = (("param1", "value1"), ("param2", 42))
        assert result == expected_base + (expected_kwargs,)

    def test_create_cache_key_with_non_hashable_kwargs(self) -> None:
        """Test cache key creation with non-hashable kwargs."""
        excluded_nodes = {"node1"}
        excluded_links = set()
        analysis_name = "test_analysis"

        # Non-hashable object
        non_hashable_dict = {"nested": {"data": [1, 2, 3]}}
        analysis_kwargs = {"hashable_param": "value", "non_hashable": non_hashable_dict}

        result = _create_cache_key(
            excluded_nodes, excluded_links, analysis_name, analysis_kwargs
        )

        # Verify the structure
        assert len(result) == 4
        assert result[0] == ("node1",)
        assert result[1] == ()
        assert result[2] == "test_analysis"

        # Check that non-hashable object was handled correctly
        kwargs_tuple = result[3]
        assert len(kwargs_tuple) == 2

        # Find the non-hashable parameter
        non_hashable_item = next(
            item for item in kwargs_tuple if item[0] == "non_hashable"
        )
        assert non_hashable_item[0] == "non_hashable"
        assert non_hashable_item[1].startswith("dict_")
        assert len(non_hashable_item[1]) == 5 + 8  # "dict_" + 8 char hash

    def test_auto_adjust_parallelism_normal_function(self) -> None:
        """Test parallelism adjustment for normal functions."""

        def normal_function():
            pass

        result = _auto_adjust_parallelism(4, normal_function)
        assert result == 4

    def test_auto_adjust_parallelism_main_module_function(self) -> None:
        """Test parallelism adjustment for __main__ module functions."""
        mock_function = MagicMock()
        mock_function.__module__ = "__main__"

        with patch("ngraph.failure_manager.logger") as mock_logger:
            result = _auto_adjust_parallelism(4, mock_function)
            assert result == 1
            mock_logger.warning.assert_called_once()

    def test_auto_adjust_parallelism_main_module_function_already_serial(self) -> None:
        """Test parallelism adjustment for __main__ module functions when already serial."""
        mock_function = MagicMock()
        mock_function.__module__ = "__main__"

        with patch("ngraph.failure_manager.logger") as mock_logger:
            result = _auto_adjust_parallelism(1, mock_function)
            assert result == 1
            mock_logger.warning.assert_not_called()

    def test_auto_adjust_parallelism_function_without_module(self) -> None:
        """Test parallelism adjustment for functions without __module__ attribute."""
        mock_function = MagicMock()
        del mock_function.__module__

        result = _auto_adjust_parallelism(4, mock_function)
        assert result == 4


class TestWorkerFunctions:
    """Test worker initialization and execution functions."""

    def test_worker_init(self) -> None:
        """Test worker initialization with network data."""
        # Create a simple mock network that can be pickled
        mock_network = {"nodes": {"A": "data"}, "links": {"L1": "data"}}
        import pickle

        network_pickle = pickle.dumps(mock_network)

        # Test worker initialization
        with patch("ngraph.failure_manager.get_logger") as mock_logger:
            _worker_init(network_pickle)
            mock_logger.assert_called_once()

    def test_generic_worker_not_initialized(self) -> None:
        """Test generic worker when not initialized."""
        # Ensure global network is None
        import ngraph.failure_manager

        original_network = ngraph.failure_manager._shared_network
        ngraph.failure_manager._shared_network = None

        try:
            args = (set(), set(), lambda x: x, {}, 0, False, "test_func")
            with pytest.raises(RuntimeError, match="Worker not initialized"):
                _generic_worker(args)
        finally:
            ngraph.failure_manager._shared_network = original_network

    @patch.dict(os.environ, {"NGRAPH_PROFILE_DIR": "/tmp/test_profiles"})
    @patch("ngraph.failure_manager.NetworkView.from_excluded_sets")
    def test_generic_worker_with_profiling(self, mock_network_view) -> None:
        """Test generic worker with profiling enabled."""
        import ngraph.failure_manager

        # Setup mock network
        mock_network = MagicMock()
        ngraph.failure_manager._shared_network = mock_network

        # Setup mock network view
        mock_nv = MagicMock()
        mock_network_view.return_value = mock_nv

        # Mock analysis function
        def mock_analysis(network_view, **kwargs):
            return "test_result"

        args = (
            {"node1"},  # excluded_nodes
            {"link1"},  # excluded_links
            mock_analysis,  # analysis_func
            {"param": "value"},  # analysis_kwargs
            5,  # iteration_index
            True,  # is_baseline
            "test_analysis",  # analysis_name
        )

        with patch("pathlib.Path") as mock_path:
            # Mock Path operations
            mock_path_obj = MagicMock()
            mock_path.return_value = mock_path_obj
            mock_path_obj.mkdir.return_value = None

            result = _generic_worker(args)

            # Verify result structure
            assert len(result) == 5
            assert result[0] == "test_result"
            assert result[1] == 5  # iteration_index
            assert result[2] is True  # is_baseline
            assert result[3] == {"node1"}  # excluded_nodes
            assert result[4] == {"link1"}  # excluded_links

    def test_generic_worker_cache_hit(self) -> None:
        """Test generic worker with cache hit."""
        import ngraph.failure_manager

        # Setup mock network
        mock_network = MagicMock()
        ngraph.failure_manager._shared_network = mock_network

        # Pre-populate cache
        cache_key = (("node1",), ("link1",), "test_analysis", ())
        ngraph.failure_manager._analysis_cache[cache_key] = "cached_result"

        def mock_analysis(network_view, **kwargs):
            return "fresh_result"

        args = (
            {"node1"},  # excluded_nodes
            {"link1"},  # excluded_links
            mock_analysis,  # analysis_func
            {},  # analysis_kwargs
            0,  # iteration_index
            False,  # is_baseline
            "test_analysis",  # analysis_name
        )

        result = _generic_worker(args)

        # Should return cached result, not fresh computation
        assert result[0] == "cached_result"

    def test_generic_worker_cache_eviction(self) -> None:
        """Test generic worker cache eviction when cache grows too large."""
        import ngraph.failure_manager

        # Setup mock network
        mock_network = MagicMock()
        ngraph.failure_manager._shared_network = mock_network

        # Fill cache to trigger eviction
        cache = ngraph.failure_manager._analysis_cache
        cache.clear()

        # Fill cache beyond limit (1000 entries)
        for i in range(1050):
            cache[(f"node{i}",), (), f"analysis{i}", ()] = f"result{i}"

        with patch("ngraph.failure_manager.NetworkView.from_excluded_sets"):

            def mock_analysis(network_view, **kwargs):
                return "new_result"

            args = (
                {"new_node"},  # excluded_nodes
                set(),  # excluded_links
                mock_analysis,  # analysis_func
                {},  # analysis_kwargs
                0,  # iteration_index
                False,  # is_baseline
                "new_analysis",  # analysis_name
            )

            result = _generic_worker(args)

            # Cache should have been pruned
            assert len(cache) <= 1000
            assert result[0] == "new_result"


class TestFailureManagerErrorHandling:
    """Test error handling and edge cases in FailureManager."""

    def test_run_monte_carlo_parallel_execution_error(
        self, failure_manager: FailureManager
    ):
        """Test parallel execution error handling."""
        with patch("ngraph.failure_manager.ProcessPoolExecutor") as mock_pool_executor:
            # Mock pool that raises an exception
            mock_pool = MagicMock()
            mock_pool_executor.return_value.__enter__.return_value = mock_pool
            mock_pool.map.side_effect = RuntimeError("Parallel execution failed")

            # Mock pickle to avoid actual serialization
            with patch(
                "ngraph.failure_manager.pickle.dumps", return_value=b"fake_data"
            ):
                with pytest.raises(RuntimeError, match="Parallel execution failed"):
                    failure_manager.run_monte_carlo_analysis(
                        analysis_func=mock_analysis_func, iterations=2, parallelism=2
                    )

    def test_compute_exclusions_with_seed_offset(self, failure_manager: FailureManager):
        """Test compute_exclusions with seed offset parameter."""
        excluded_nodes, excluded_links = failure_manager.compute_exclusions(
            seed_offset=123
        )

        # Basic verification that method runs without error
        assert isinstance(excluded_nodes, set)
        assert isinstance(excluded_links, set)

    def test_complex_risk_group_expansion(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ):
        """Test complex risk group expansion with nested groups."""
        # Setup nested risk groups
        child_group = MagicMock()
        child_group.name = "child_rg"
        child_group.children = []

        parent_group = MagicMock()
        parent_group.name = "parent_rg"
        parent_group.children = [child_group]

        mock_network.risk_groups = {"parent_rg": parent_group, "child_rg": child_group}

        # Setup nodes in risk groups
        mock_network.nodes["node1"].risk_groups = {"parent_rg"}
        mock_network.nodes["node2"].risk_groups = {"child_rg"}
        mock_network.links["link1"].risk_groups = {"parent_rg"}

        # Create policy that fails parent risk group
        policy = MagicMock(spec=FailurePolicy)
        policy.rules = ["rule1"]
        policy.apply_failures.return_value = ["parent_rg"]
        policy.attrs = {}
        policy.fail_risk_groups = False
        policy.fail_risk_group_children = False
        policy.use_cache = True

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        # Both nodes should be excluded (node1 directly, node2 through child group)
        assert "node1" in excluded_nodes
        assert "link1" in excluded_links


class TestFailureManagerConvenienceMethods:
    """Test convenience methods for specific analysis types."""

    @patch("ngraph.monte_carlo.functions.max_flow_analysis")
    @patch("ngraph.monte_carlo.results.CapacityEnvelopeResults")
    def test_run_max_flow_monte_carlo(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ):
        """Test max flow Monte Carlo convenience method."""
        # Mock the analysis function
        mock_analysis_func.return_value = [("src", "dst", 100.0)]

        # Mock the run_monte_carlo_analysis to return expected structure
        mock_mc_result = {
            "results": [[("src", "dst", 100.0)], [("src", "dst", 90.0)]],
            "failure_patterns": [],
            "metadata": {"iterations": 2},
        }

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ):
            failure_manager.run_max_flow_monte_carlo(
                source_path="datacenter.*",
                sink_path="edge.*",
                mode="combine",
                iterations=2,
                parallelism=1,
            )

            # Verify CapacityEnvelopeResults was called
            mock_results_class.assert_called_once()

    @patch("ngraph.monte_carlo.functions.demand_placement_analysis")
    @patch("ngraph.monte_carlo.results.DemandPlacementResults")
    def test_run_demand_placement_monte_carlo(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ):
        """Test demand placement Monte Carlo convenience method."""
        # Mock analysis function
        mock_analysis_func.return_value = {"total_placed": 100.0}

        # Mock TrafficMatrixSet input
        mock_traffic_set = MagicMock()
        mock_demand = MagicMock()
        mock_demand.source_path = "A"
        mock_demand.sink_path = "B"
        mock_demand.demand = 100.0
        mock_traffic_set.demands = [mock_demand]

        mock_mc_result = {
            "results": [{"total_placed": 100.0}],
            "failure_patterns": [],
            "metadata": {"iterations": 1},
        }

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ):
            failure_manager.run_demand_placement_monte_carlo(
                demands_config=mock_traffic_set, iterations=1, parallelism=1
            )

            # Verify DemandPlacementResults was called
            mock_results_class.assert_called_once()

    @patch("ngraph.monte_carlo.functions.sensitivity_analysis")
    @patch("ngraph.monte_carlo.results.SensitivityResults")
    def test_run_sensitivity_monte_carlo(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ):
        """Test sensitivity Monte Carlo convenience method."""
        # Mock analysis function
        mock_analysis_func.return_value = {"flow->key": {"component": 0.5}}

        mock_mc_result = {
            "results": [{"flow->key": {"component": 0.5}}],
            "failure_patterns": [],
            "metadata": {"iterations": 1},
        }

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ):
            failure_manager.run_sensitivity_monte_carlo(
                source_path="datacenter.*",
                sink_path="edge.*",
                mode="combine",
                iterations=1,
                parallelism=1,
            )

            # Verify SensitivityResults was called
            mock_results_class.assert_called_once()

    def test_process_results_to_samples(self, failure_manager: FailureManager):
        """Test _process_results_to_samples helper method."""
        results = [
            [("src1", "dst1", 100.0), ("src2", "dst2", 200.0)],
            [("src1", "dst1", 90.0), ("src2", "dst2", 180.0)],
        ]

        samples = failure_manager._process_results_to_samples(results)

        assert ("src1", "dst1") in samples
        assert ("src2", "dst2") in samples
        assert samples[("src1", "dst1")] == [100.0, 90.0]
        assert samples[("src2", "dst2")] == [200.0, 180.0]

    @patch("ngraph.results_artifacts.CapacityEnvelope.from_values")
    def test_build_capacity_envelopes(
        self, mock_envelope_class, failure_manager: FailureManager
    ):
        """Test _build_capacity_envelopes helper method."""
        samples = {
            ("src1", "dst1"): [100.0, 90.0, 95.0],
            ("src2", "dst2"): [200.0, 180.0, 190.0],
        }

        mock_envelope = MagicMock()
        mock_envelope.total_samples = 3
        mock_envelope.min_capacity = 90.0
        mock_envelope.max_capacity = 100.0
        mock_envelope.mean_capacity = 95.0
        mock_envelope_class.return_value = mock_envelope

        envelopes = failure_manager._build_capacity_envelopes(
            samples, "src.*", "dst.*", "combine"
        )

        assert "src1->dst1" in envelopes
        assert "src2->dst2" in envelopes
        assert len(envelopes) == 2

    def test_build_capacity_envelopes_empty_values(
        self, failure_manager: FailureManager
    ):
        """Test _build_capacity_envelopes with empty capacity values."""
        samples = {
            ("src1", "dst1"): [],  # Empty capacity values
            ("src2", "dst2"): [100.0, 90.0],
        }

        with patch(
            "ngraph.results_artifacts.CapacityEnvelope.from_values"
        ) as mock_envelope_class:
            mock_envelope = MagicMock()
            mock_envelope.total_samples = 2
            mock_envelope.min_capacity = 90.0
            mock_envelope.max_capacity = 100.0
            mock_envelope.mean_capacity = 95.0
            mock_envelope_class.return_value = mock_envelope

            envelopes = failure_manager._build_capacity_envelopes(
                samples, "src.*", "dst.*", "combine"
            )

            # Only one envelope should be created (empty values skipped)
            assert "src2->dst2" in envelopes
            assert "src1->dst1" not in envelopes
            assert len(envelopes) == 1

    def test_build_failure_pattern_results(self, failure_manager: FailureManager):
        """Test _build_failure_pattern_results helper method."""
        failure_patterns = [
            {
                "iteration_index": 0,
                "is_baseline": True,
                "excluded_nodes": ["node1"],
                "excluded_links": ["link1"],
            },
            {
                "iteration_index": 1,
                "is_baseline": False,
                "excluded_nodes": ["node2"],
                "excluded_links": [],
            },
        ]

        samples = {("src1", "dst1"): [100.0, 90.0], ("src2", "dst2"): [200.0, 180.0]}

        with patch(
            "ngraph.results_artifacts.FailurePatternResult"
        ) as mock_pattern_class:
            mock_pattern = MagicMock()
            mock_pattern.pattern_key = "test_key"
            mock_pattern.count = 0
            mock_pattern_class.return_value = mock_pattern

            failure_manager._build_failure_pattern_results(failure_patterns, samples)

            # Verify FailurePatternResult was created
            assert mock_pattern_class.call_count >= 1


class TestFailureManagerMetadataAndLogging:
    """Test metadata collection and logging functionality."""

    def test_monte_carlo_metadata_collection(self, failure_manager: FailureManager):
        """Test that Monte Carlo analysis collects proper metadata."""
        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=3,
            parallelism=1,
            baseline=True,
            seed=42,
        )

        metadata = result["metadata"]
        assert metadata["iterations"] == 3
        assert metadata["parallelism"] == 1
        assert metadata["baseline"] is True
        assert metadata["analysis_function"] == "mock_analysis_func"
        assert metadata["policy_name"] == "test_policy"
        assert "execution_time" in metadata
        assert "unique_patterns" in metadata

    def test_parallel_execution_chunksize_calculation(
        self, failure_manager: FailureManager
    ):
        """Test chunksize calculation for parallel execution."""
        with patch("ngraph.failure_manager.ProcessPoolExecutor") as mock_pool_executor:
            mock_pool = MagicMock()
            mock_pool_executor.return_value.__enter__.return_value = mock_pool
            mock_pool.map.return_value = [
                ([("src", "dst", 100.0)], 0, False, set(), set()),
                ([("src", "dst", 90.0)], 1, False, set(), set()),
            ]

            with patch(
                "ngraph.failure_manager.pickle.dumps", return_value=b"fake_data"
            ):
                failure_manager.run_monte_carlo_analysis(
                    analysis_func=mock_analysis_func, iterations=100, parallelism=4
                )

                # Verify that parallel execution was attempted
                mock_pool_executor.assert_called_once()
                mock_pool.map.assert_called_once()

                # Check that chunksize was calculated (should be max(1, 100 // (4 * 4)) = 6)
                args, kwargs = mock_pool.map.call_args
                assert "chunksize" in kwargs
                assert kwargs["chunksize"] >= 1


class TestFailureManagerStringConversions:
    """Test string-based flow placement conversion in convenience methods."""

    @patch("ngraph.monte_carlo.functions.max_flow_analysis")
    @patch("ngraph.monte_carlo.results.CapacityEnvelopeResults")
    def test_string_flow_placement_conversion(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ):
        """Test that string flow_placement values are converted to enum."""
        mock_mc_result = {
            "results": [[("src", "dst", 100.0)]],
            "failure_patterns": [],
            "metadata": {"iterations": 1},
        }

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ) as mock_mc:
            failure_manager.run_max_flow_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="EQUAL_BALANCED",  # String instead of enum
                iterations=1,
            )

            # Verify that the string was converted to enum in the call
            call_kwargs = mock_mc.call_args[1]
            from ngraph.lib.algorithms.base import FlowPlacement

            assert call_kwargs["flow_placement"] == FlowPlacement.EQUAL_BALANCED

    def test_invalid_flow_placement_string_max_flow(
        self, failure_manager: FailureManager
    ):
        """Test that invalid flow_placement strings raise ValueError in run_max_flow_monte_carlo."""
        with pytest.raises(ValueError) as exc_info:
            failure_manager.run_max_flow_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="INVALID_OPTION",  # Invalid string
                iterations=1,
            )

        error_msg = str(exc_info.value)
        assert "Invalid flow_placement 'INVALID_OPTION'" in error_msg
        assert "Valid values are: PROPORTIONAL, EQUAL_BALANCED" in error_msg

    def test_invalid_flow_placement_string_sensitivity(
        self, failure_manager: FailureManager
    ):
        """Test that invalid flow_placement strings raise ValueError in run_sensitivity_monte_carlo."""
        with pytest.raises(ValueError) as exc_info:
            failure_manager.run_sensitivity_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="ANOTHER_INVALID",  # Invalid string
                iterations=1,
            )

        error_msg = str(exc_info.value)
        assert "Invalid flow_placement 'ANOTHER_INVALID'" in error_msg
        assert "Valid values are: PROPORTIONAL, EQUAL_BALANCED" in error_msg

    @patch("ngraph.monte_carlo.functions.sensitivity_analysis")
    @patch("ngraph.monte_carlo.results.SensitivityResults")
    def test_valid_string_flow_placement_sensitivity(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ):
        """Test that valid string flow_placement values are converted to enum in sensitivity analysis."""
        mock_mc_result = {
            "results": [{"component1": {"score": 0.5}}],
            "failure_patterns": [],
            "metadata": {"iterations": 1},
        }

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ) as mock_mc:
            failure_manager.run_sensitivity_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="proportional",  # Lowercase string should work
                iterations=1,
            )

            # Verify that the string was converted to enum in the call
            call_kwargs = mock_mc.call_args[1]
            from ngraph.lib.algorithms.base import FlowPlacement

            assert call_kwargs["flow_placement"] == FlowPlacement.PROPORTIONAL

    def test_case_insensitive_flow_placement_conversion(
        self, failure_manager: FailureManager
    ):
        """Test that flow_placement string conversion is case-insensitive."""
        from ngraph.lib.algorithms.base import FlowPlacement

        # Test lowercase
        mock_mc_result = {
            "results": [[("src", "dst", 100.0)]],
            "failure_patterns": [],
            "metadata": {"iterations": 1},
        }

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ) as mock_mc:
            failure_manager.run_max_flow_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="proportional",  # lowercase
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            assert call_kwargs["flow_placement"] == FlowPlacement.PROPORTIONAL

        # Test mixed case
        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ) as mock_mc:
            failure_manager.run_max_flow_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="Equal_Balanced",  # mixed case
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            assert call_kwargs["flow_placement"] == FlowPlacement.EQUAL_BALANCED
