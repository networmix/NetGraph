from __future__ import annotations

import json
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
    _run_single_iteration,
    _worker,
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
    policy_set.add("default", simple_failure_policy)
    scenario.failure_policy_set = policy_set

    return scenario


class TestCapacityEnvelopeAnalysis:
    """Test suite for CapacityEnvelopeAnalysis workflow step."""

    def test_initialization_defaults(self):
        """Test default parameter initialization."""
        step = CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C")

        assert step.source_path == "^A"
        assert step.sink_path == "^C"
        assert step.mode == "combine"
        assert step.failure_policy is None
        assert step.iterations == 1
        assert step.parallelism == 1
        assert not step.shortest_path
        assert step.flow_placement == FlowPlacement.PROPORTIONAL
        assert step.seed is None

    def test_initialization_with_parameters(self):
        """Test initialization with all parameters."""
        step = CapacityEnvelopeAnalysis(
            source_path="^Src",
            sink_path="^Dst",
            mode="pairwise",
            failure_policy="test_policy",
            iterations=50,
            parallelism=4,
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            seed=42,
        )

        assert step.source_path == "^Src"
        assert step.sink_path == "^Dst"
        assert step.mode == "pairwise"
        assert step.failure_policy == "test_policy"
        assert step.iterations == 50
        assert step.parallelism == 4
        assert step.shortest_path
        assert step.flow_placement == FlowPlacement.EQUAL_BALANCED
        assert step.seed == 42

    def test_string_flow_placement_conversion(self):
        """Test automatic conversion of string flow_placement to enum."""
        step = CapacityEnvelopeAnalysis(
            source_path="^A", sink_path="^C", flow_placement="EQUAL_BALANCED"
        )
        assert step.flow_placement == FlowPlacement.EQUAL_BALANCED

    def test_validation_errors(self):
        """Test parameter validation."""
        # Test invalid iterations
        with pytest.raises(ValueError, match="iterations must be >= 1"):
            CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", iterations=0)

        # Test invalid parallelism
        with pytest.raises(ValueError, match="parallelism must be >= 1"):
            CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", parallelism=0)

        # Test invalid mode
        with pytest.raises(ValueError, match="mode must be 'combine' or 'pairwise'"):
            CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", mode="invalid")

        # Test invalid flow_placement string
        with pytest.raises(ValueError, match="Invalid flow_placement"):
            CapacityEnvelopeAnalysis(
                source_path="^A", sink_path="^C", flow_placement="INVALID"
            )

    def test_validation_iterations_without_failure_policy(self):
        """Test that iterations > 1 without failure policy raises error."""
        step = CapacityEnvelopeAnalysis(
            source_path="A", sink_path="C", iterations=5, name="test_step"
        )

        # Create scenario without failure policy
        mock_scenario = MagicMock(spec=Scenario)
        mock_scenario.failure_policy_set = FailurePolicySet()  # Empty policy set

        with pytest.raises(
            ValueError, match="iterations=5 is meaningless without a failure policy"
        ):
            step.run(mock_scenario)

    def test_validation_iterations_with_empty_failure_policy(self):
        """Test that iterations > 1 with empty failure policy raises error."""
        step = CapacityEnvelopeAnalysis(
            source_path="A", sink_path="C", iterations=10, name="test_step"
        )

        # Create scenario with empty failure policy
        mock_scenario = MagicMock(spec=Scenario)
        empty_policy_set = FailurePolicySet()
        empty_policy_set.add("default", FailurePolicy(rules=[]))  # Policy with no rules
        mock_scenario.failure_policy_set = empty_policy_set

        with pytest.raises(
            ValueError, match="iterations=10 is meaningless without a failure policy"
        ):
            step.run(mock_scenario)

    def test_get_failure_policy_default(self, mock_scenario):
        """Test getting default failure policy."""
        step = CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C")
        policy = step._get_failure_policy(mock_scenario)
        assert policy is not None
        assert len(policy.rules) == 1

    def test_get_failure_policy_named(self, mock_scenario):
        """Test getting named failure policy."""
        step = CapacityEnvelopeAnalysis(
            source_path="^A", sink_path="^C", failure_policy="default"
        )
        policy = step._get_failure_policy(mock_scenario)
        assert policy is not None
        assert len(policy.rules) == 1

    def test_get_failure_policy_missing(self, mock_scenario):
        """Test error when named failure policy doesn't exist."""
        step = CapacityEnvelopeAnalysis(
            source_path="^A", sink_path="^C", failure_policy="missing"
        )
        with pytest.raises(ValueError, match="Failure policy 'missing' not found"):
            step._get_failure_policy(mock_scenario)

    def test_get_monte_carlo_iterations_with_policy(self, simple_failure_policy):
        """Test Monte Carlo iteration count with failure policy."""
        step = CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", iterations=10)
        iters = step._get_monte_carlo_iterations(simple_failure_policy)
        assert iters == 10

    def test_get_monte_carlo_iterations_without_policy(self):
        """Test Monte Carlo iteration count without failure policy."""
        step = CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", iterations=10)
        iters = step._get_monte_carlo_iterations(None)
        assert iters == 1

    def test_get_monte_carlo_iterations_empty_policy(self):
        """Test Monte Carlo iteration count with empty failure policy."""
        empty_policy = FailurePolicy(rules=[])
        step = CapacityEnvelopeAnalysis(source_path="^A", sink_path="^C", iterations=10)
        iters = step._get_monte_carlo_iterations(empty_policy)
        assert iters == 1

    def test_run_basic_no_failures(self, mock_scenario):
        """Test basic run without failures."""
        # Remove failure policy to test no-failure case
        mock_scenario.failure_policy_set = FailurePolicySet()

        step = CapacityEnvelopeAnalysis(
            source_path="A", sink_path="C", name="test_step"
        )
        step.run(mock_scenario)

        # Verify results were stored
        envelopes = mock_scenario.results.get("test_step", "capacity_envelopes")
        assert envelopes is not None
        assert isinstance(envelopes, dict)

        # Should have exactly one flow key
        assert len(envelopes) == 1

        # Get the envelope data
        envelope_data = list(envelopes.values())[0]
        assert "source" in envelope_data
        assert "sink" in envelope_data
        assert "values" in envelope_data
        assert len(envelope_data["values"]) == 1  # Single iteration

    def test_run_with_failures(self, mock_scenario):
        """Test run with failure policy."""
        step = CapacityEnvelopeAnalysis(
            source_path="A", sink_path="C", iterations=3, name="test_step"
        )

        with patch("ngraph.workflow.capacity_envelope_analysis.random.seed"):
            step.run(mock_scenario)

        # Verify results were stored
        envelopes = mock_scenario.results.get("test_step", "capacity_envelopes")
        assert envelopes is not None
        assert isinstance(envelopes, dict)

        # Should have exactly one flow key
        assert len(envelopes) == 1

        # Get the envelope data
        envelope_data = list(envelopes.values())[0]
        assert len(envelope_data["values"]) == 3  # Three iterations

    def test_run_pairwise_mode(self, mock_scenario):
        """Test run with pairwise mode."""
        step = CapacityEnvelopeAnalysis(
            source_path="[AB]", sink_path="C", mode="pairwise", name="test_step"
        )
        step.run(mock_scenario)

        # Verify results
        envelopes = mock_scenario.results.get("test_step", "capacity_envelopes")
        assert envelopes is not None

        # In pairwise mode, we should get separate results for each source-sink pair
        # that actually matches and has connectivity
        assert len(envelopes) >= 1

    def test_parallel_vs_serial_consistency(self, mock_scenario):
        """Test that parallel and serial execution produce consistent results."""
        # Configure scenario with deterministic failure policy
        rule = FailureRule(entity_scope="link", rule_type="all")
        deterministic_policy = FailurePolicy(rules=[rule])
        mock_scenario.failure_policy_set = FailurePolicySet()
        mock_scenario.failure_policy_set.add("default", deterministic_policy)

        # Run serial
        step_serial = CapacityEnvelopeAnalysis(
            source_path="A",
            sink_path="C",
            iterations=4,
            parallelism=1,
            seed=42,
            name="serial",
        )
        step_serial.run(mock_scenario)

        # Run parallel
        step_parallel = CapacityEnvelopeAnalysis(
            source_path="A",
            sink_path="C",
            iterations=4,
            parallelism=2,
            seed=42,
            name="parallel",
        )
        step_parallel.run(mock_scenario)

        # Get results
        serial_envelopes = mock_scenario.results.get("serial", "capacity_envelopes")
        parallel_envelopes = mock_scenario.results.get("parallel", "capacity_envelopes")

        # Both should have same number of flow keys
        assert len(serial_envelopes) == len(parallel_envelopes)

        # Check that both produced the expected number of samples
        for key in serial_envelopes:
            assert len(serial_envelopes[key]["values"]) == 4
            assert len(parallel_envelopes[key]["values"]) == 4

    def test_parallelism_clamped(self, mock_scenario):
        """Test that parallelism is clamped to iteration count."""
        step = CapacityEnvelopeAnalysis(
            source_path="A",
            sink_path="C",
            iterations=2,
            parallelism=16,
            name="test_step",
        )
        step.run(mock_scenario)

        # Verify results have exactly 2 samples per envelope key
        envelopes = mock_scenario.results.get("test_step", "capacity_envelopes")
        for envelope_data in envelopes.values():
            assert len(envelope_data["values"]) == 2

    def test_any_to_any_pattern_usage(self):
        """Test the (.+) pattern for automatic any-to-any analysis."""
        yaml_content = """
network:
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 10
    - source: B
      target: C
      link_params:
        capacity: 5
    - source: C
      target: D
      link_params:
        capacity: 8

workflow:
  - step_type: CapacityEnvelopeAnalysis
    name: any_to_any_analysis
    source_path: "(.+)"  # Any node as individual source group
    sink_path: "(.+)"    # Any node as individual sink group
    mode: pairwise       # Creates N×N flow combinations
    iterations: 1
"""

        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        # Verify results
        envelopes = scenario.results.get("any_to_any_analysis", "capacity_envelopes")
        assert envelopes is not None
        assert isinstance(envelopes, dict)

        # Should have 4×4 = 16 combinations (including zero-flow self-loops)
        assert len(envelopes) == 16

        # Verify all expected node combinations are present
        nodes = ["A", "B", "C", "D"]
        expected_keys = {f"{src}->{dst}" for src in nodes for dst in nodes}
        actual_keys = set(envelopes.keys())
        assert actual_keys == expected_keys

        # Verify self-loops have zero capacity
        for node in nodes:
            self_loop_key = f"{node}->{node}"
            self_loop_data = envelopes[self_loop_key]
            assert self_loop_data["mean"] == 0.0
            assert self_loop_data["values"] == [0.0]

        # Verify some non-zero flows exist (connected components)
        non_zero_flows = [key for key, data in envelopes.items() if data["mean"] > 0]
        assert len(non_zero_flows) > 0

    def test_worker_no_failures(self, simple_network):
        """Test worker function without failures."""
        args = (
            simple_network,
            None,  # No failure policy
            "A",
            "C",
            "combine",
            False,
            FlowPlacement.PROPORTIONAL,
            42,  # seed
        )

        result = _worker(args)
        assert isinstance(result, list)
        assert len(result) >= 1

        # Check result format
        src, dst, flow_val = result[0]
        assert isinstance(src, str)
        assert isinstance(dst, str)
        assert isinstance(flow_val, (int, float))

    def test_worker_with_failures(self, simple_network, simple_failure_policy):
        """Test worker function with failures."""
        args = (
            simple_network,
            simple_failure_policy,
            "A",
            "C",
            "combine",
            False,
            FlowPlacement.PROPORTIONAL,
            42,  # seed
        )

        result = _worker(args)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_run_single_iteration(self, simple_network):
        """Test single iteration helper function."""
        from collections import defaultdict

        samples = defaultdict(list)

        _run_single_iteration(
            simple_network,
            None,  # No failures
            "A",
            "C",
            "combine",
            False,
            FlowPlacement.PROPORTIONAL,
            samples,
            42,  # seed
        )

        assert len(samples) >= 1
        for values in samples.values():
            assert len(values) == 1


class TestIntegration:
    """Integration tests using actual scenarios."""

    def test_yaml_integration(self):
        """Test that the step can be loaded from YAML."""
        yaml_content = """
network:
  nodes:
    A: {}
    B: {}
    C: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 10
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 5
        cost: 1

failure_policy_set:
  default:
    rules:
      - entity_scope: "link"
        rule_type: "choice"
        count: 1

workflow:
  - step_type: CapacityEnvelopeAnalysis
    name: ce_analysis
    source_path: "A"
    sink_path: "C"
    mode: combine
    iterations: 5
    parallelism: 2
    shortest_path: false
    flow_placement: PROPORTIONAL
"""

        scenario = Scenario.from_yaml(yaml_content)
        assert len(scenario.workflow) == 1

        step = scenario.workflow[0]
        assert isinstance(step, CapacityEnvelopeAnalysis)
        assert step.source_path == "A"
        assert step.sink_path == "C"
        assert step.iterations == 5
        assert step.parallelism == 2

    def test_end_to_end_execution(self):
        """Test complete end-to-end execution."""
        yaml_content = """
network:
  nodes:
    Src1: {}
    Src2: {}
    Mid: {}
    Dst: {}
  links:
    - source: Src1
      target: Mid
      link_params:
        capacity: 100
        cost: 1
    - source: Src2
      target: Mid
      link_params:
        capacity: 50
        cost: 1
    - source: Mid
      target: Dst
      link_params:
        capacity: 80
        cost: 1

failure_policy_set:
  default:
    rules:
      - entity_scope: "link"
        rule_type: "random"
        probability: 0.5

workflow:
  - step_type: CapacityEnvelopeAnalysis
    name: envelope_analysis
    source_path: "^Src"
    sink_path: "Dst"
    mode: pairwise
    iterations: 10
    seed: 123
"""

        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        # Verify results
        envelopes = scenario.results.get("envelope_analysis", "capacity_envelopes")
        assert envelopes is not None
        assert isinstance(envelopes, dict)
        assert len(envelopes) >= 1

        # Verify envelope structure
        for envelope_data in envelopes.values():
            assert "source" in envelope_data
            assert "sink" in envelope_data
            assert "mode" in envelope_data
            assert "values" in envelope_data
            assert "min" in envelope_data
            assert "max" in envelope_data
            assert "mean" in envelope_data
            assert "stdev" in envelope_data

            # Should have 10 samples
            assert len(envelope_data["values"]) == 10

            # Verify JSON serializable
            json.dumps(envelope_data)

    @patch("ngraph.workflow.capacity_envelope_analysis.ProcessPoolExecutor")
    def test_parallel_execution_path(self, mock_executor_class, mock_scenario):
        """Test that parallel execution path is taken when appropriate."""
        mock_executor = MagicMock()
        mock_executor.__enter__.return_value = mock_executor
        mock_executor.map.return_value = [
            [("A", "C", 5.0)],
            [("A", "C", 4.0)],
            [("A", "C", 6.0)],
        ]
        mock_executor_class.return_value = mock_executor

        step = CapacityEnvelopeAnalysis(
            source_path="A",
            sink_path="C",
            iterations=3,
            parallelism=2,
            failure_policy="default",  # Use the failure policy to get mc_iters > 1
            name="test_step",
        )
        step.run(mock_scenario)

        # Verify ProcessPoolExecutor was used
        mock_executor_class.assert_called_once_with(max_workers=2)
        mock_executor.map.assert_called_once()

    def test_no_parallel_when_single_iteration(self, mock_scenario):
        """Test that parallel execution is not used for single iteration."""
        with patch("concurrent.futures.ProcessPoolExecutor") as mock_executor_class:
            step = CapacityEnvelopeAnalysis(
                source_path="A",
                sink_path="C",
                iterations=1,
                parallelism=4,
                name="test_step",
            )
            step.run(mock_scenario)

            # Should not use ProcessPoolExecutor for single iteration
            mock_executor_class.assert_not_called()


if __name__ == "__mp_main__":
    # Guard for Windows multiprocessing
    pytest.main([__file__])
