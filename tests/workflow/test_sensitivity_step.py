from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ngraph.model.failure.policy import FailurePolicy, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node
from ngraph.results import Results
from ngraph.scenario import Scenario
from ngraph.types.base import FlowPlacement
from ngraph.workflow.sensitivity_step import Sensitivity


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
        scope="link",
        mode="choice",
        count=1,
    )
    return FailurePolicy(
        modes=[
            __import__(
                "ngraph.model.failure.policy", fromlist=["FailureMode"]
            ).FailureMode(weight=1.0, rules=[rule])
        ]
    )


@pytest.fixture
def mock_scenario(simple_network, simple_failure_policy) -> Scenario:
    """Create a mock scenario for testing."""
    scenario = MagicMock(spec=Scenario)
    scenario.network = simple_network
    scenario.results = Results()
    scenario.seed = None
    scenario._execution_counter = 0

    policy_set = FailurePolicySet()
    policy_set.add("test_policy", simple_failure_policy)
    scenario.failure_policy_set = policy_set

    return scenario


class TestSensitivityStep:
    """Test suite for Sensitivity workflow step."""

    def test_initialization_defaults(self):
        """Test Sensitivity initialization with defaults."""
        step = Sensitivity(source="^A", target="^C")

        assert step.source == "^A"
        assert step.target == "^C"
        assert step.mode == "combine"
        assert step.failure_policy is None
        assert step.iterations == 1
        assert step.parallelism == "auto"
        assert step.shortest_path is False
        assert step.flow_placement == FlowPlacement.PROPORTIONAL
        assert step.seed is None
        assert step.store_failure_patterns is False

    def test_initialization_custom_values(self):
        """Test Sensitivity initialization with custom values."""
        step = Sensitivity(
            source="^src",
            target="^dst",
            mode="pairwise",
            failure_policy="test_policy",
            iterations=100,
            parallelism=4,
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            seed=42,
            store_failure_patterns=True,
        )

        assert step.source == "^src"
        assert step.target == "^dst"
        assert step.mode == "pairwise"
        assert step.failure_policy == "test_policy"
        assert step.iterations == 100
        assert step.parallelism == 4
        assert step.shortest_path is True
        assert step.flow_placement == FlowPlacement.EQUAL_BALANCED
        assert step.seed == 42
        assert step.store_failure_patterns is True

    def test_validation_errors(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="iterations must be >= 0"):
            Sensitivity(source="^A", target="^C", iterations=-1)

        with pytest.raises(ValueError, match="parallelism must be >= 1"):
            Sensitivity(source="^A", target="^C", parallelism=0)

        with pytest.raises(ValueError, match="mode must be 'combine' or 'pairwise'"):
            Sensitivity(source="^A", target="^C", mode="invalid")

        with pytest.raises(
            ValueError, match="parallelism must be an integer or 'auto'"
        ):
            Sensitivity(source="^A", target="^C", parallelism="bad")

    def test_flow_placement_string_conversion(self):
        """Test that string flow_placement is converted to enum."""
        step = Sensitivity(source="^A", target="^C", flow_placement="PROPORTIONAL")
        assert step.flow_placement == FlowPlacement.PROPORTIONAL

    def test_flow_placement_enum_passthrough(self):
        """Test that FlowPlacement enum is accepted directly."""
        step = Sensitivity(
            source="^A", target="^C", flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert step.flow_placement == FlowPlacement.EQUAL_BALANCED

    @patch("ngraph.workflow.sensitivity_step.FailureManager")
    def test_run_forwards_correct_args(self, mock_failure_manager_class, mock_scenario):
        """Test that run() passes correct arguments to run_sensitivity_monte_carlo."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        mock_raw = {
            "baseline": {
                "failure_id": "",
                "failure_state": {"excluded_nodes": [], "excluded_links": []},
                "failure_trace": None,
                "flows": [
                    {
                        "source": "A",
                        "destination": "C",
                        "priority": 0,
                        "demand": 5.0,
                        "placed": 5.0,
                        "dropped": 0.0,
                        "cost_distribution": {},
                        "data": {"sensitivity": {"link_ab:fwd": 5.0}},
                    }
                ],
                "summary": {
                    "total_demand": 5.0,
                    "total_placed": 5.0,
                    "overall_ratio": 1.0,
                    "dropped_flows": 0,
                    "num_flows": 1,
                },
            },
            "results": [],
            "component_scores": {},
            "metadata": {"iterations": 1, "parallelism": 1},
        }
        mock_failure_manager.run_sensitivity_monte_carlo.return_value = mock_raw

        step = Sensitivity(
            source="^A",
            target="^C",
            failure_policy="test_policy",
            iterations=1,
            parallelism=1,
            shortest_path=True,
            seed=42,
            store_failure_patterns=True,
        )
        step.name = "sens_test"
        step.execute(mock_scenario)

        # Verify FailureManager was created correctly
        mock_failure_manager_class.assert_called_once_with(
            network=mock_scenario.network,
            failure_policy_set=mock_scenario.failure_policy_set,
            policy_name="test_policy",
        )

        # Verify run_sensitivity_monte_carlo was called with correct parameters
        _, kwargs = mock_failure_manager.run_sensitivity_monte_carlo.call_args
        assert kwargs["source"] == "^A"
        assert kwargs["target"] == "^C"
        assert kwargs["mode"] == "combine"
        assert kwargs["iterations"] == 1
        assert kwargs["parallelism"] == 1
        assert kwargs["shortest_path"] is True
        assert kwargs["flow_placement"] == FlowPlacement.PROPORTIONAL
        assert kwargs["seed"] == 42
        assert kwargs["store_failure_patterns"] is True

    @patch("ngraph.workflow.sensitivity_step.FailureManager")
    def test_result_structure(self, mock_failure_manager_class, mock_scenario):
        """Test that results are stored with correct structure."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        mock_raw = {
            "baseline": {
                "failure_id": "",
                "failure_state": {"excluded_nodes": [], "excluded_links": []},
                "flows": [],
                "summary": {
                    "total_demand": 5.0,
                    "total_placed": 5.0,
                    "overall_ratio": 1.0,
                    "dropped_flows": 0,
                    "num_flows": 0,
                },
            },
            "results": [
                MagicMock(
                    failure_id="deadbeef",
                    failure_state={
                        "excluded_nodes": [],
                        "excluded_links": ["link1"],
                    },
                    occurrence_count=2,
                    to_dict=lambda: {
                        "failure_id": "deadbeef",
                        "failure_state": {
                            "excluded_nodes": [],
                            "excluded_links": ["link1"],
                        },
                        "occurrence_count": 2,
                        "flows": [
                            {
                                "source": "A",
                                "destination": "C",
                                "priority": 0,
                                "demand": 3.0,
                                "placed": 3.0,
                                "dropped": 0.0,
                                "cost_distribution": {},
                                "data": {"sensitivity": {"link_bc:fwd": 3.0}},
                            }
                        ],
                        "summary": {
                            "total_demand": 3.0,
                            "total_placed": 3.0,
                            "overall_ratio": 1.0,
                            "dropped_flows": 0,
                            "num_flows": 1,
                        },
                    },
                )
            ],
            "component_scores": {
                "^A->^C": {
                    "link_bc:fwd": {
                        "mean": 3.0,
                        "max": 3.0,
                        "min": 3.0,
                        "count": 2.0,
                    }
                }
            },
            "metadata": {
                "iterations": 2,
                "parallelism": 1,
                "unique_patterns": 1,
            },
        }
        mock_failure_manager.run_sensitivity_monte_carlo.return_value = mock_raw

        step = Sensitivity(
            source="^A",
            target="^C",
            iterations=2,
            parallelism=1,
        )
        step.name = "sens_struct"
        step.execute(mock_scenario)

        exported = mock_scenario.results.to_dict()
        step_data = exported["steps"]["sens_struct"]

        # Verify metadata
        assert step_data["metadata"]["iterations"] == 2
        assert step_data["metadata"]["unique_patterns"] == 1

        # Verify data structure
        data = step_data["data"]
        assert "baseline" in data
        assert "flow_results" in data
        assert "component_scores" in data
        assert "context" in data

        # Verify baseline is stored
        assert data["baseline"]["failure_id"] == ""

        # Verify flow_results contains serialized iteration results
        assert len(data["flow_results"]) == 1
        result = data["flow_results"][0]
        assert result["failure_id"] == "deadbeef"
        assert result["occurrence_count"] == 2
        assert result["flows"][0]["data"]["sensitivity"]["link_bc:fwd"] == 3.0

        # Verify component_scores are stored
        scores = data["component_scores"]
        assert "^A->^C" in scores
        assert scores["^A->^C"]["link_bc:fwd"]["mean"] == 3.0

        # Verify context records analysis parameters
        ctx = data["context"]
        assert ctx["source"] == "^A"
        assert ctx["target"] == "^C"
        assert ctx["mode"] == "combine"
        assert ctx["shortest_path"] is False
        assert ctx["flow_placement"] == "PROPORTIONAL"

    @patch("ngraph.workflow.sensitivity_step.FailureManager")
    def test_json_serialization_roundtrip(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test that stored results survive JSON serialization."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        mock_raw = {
            "baseline": None,
            "results": [],
            "component_scores": {
                "S->T": {
                    "edge_a:fwd": {"mean": 1.5, "max": 3.0, "min": 0.0, "count": 4.0}
                }
            },
            "metadata": {"iterations": 0, "parallelism": 1},
        }
        mock_failure_manager.run_sensitivity_monte_carlo.return_value = mock_raw

        step = Sensitivity(source="^S", target="^T", iterations=0, parallelism=1)
        step.name = "json_test"
        step.execute(mock_scenario)

        exported = mock_scenario.results.to_dict()

        # Must be JSON serializable without errors
        json_str = json.dumps(exported)
        restored = json.loads(json_str)

        # Verify round-trip fidelity
        data = restored["steps"]["json_test"]["data"]
        assert data["component_scores"]["S->T"]["edge_a:fwd"]["mean"] == 1.5
        assert data["baseline"] is None
        assert data["flow_results"] == []

    @patch("ngraph.workflow.sensitivity_step.FailureManager")
    def test_no_failure_policy(self, mock_failure_manager_class, mock_scenario):
        """Test running without a failure policy (baseline-only analysis)."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        mock_raw = {
            "baseline": {"failure_id": "", "flows": [], "summary": {}},
            "results": [],
            "component_scores": {},
            "metadata": {"iterations": 0, "parallelism": 1},
        }
        mock_failure_manager.run_sensitivity_monte_carlo.return_value = mock_raw

        step = Sensitivity(
            source="^A",
            target="^C",
            iterations=0,
            parallelism=1,
        )
        step.name = "no_policy"
        step.execute(mock_scenario)

        # Verify FailureManager was created with policy_name=None
        mock_failure_manager_class.assert_called_once_with(
            network=mock_scenario.network,
            failure_policy_set=mock_scenario.failure_policy_set,
            policy_name=None,
        )
