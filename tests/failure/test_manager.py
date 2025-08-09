"""High-value tests for `FailureManager` public behavior and APIs.

Focus on functional outcomes and API semantics. Internal helper and
implementation-specific behaviors are intentionally not tested here.
"""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from ngraph.failure.manager.manager import FailureManager
from ngraph.failure.policy import FailurePolicy
from ngraph.failure.policy_set import FailurePolicySet
from ngraph.model.network import Network
from ngraph.model.view import NetworkView


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
    from ngraph.failure.policy import FailureRule

    rule = FailureRule(entity_scope="node", rule_type="choice", count=1)
    policy = FailurePolicy(rules=[rule])

    policy.apply_failures = MagicMock(return_value=["node1", "link1"])  # type: ignore[attr-defined]
    return policy


@pytest.fixture
def mock_failure_policy_set(mock_failure_policy: FailurePolicy) -> FailurePolicySet:
    """Create a mock FailurePolicySet for testing."""
    policy_set = MagicMock(spec=FailurePolicySet)
    policy_set.get_policy.return_value = mock_failure_policy
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
    """Focused tests for `FailureManager` behavior and validations."""

    def test_initialization(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
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
    ) -> None:
        policy = failure_manager.get_failure_policy()

        cast(
            MagicMock, failure_manager.failure_policy_set.get_policy
        ).assert_called_once_with("test_policy")
        assert policy is not None

    def test_get_failure_policy_with_default_policy(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        policy = fm.get_failure_policy()
        assert policy is None

    def test_get_failure_policy_not_found(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
        cast(MagicMock, mock_failure_policy_set.get_policy).side_effect = KeyError(
            "Policy not found"
        )

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name="nonexistent_policy",
        )

        with pytest.raises(ValueError, match="not found in scenario"):
            fm.get_failure_policy()

    def test_compute_exclusions_no_policy(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions()
        assert excluded_nodes == set()
        assert excluded_links == set()

    def test_compute_exclusions_with_policy(
        self, failure_manager: FailureManager
    ) -> None:
        policy = failure_manager.get_failure_policy()

        excluded_nodes, excluded_links = failure_manager.compute_exclusions(
            policy=policy, seed_offset=42
        )

        assert len(excluded_nodes) > 0 or len(excluded_links) > 0

    @patch("ngraph.failure.manager.manager.NetworkView.from_excluded_sets")
    def test_create_network_view_with_exclusions(
        self, mock_from_excluded_sets: MagicMock, failure_manager: FailureManager
    ) -> None:
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

    @patch("ngraph.failure.manager.manager.NetworkView.from_excluded_sets")
    def test_create_network_view_no_exclusions(
        self, mock_from_excluded_sets: MagicMock, failure_manager: FailureManager
    ) -> None:
        mock_network_view = MagicMock(spec=NetworkView)
        mock_from_excluded_sets.return_value = mock_network_view

        result = failure_manager.create_network_view()

        mock_from_excluded_sets.assert_called_once_with(
            failure_manager.network,
            excluded_nodes=set(),
            excluded_links=set(),
        )
        assert result is mock_network_view

    def test_run_single_failure_scenario(self, failure_manager: FailureManager) -> None:
        result = failure_manager.run_single_failure_scenario(
            mock_analysis_func, test_param="value"
        )
        assert result == [("src1", "dst1", 100.0), ("src2", "dst2", 200.0)]

    def test_run_monte_carlo_analysis_single_iteration(
        self, failure_manager: FailureManager
    ) -> None:
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
    ) -> None:
        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=3,
            parallelism=1,
            test_param="value",
        )

        assert len(result["results"]) == 3
        assert result["metadata"]["iterations"] == 3
        for res in result["results"]:
            assert res == [("src1", "dst1", 100.0), ("src2", "dst2", 200.0)]

    def test_run_monte_carlo_analysis_with_baseline(
        self, failure_manager: FailureManager
    ) -> None:
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
    ) -> None:
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

    def test_validation_errors(self, failure_manager: FailureManager) -> None:
        cast(
            MagicMock, failure_manager.failure_policy_set.get_policy
        ).return_value = None

        with pytest.raises(
            ValueError, match="iterations=2 has no effect without a failure policy"
        ):
            failure_manager.run_monte_carlo_analysis(
                analysis_func=mock_analysis_func, iterations=2, baseline=False
            )

        with pytest.raises(ValueError, match="baseline=True requires iterations >= 2"):
            failure_manager.run_monte_carlo_analysis(
                analysis_func=mock_analysis_func, iterations=1, baseline=True
            )

    @patch("ngraph.failure.manager.manager.ProcessPoolExecutor")
    @patch("ngraph.failure.manager.manager.pickle")
    def test_parallel_execution(
        self,
        mock_pickle: MagicMock,
        mock_pool_executor: MagicMock,
        failure_manager: FailureManager,
    ) -> None:
        mock_pickle.dumps.return_value = b"fake_network_data"

        mock_pool = MagicMock()
        mock_pool_executor.return_value.__enter__.return_value = mock_pool

        mock_results = [
            [("src1", "dst1", 100.0)],
            [("src2", "dst2", 200.0)],
        ]
        mock_pool.map.return_value = [
            (mock_results[0], 0, False, set(), set()),
            (mock_results[1], 1, False, set(), set()),
        ]

        result = failure_manager.run_monte_carlo_analysis(
            analysis_func=mock_analysis_func,
            iterations=2,
            parallelism=2,
        )

        assert len(result["results"]) == 2
        assert result["metadata"]["parallelism"] == 2
        mock_pool_executor.assert_called_once()


class TestFailureManagerTopLevelMatching:
    """Tests for compute_exclusions merged attribute view correctness."""

    def test_node_matching_on_top_level_disabled(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
        mock_network.nodes["node1"].disabled = True
        mock_network.nodes["node2"].disabled = False

        from ngraph.failure.policy import FailureCondition, FailurePolicy, FailureRule

        rule = FailureRule(
            entity_scope="node",
            conditions=[FailureCondition(attr="disabled", operator="==", value=True)],
            logic="and",
            rule_type="all",
        )
        policy = FailurePolicy(rules=[rule])

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        assert "node1" in excluded_nodes
        assert "node2" not in excluded_nodes
        assert excluded_links == set()

    def test_link_matching_on_top_level_capacity(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
        mock_network.links["link1"].capacity = 100.0
        mock_network.links["link2"].capacity = 50.0

        from ngraph.failure.policy import FailureCondition, FailurePolicy, FailureRule

        rule = FailureRule(
            entity_scope="link",
            conditions=[FailureCondition(attr="capacity", operator=">", value=60.0)],
            logic="and",
            rule_type="all",
        )
        policy = FailurePolicy(rules=[rule])

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        assert "link1" in excluded_links
        assert "link2" not in excluded_links
        assert excluded_nodes == set()

    def test_risk_group_expansion_uses_top_level_risk_groups(
        self, mock_network: Network, mock_failure_policy_set: FailurePolicySet
    ) -> None:
        mock_risk_group = MagicMock()
        mock_risk_group.name = "rg1"
        mock_risk_group.children = []
        mock_network.risk_groups = {"rg1": mock_risk_group}
        mock_network.nodes["node1"].risk_groups = {"rg1"}
        mock_network.links["link1"].risk_groups = {"rg1"}

        from ngraph.failure.policy import FailurePolicy, FailureRule

        rule = FailureRule(entity_scope="risk_group", rule_type="all")
        policy = FailurePolicy(rules=[rule])
        policy.apply_failures = MagicMock(return_value=["rg1"])  # type: ignore[attr-defined]

        fm = FailureManager(
            network=mock_network,
            failure_policy_set=mock_failure_policy_set,
            policy_name=None,
        )

        excluded_nodes, excluded_links = fm.compute_exclusions(policy=policy)

        assert "node1" in excluded_nodes
        assert "link1" in excluded_links


class TestFailureManagerErrorHandling:
    """Test error handling and edge cases in FailureManager."""

    def test_run_monte_carlo_parallel_execution_error(
        self, failure_manager: FailureManager
    ) -> None:
        with patch(
            "ngraph.failure.manager.manager.ProcessPoolExecutor"
        ) as mock_pool_executor:
            mock_pool = MagicMock()
            mock_pool_executor.return_value.__enter__.return_value = mock_pool
            mock_pool.map.side_effect = RuntimeError("Parallel execution failed")

            with patch(
                "ngraph.failure.manager.manager.pickle.dumps", return_value=b"fake_data"
            ):
                with pytest.raises(RuntimeError, match="Parallel execution failed"):
                    failure_manager.run_monte_carlo_analysis(
                        analysis_func=mock_analysis_func, iterations=2, parallelism=2
                    )


class TestFailureManagerConvenienceMethods:
    """Test convenience methods for specific analysis types."""

    @patch("ngraph.monte_carlo.functions.max_flow_analysis")
    @patch("ngraph.monte_carlo.results.CapacityEnvelopeResults")
    def test_run_max_flow_monte_carlo(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ) -> None:
        mock_analysis_func.return_value = [("src", "dst", 100.0)]

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

            mock_results_class.assert_called_once()

    @patch("ngraph.monte_carlo.functions.demand_placement_analysis")
    @patch("ngraph.monte_carlo.results.DemandPlacementResults")
    def test_run_demand_placement_monte_carlo(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ) -> None:
        mock_analysis_func.return_value = {"total_placed": 100.0}

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

            mock_results_class.assert_called_once()

    @patch("ngraph.monte_carlo.functions.sensitivity_analysis")
    @patch("ngraph.monte_carlo.results.SensitivityResults")
    def test_run_sensitivity_monte_carlo(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ) -> None:
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

            mock_results_class.assert_called_once()


class TestFailureManagerMetadataAndLogging:
    """Test metadata collection and logging functionality."""

    def test_monte_carlo_metadata_collection(
        self, failure_manager: FailureManager
    ) -> None:
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


class TestFailureManagerStringConversions:
    """Test string-based flow placement conversion in convenience methods."""

    @patch("ngraph.monte_carlo.functions.max_flow_analysis")
    @patch("ngraph.monte_carlo.results.CapacityEnvelopeResults")
    def test_string_flow_placement_conversion(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ) -> None:
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
                flow_placement="EQUAL_BALANCED",
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            from ngraph.algorithms.base import FlowPlacement

            assert call_kwargs["flow_placement"] == FlowPlacement.EQUAL_BALANCED

    def test_invalid_flow_placement_string_max_flow(
        self, failure_manager: FailureManager
    ) -> None:
        with pytest.raises(ValueError) as exc_info:
            failure_manager.run_max_flow_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="INVALID_OPTION",
                iterations=1,
            )

        error_msg = str(exc_info.value)
        assert "Invalid flow_placement 'INVALID_OPTION'" in error_msg
        assert "Valid values are: PROPORTIONAL, EQUAL_BALANCED" in error_msg

    def test_invalid_flow_placement_string_sensitivity(
        self, failure_manager: FailureManager
    ) -> None:
        with pytest.raises(ValueError) as exc_info:
            failure_manager.run_sensitivity_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="ANOTHER_INVALID",
                iterations=1,
            )

        error_msg = str(exc_info.value)
        assert "Invalid flow_placement 'ANOTHER_INVALID'" in error_msg
        assert "Valid values are: PROPORTIONAL, EQUAL_BALANCED" in error_msg

    @patch("ngraph.monte_carlo.functions.sensitivity_analysis")
    @patch("ngraph.monte_carlo.results.SensitivityResults")
    def test_valid_string_flow_placement_sensitivity(
        self, mock_results_class, mock_analysis_func, failure_manager: FailureManager
    ) -> None:
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
                flow_placement="proportional",
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            from ngraph.algorithms.base import FlowPlacement

            assert call_kwargs["flow_placement"] == FlowPlacement.PROPORTIONAL

    def test_case_insensitive_flow_placement_conversion(
        self, failure_manager: FailureManager
    ) -> None:
        from ngraph.algorithms.base import FlowPlacement

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
                flow_placement="proportional",
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            assert call_kwargs["flow_placement"] == FlowPlacement.PROPORTIONAL

        with patch.object(
            failure_manager, "run_monte_carlo_analysis", return_value=mock_mc_result
        ) as mock_mc:
            failure_manager.run_max_flow_monte_carlo(
                source_path="src.*",
                sink_path="dst.*",
                flow_placement="Equal_Balanced",
                iterations=1,
            )

            call_kwargs = mock_mc.call_args[1]
            assert call_kwargs["flow_placement"] == FlowPlacement.EQUAL_BALANCED
