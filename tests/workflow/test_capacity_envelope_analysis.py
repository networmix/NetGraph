from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.failure_policy import FailurePolicy, FailureRule
from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.network import Link, Network, Node
from ngraph.results import Results
from ngraph.results_artifacts import FailurePolicySet
from ngraph.scenario import Scenario
from ngraph.workflow.capacity_envelope_analysis import (
    CapacityEnvelopeAnalysis,
)


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
    return FailurePolicy(rules=[rule])


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


class TestCapacityEnvelopeAnalysis:
    """Test suite for CapacityEnvelopeAnalysis workflow step."""

    def test_initialization_defaults(self):
        """Test CapacityEnvelopeAnalysis initialization with defaults."""
        step = CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C")

        assert step.source_path == "^A"
        assert step.sink_path == "^C"
        assert step.mode == "combine"
        assert step.failure_policy is None
        assert step.iterations == 1
        assert step.parallelism == 1
        assert step.shortest_path is False
        assert step.flow_placement == FlowPlacement.PROPORTIONAL
        assert step.baseline is False
        assert step.seed is None
        assert step.store_failure_patterns is False

    def test_initialization_custom_values(self):
        """Test CapacityEnvelopeAnalysis initialization with custom values."""
        step = CapacityEnvelopeAnalysis(
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

    def test_validation_errors(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="iterations must be >= 1"):
            CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", iterations=0)

        with pytest.raises(ValueError, match="parallelism must be >= 1"):
            CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", parallelism=0)

        with pytest.raises(ValueError, match="mode must be 'combine' or 'pairwise'"):
            CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", mode="invalid")

        with pytest.raises(ValueError, match="baseline=True requires iterations >= 2"):
            CapacityEnvelopeAnalysis(
                source_path="^A", sink_path="^C", baseline=True, iterations=1
            )

    def test_flow_placement_enum_usage(self):
        """Test that FlowPlacement enum is used correctly."""
        step = CapacityEnvelopeAnalysis(
            source_path="^A", sink_path="^C", flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert step.flow_placement == FlowPlacement.PROPORTIONAL

    @patch("ngraph.workflow.capacity_envelope_analysis.FailureManager")
    def test_run_with_mock_failure_manager(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test running the workflow step with mocked FailureManager."""
        # Setup mock FailureManager
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Mock the convenience method results
        mock_envelope_results = MagicMock()
        mock_envelope_results.envelopes = {"A->C": MagicMock()}
        mock_envelope_results.envelopes["A->C"].to_dict.return_value = {
            "min": 5.0,
            "max": 5.0,
            "mean": 5.0,
            "frequencies": {"5.0": 1},
        }
        mock_envelope_results.failure_patterns = {}
        mock_failure_manager.run_max_flow_monte_carlo.return_value = (
            mock_envelope_results
        )

        # Create and run the step
        step = CapacityEnvelopeAnalysis(
            source_path="^A", sink_path="^C", failure_policy="test_policy", iterations=1
        )
        step.run(mock_scenario)

        # Verify FailureManager was created correctly
        mock_failure_manager_class.assert_called_once_with(
            network=mock_scenario.network,
            failure_policy_set=mock_scenario.failure_policy_set,
            policy_name="test_policy",
        )

        # Verify convenience method was called with correct parameters
        mock_failure_manager.run_max_flow_monte_carlo.assert_called_once_with(
            source_path="^A",
            sink_path="^C",
            mode="combine",
            iterations=1,
            parallelism=1,
            shortest_path=False,
            flow_placement=step.flow_placement,
            baseline=False,
            seed=None,
            store_failure_patterns=False,
        )

        # Verify results were processed (just check that the step ran without error)
        # The analysis and results storage happened as evidenced by the log messages

    @patch("ngraph.workflow.capacity_envelope_analysis.FailureManager")
    def test_run_with_failure_patterns(self, mock_failure_manager_class, mock_scenario):
        """Test running with failure pattern storage enabled."""
        # Setup mock FailureManager
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Mock results with failure patterns
        mock_envelope_results = MagicMock()
        mock_envelope_results.envelopes = {"A->C": MagicMock()}
        mock_envelope_results.envelopes["A->C"].to_dict.return_value = {
            "min": 4.0,
            "max": 5.0,
            "mean": 4.5,
            "frequencies": {"4.0": 1, "5.0": 1},
        }

        # Mock failure patterns
        mock_pattern = MagicMock()
        mock_pattern.to_dict.return_value = {
            "excluded_nodes": ["node1"],
            "excluded_links": [],
            "capacity_matrix": {"A->C": 4.0},
            "count": 1,
            "is_baseline": False,
        }
        mock_envelope_results.failure_patterns = {"pattern_key": mock_pattern}

        mock_failure_manager.run_max_flow_monte_carlo.return_value = (
            mock_envelope_results
        )

        # Create and run the step with failure pattern storage
        step = CapacityEnvelopeAnalysis(
            source_path="^A",
            sink_path="^C",
            iterations=2,
            store_failure_patterns=True,
        )
        step.run(mock_scenario)

        # Verify convenience method was called with store_failure_patterns=True
        mock_failure_manager.run_max_flow_monte_carlo.assert_called_once_with(
            source_path="^A",
            sink_path="^C",
            mode="combine",
            iterations=2,
            parallelism=1,
            shortest_path=False,
            flow_placement=step.flow_placement,
            baseline=False,
            seed=None,
            store_failure_patterns=True,
        )

        # The test verifies that the FailureManager integration works properly

    def test_capacity_envelope_analysis_with_failures_mocked(self):
        """Test capacity envelope analysis with mocked FailureManager."""
        step = CapacityEnvelopeAnalysis(
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

        # Mock the convenience method call results
        mock_envelope_results = MagicMock()
        mock_envelope_results.envelopes = {"A->C": MagicMock()}
        mock_envelope_results.envelopes["A->C"].to_dict.return_value = {
            "min": 3.0,
            "max": 5.0,
            "mean": 4.25,
            "frequencies": {"3.0": 1, "4.0": 1, "5.0": 2},
        }
        mock_envelope_results.failure_patterns = {}

        # Mock the FailureManager class and its convenience method
        with patch(
            "ngraph.workflow.capacity_envelope_analysis.FailureManager"
        ) as mock_fm_class:
            mock_fm_instance = mock_fm_class.return_value
            mock_fm_instance.run_max_flow_monte_carlo.return_value = (
                mock_envelope_results
            )

            step.run(scenario)

        # Check that results were stored
        envelopes = scenario.results.get(step.name, "capacity_envelopes")
        assert envelopes is not None
        assert "A->C" in envelopes
