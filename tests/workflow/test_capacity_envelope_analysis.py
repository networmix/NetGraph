from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.algorithms.base import FlowPlacement
from ngraph.failure.policy import FailurePolicy, FailureRule
from ngraph.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node
from ngraph.results import Results
from ngraph.scenario import Scenario
from ngraph.workflow.max_flow_step import MaxFlow


@pytest.fixture
def simple_network() -> Network:
    """Create a simple test network."""
    network = Network()
    network.add_node(Node("A"))
    network.add_node(Node("B"))
    network.add_node(Node("C"))
    network.add_link(Link("A", "B", capacity=10.0))
    network.add_link(Link("B", "C", capacity=5.0))
    return network


@pytest.fixture
def simple_failure_policy() -> FailurePolicy:
    """Create a simple failure policy that fails one link."""
    rule = FailureRule(
        entity_scope="link",
        rule_type="choice",
        count=1,
    )
    return FailurePolicy(
        modes=[
            __import__("ngraph.failure.policy", fromlist=["FailureMode"]).FailureMode(
                weight=1.0, rules=[rule]
            )
        ]
    )


@pytest.fixture
def mock_scenario(simple_network, simple_failure_policy) -> Scenario:
    """Create a mock scenario for testing."""
    scenario = MagicMock(spec=Scenario)
    scenario.network = simple_network
    scenario.results = Results()

    # Create failure policy set
    policy_set = FailurePolicySet()
    policy_set.add("test_policy", simple_failure_policy)
    scenario.failure_policy_set = policy_set

    return scenario


class TestMaxFlowStep:
    """Test suite for MaxFlow workflow step."""

    def test_initialization_defaults(self):
        """Test MaxFlow initialization with defaults."""
        step = MaxFlow(source_path="^A", sink_path="^C")

        assert step.source_path == "^A"
        assert step.sink_path == "^C"
        assert step.mode == "combine"
        assert step.failure_policy is None
        assert step.iterations == 1
        assert step.parallelism == "auto"
        assert step.shortest_path is False
        assert step.flow_placement == FlowPlacement.PROPORTIONAL
        assert step.baseline is False
        assert step.seed is None
        assert step.store_failure_patterns is False
        assert step.include_flow_details is False

    def test_initialization_custom_values(self):
        """Test MaxFlow initialization with custom values."""
        step = MaxFlow(
            source_path="^src",
            sink_path="^dst",
            mode="pairwise",
            failure_policy="test_policy",
            iterations=100,
            parallelism=4,
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            baseline=True,
            seed=42,
            store_failure_patterns=True,
            include_flow_details=True,
        )

        assert step.source_path == "^src"
        assert step.sink_path == "^dst"
        assert step.mode == "pairwise"
        assert step.failure_policy == "test_policy"
        assert step.iterations == 100
        assert step.parallelism == 4
        assert step.shortest_path is True
        assert step.flow_placement == FlowPlacement.EQUAL_BALANCED
        assert step.baseline is True
        assert step.seed == 42
        assert step.store_failure_patterns is True
        assert step.include_flow_details is True

    def test_validation_errors(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="iterations must be >= 1"):
            MaxFlow(source_path="^A", sink_path="^C", iterations=0)

        with pytest.raises(ValueError, match="parallelism must be >= 1"):
            MaxFlow(source_path="^A", sink_path="^C", parallelism=0)

        with pytest.raises(ValueError, match="mode must be 'combine' or 'pairwise'"):
            MaxFlow(source_path="^A", sink_path="^C", mode="invalid")

        with pytest.raises(ValueError, match="baseline=True requires iterations >= 2"):
            MaxFlow(source_path="^A", sink_path="^C", baseline=True, iterations=1)

    def test_flow_placement_enum_usage(self):
        """Test that FlowPlacement enum is used correctly."""
        step = MaxFlow(
            source_path="^A", sink_path="^C", flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert step.flow_placement == FlowPlacement.PROPORTIONAL

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_run_with_mock_failure_manager(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test running the workflow step with mocked FailureManager."""
        # Setup mock FailureManager
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Mock the convenience method results returning unified flow_results
        mock_raw = {
            "results": [
                {
                    "failure_id": "baseline",
                    "failure_state": {"excluded_nodes": [], "excluded_links": []},
                    "flows": [
                        {
                            "source": "A",
                            "destination": "C",
                            "priority": 0,
                            "demand": 5.0,
                            "placed": 5.0,
                            "dropped": 0.0,
                            "cost_distribution": {},
                            "data": {},
                        }
                    ],
                    "summary": {
                        "total_demand": 5.0,
                        "total_placed": 5.0,
                        "overall_ratio": 1.0,
                        "dropped_flows": 0,
                        "num_flows": 1,
                    },
                }
            ],
            "metadata": {"iterations": 1, "parallelism": 1, "baseline": False},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        # Create and run the step
        step = MaxFlow(
            source_path="^A",
            sink_path="^C",
            failure_policy="test_policy",
            iterations=1,
            parallelism=1,
        )
        step.name = "envelope"
        step.execute(mock_scenario)

        # Verify FailureManager was created correctly
        mock_failure_manager_class.assert_called_once_with(
            network=mock_scenario.network,
            failure_policy_set=mock_scenario.failure_policy_set,
            policy_name="test_policy",
        )

        # Verify convenience method was called with correct parameters
        _, kwargs = mock_failure_manager.run_max_flow_monte_carlo.call_args
        assert kwargs["source_path"] == "^A"
        assert kwargs["sink_path"] == "^C"
        assert kwargs["mode"] == "combine"
        assert kwargs["iterations"] == 1
        assert kwargs["parallelism"] == 1
        assert kwargs["shortest_path"] is False
        assert kwargs["flow_placement"] == step.flow_placement
        assert kwargs["baseline"] is False
        assert kwargs["seed"] is None
        assert kwargs["store_failure_patterns"] is False
        assert kwargs["include_flow_summary"] is False

        # Verify results were processed into metadata + data with flow_results
        exported = mock_scenario.results.to_dict()
        data = exported["steps"]["envelope"]["data"]
        assert isinstance(data, dict)
        assert "flow_results" in data and isinstance(data["flow_results"], list)
        assert len(data["flow_results"]) == 1

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_run_with_failure_patterns(self, mock_failure_manager_class, mock_scenario):
        """Test running with failure pattern storage enabled."""
        # Setup mock FailureManager
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Mock raw results and patterns
        mock_raw = {
            "results": [
                {
                    "failure_id": "deadbeef",
                    "failure_state": {
                        "excluded_nodes": ["node1"],
                        "excluded_links": [],
                    },
                    "flows": [],
                    "summary": {
                        "total_demand": 0.0,
                        "total_placed": 0.0,
                        "overall_ratio": 1.0,
                        "dropped_flows": 0,
                        "num_flows": 0,
                    },
                }
            ],
            "metadata": {"iterations": 2, "parallelism": 1, "baseline": False},
            "failure_patterns": [
                {
                    "iteration_index": 0,
                    "is_baseline": False,
                    "excluded_nodes": ["node1"],
                    "excluded_links": [],
                }
            ],
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        # Create and run the step with failure pattern storage
        step = MaxFlow(
            source_path="^A",
            sink_path="^C",
            iterations=2,
            store_failure_patterns=True,
            parallelism=1,
        )
        step.execute(mock_scenario)

        # Verify parameters passed
        _, kwargs = mock_failure_manager.run_max_flow_monte_carlo.call_args
        assert kwargs["store_failure_patterns"] is True
        assert kwargs["include_flow_summary"] is False

    def test_capacity_envelope_with_failures_mocked(self):
        """Test capacity envelope step with mocked FailureManager."""
        step = MaxFlow(
            source_path="^A",
            sink_path="^C",
            mode="combine",
            iterations=2,
            parallelism=1,
            baseline=False,
            store_failure_patterns=True,
        )

        scenario = Scenario(
            network=MagicMock(),
            workflow=[],  # Empty workflow for testing
            failure_policy_set=MagicMock(),
            results=Results(),
        )

        # Mock the convenience method call results (unified flow_results)
        mock_raw = {
            "results": [
                {
                    "failure_id": "",
                    "failure_state": {"excluded_nodes": [], "excluded_links": []},
                    "flows": [],
                    "summary": {
                        "total_demand": 0.0,
                        "total_placed": 0.0,
                        "overall_ratio": 1.0,
                        "dropped_flows": 0,
                        "num_flows": 0,
                    },
                }
            ],
            "metadata": {"iterations": 2, "parallelism": 1, "baseline": False},
        }

        # Mock the FailureManager class and its convenience method
        with patch("ngraph.workflow.max_flow_step.FailureManager") as mock_fm_class:
            mock_fm_instance = mock_fm_class.return_value
            mock_fm_instance.run_max_flow_monte_carlo.return_value = mock_raw

            step.name = "envelope"
            step.execute(scenario)

        # Check that results were stored under metadata/data keys
        exported = scenario.results.to_dict()
        assert exported["steps"]["envelope"]["metadata"] is not None
        assert exported["steps"]["envelope"]["data"] is not None

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_include_flow_summary_functionality(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test that include_flow_details parameter is passed through correctly."""
        # Setup mock FailureManager
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Mock results with flow details (cost_distribution and min_cut edges)
        mock_raw = {
            "results": [
                {
                    "failure_id": "",
                    "failure_state": {"excluded_nodes": [], "excluded_links": []},
                    "flows": [
                        {
                            "source": "A",
                            "destination": "C",
                            "priority": 0,
                            "demand": 5.0,
                            "placed": 5.0,
                            "dropped": 0.0,
                            "cost_distribution": {"3": 5.0},
                            "data": {
                                "edges": ["('A','B','k')"],
                                "edges_kind": "min_cut",
                            },
                        }
                    ],
                    "summary": {
                        "total_demand": 5.0,
                        "total_placed": 5.0,
                        "overall_ratio": 1.0,
                        "dropped_flows": 0,
                        "num_flows": 1,
                    },
                }
            ],
            "metadata": {"iterations": 1, "parallelism": 1, "baseline": False},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        # Test with include_flow_details=True
        step = MaxFlow(
            source_path="^A",
            sink_path="^C",
            iterations=1,
            include_flow_details=True,
            parallelism=1,
        )
        step.execute(mock_scenario)

        # Verify the parameter was passed through correctly
        _, kwargs = mock_failure_manager.run_max_flow_monte_carlo.call_args
        assert kwargs["include_flow_summary"] is True

        # Verify run without error; detailed stats are embedded in flow_results entries now
