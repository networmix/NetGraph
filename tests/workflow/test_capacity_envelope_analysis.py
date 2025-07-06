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
            source_path="^A",
            sink_path="^C",
            flow_placement="EQUAL_BALANCED",  # type: ignore[arg-type]
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
                source_path="^A",
                sink_path="^C",
                flow_placement="INVALID",  # type: ignore[arg-type]
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

        # Verify total capacity frequencies were stored
        total_capacity_frequencies = mock_scenario.results.get(
            "test_step", "total_capacity_frequencies"
        )
        assert total_capacity_frequencies is not None
        assert isinstance(total_capacity_frequencies, dict)
        assert (
            sum(total_capacity_frequencies.values()) == 1
        )  # Single iteration for no-failure case

        # Should have exactly one flow key
        assert len(envelopes) == 1

        # Get the envelope data
        envelope_data = list(envelopes.values())[0]
        assert "source" in envelope_data
        assert "sink" in envelope_data
        assert "frequencies" in envelope_data
        assert "total_samples" in envelope_data
        assert envelope_data["total_samples"] == 1  # Single iteration

    def test_run_with_failures(self, mock_scenario):
        """Test run with failure policy."""
        step = CapacityEnvelopeAnalysis(
            source_path="A", sink_path="C", iterations=3, name="test_step"
        )

        step.run(mock_scenario)

        # Verify results were stored
        envelopes = mock_scenario.results.get("test_step", "capacity_envelopes")
        assert envelopes is not None
        assert isinstance(envelopes, dict)

        # Verify total capacity frequencies were stored
        total_capacity_frequencies = mock_scenario.results.get(
            "test_step", "total_capacity_frequencies"
        )
        assert total_capacity_frequencies is not None
        assert isinstance(total_capacity_frequencies, dict)
        assert sum(total_capacity_frequencies.values()) == 3  # 3 iterations

        # Should have exactly one flow key
        assert len(envelopes) == 1

        # Get the envelope data
        envelope_data = list(envelopes.values())[0]
        assert envelope_data["total_samples"] == 3  # Three iterations

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
            assert serial_envelopes[key]["total_samples"] == 4
            assert parallel_envelopes[key]["total_samples"] == 4

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
            assert envelope_data["total_samples"] == 2

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
            assert self_loop_data["frequencies"] == {0.0: 1}

        # Verify some non-zero flows exist (connected components)
        non_zero_flows = [key for key, data in envelopes.items() if data["mean"] > 0]
        assert len(non_zero_flows) > 0

    def test_worker_no_failures(self, simple_network):
        """Test worker function without failures."""
        # Initialize global network for the worker
        import ngraph.workflow.capacity_envelope_analysis as cap_env

        cap_env._shared_network = simple_network

        args = (
            set(),  # excluded_nodes
            set(),  # excluded_links
            "A",
            "C",
            "combine",
            False,
            FlowPlacement.PROPORTIONAL,
            42,  # seed_offset
            "test_step",  # step_name
            0,  # iteration_index
            False,  # is_baseline
        )

        (
            flow_results,
            total_capacity,
            iteration_index,
            is_baseline,
            excluded_nodes,
            excluded_links,
        ) = _worker(args)
        assert isinstance(flow_results, list)
        assert isinstance(total_capacity, (int, float))
        assert len(flow_results) >= 1
        assert iteration_index == 0
        assert is_baseline is False

        # Check result format
        src, dst, flow_val = flow_results[0]
        assert isinstance(src, str)
        assert isinstance(dst, str)
        assert isinstance(flow_val, (int, float))

        # Total capacity should be sum of individual flows
        expected_total = sum(val for _, _, val in flow_results)
        assert total_capacity == expected_total

    def test_worker_with_failures(self, simple_network, simple_failure_policy):
        """Test worker function with failures."""
        # Initialize global network for the worker
        import ngraph.workflow.capacity_envelope_analysis as cap_env

        cap_env._shared_network = simple_network

        # Pre-compute exclusions (simulate what main process does)
        from ngraph.workflow.capacity_envelope_analysis import (
            _compute_failure_exclusions,
        )

        excluded_nodes, excluded_links = _compute_failure_exclusions(
            simple_network, simple_failure_policy, 42
        )

        args = (
            excluded_nodes,
            excluded_links,
            "A",
            "C",
            "combine",
            False,
            FlowPlacement.PROPORTIONAL,
            42,  # seed_offset
            "test_step",  # step_name
            1,  # iteration_index
            False,  # is_baseline
        )

        (
            flow_results,
            total_capacity,
            iteration_index,
            is_baseline,
            returned_excluded_nodes,
            returned_excluded_links,
        ) = _worker(args)
        assert isinstance(flow_results, list)
        assert isinstance(total_capacity, (int, float))
        assert len(flow_results) >= 1
        assert iteration_index == 1
        assert is_baseline is False


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
            assert "frequencies" in envelope_data
            assert "min" in envelope_data
            assert "max" in envelope_data
            assert "mean" in envelope_data
            assert "stdev" in envelope_data
            assert "total_samples" in envelope_data

            # Should have 10 samples
            assert envelope_data["total_samples"] == 10

            # Verify JSON serializable
            json.dumps(envelope_data)

    @patch("ngraph.workflow.capacity_envelope_analysis.ProcessPoolExecutor")
    def test_parallel_execution_path(self, mock_executor_class, mock_scenario):
        """Test that parallel execution path is taken when appropriate."""
        mock_executor = MagicMock()
        mock_executor.__enter__.return_value = mock_executor
        mock_executor.map.return_value = [
            ([("A", "C", 5.0)], 5.0, 0, False, set(), set()),
            ([("A", "C", 4.0)], 4.0, 1, False, set(), {"link1"}),
            ([("A", "C", 6.0)], 6.0, 2, False, set(), {"link2"}),
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
        # Should be called with max_workers and potentially initializer/initargs
        assert mock_executor_class.call_count == 1
        call_args = mock_executor_class.call_args
        assert call_args[1]["max_workers"] == 2
        # May also have initializer and initargs for shared network setup
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

    def test_baseline_validation_error(self):
        """Test that baseline=True requires iterations >= 2."""
        with pytest.raises(ValueError, match="baseline=True requires iterations >= 2"):
            CapacityEnvelopeAnalysis(
                source_path="A",
                sink_path="C",
                baseline=True,
                iterations=1,
            )

    def test_worker_baseline_iteration(self, simple_network, simple_failure_policy):
        """Test that baseline iteration uses empty exclusion sets."""
        # Initialize global network for the worker
        import ngraph.workflow.capacity_envelope_analysis as cap_env

        cap_env._shared_network = simple_network

        # Baseline uses empty exclusion sets (no failures)
        baseline_args = (
            set(),  # excluded_nodes (empty for baseline)
            set(),  # excluded_links (empty for baseline)
            "A",
            "C",
            "combine",
            False,
            FlowPlacement.PROPORTIONAL,
            42,  # seed_offset
            "test_step",  # step_name
            0,  # iteration_index
            True,  # is_baseline
        )

        (
            baseline_results,
            baseline_capacity,
            iteration_index,
            is_baseline,
            excluded_nodes_returned,
            excluded_links_returned,
        ) = _worker(baseline_args)
        assert isinstance(baseline_results, list)
        assert isinstance(baseline_capacity, (int, float))
        assert len(baseline_results) >= 1
        assert iteration_index == 0
        assert is_baseline is True

    def test_baseline_mode_integration(self, mock_scenario):
        """Test baseline mode in full integration."""
        step = CapacityEnvelopeAnalysis(
            source_path="A",
            sink_path="C",
            iterations=3,
            baseline=True,  # First iteration should be baseline
            name="test_step",
        )

        step.run(mock_scenario)

        # Verify results were stored
        envelopes = mock_scenario.results.get("test_step", "capacity_envelopes")
        total_capacity_frequencies = mock_scenario.results.get(
            "test_step", "total_capacity_frequencies"
        )

        assert envelopes is not None
        assert total_capacity_frequencies is not None
        assert sum(total_capacity_frequencies.values()) == 3  # 3 iterations total

        # Extract capacity values to verify baseline behavior
        capacity_values = []
        for capacity, count in total_capacity_frequencies.items():
            capacity_values.extend([capacity] * count)

        # Note: We can't guarantee order in frequency storage, so we just check
        # that we have the expected total number of samples
        assert len(capacity_values) == 3


class TestCaching:
    """Test suite for caching behavior in CapacityEnvelopeAnalysis."""

    def _build_cache_test_network(self) -> Network:
        """Return a trivial A→B→C network with a direct A→C shortcut."""
        net = Network()
        for name in ("A", "B", "C"):
            net.add_node(Node(name))

        net.add_link(Link("A", "B", capacity=10, cost=1))
        net.add_link(Link("B", "C", capacity=10, cost=1))
        net.add_link(Link("A", "C", capacity=5, cost=1))
        return net

    def _build_cache_test_failure_policy(self) -> FailurePolicy:
        """Fail exactly one random link per iteration."""
        rule = FailureRule(entity_scope="link", rule_type="choice", count=1)
        return FailurePolicy(rules=[rule])

    @pytest.mark.parametrize("iterations", [10])
    def test_flow_cache_reuse(self, iterations: int) -> None:
        """The flow cache should contain <= 4 entries for this topology.

        Baseline (no failures) + 3 unique single-link failure sets = 4.
        """
        from ngraph.workflow.capacity_envelope_analysis import _flow_cache

        # Assemble scenario components.
        network = self._build_cache_test_network()
        failure_policy = self._build_cache_test_failure_policy()
        fp_set = FailurePolicySet()
        fp_set.add("default", failure_policy)

        scenario = Scenario(network=network, workflow=[], failure_policy_set=fp_set)

        analysis = CapacityEnvelopeAnalysis(
            name="cache_test",
            source_path="^A$",
            sink_path="^C$",
            mode="combine",
            iterations=iterations,
            baseline=True,
            parallelism=1,  # Serial execution simplifies cache inspection.
        )

        # Start with an empty cache to make the assertion deterministic.
        _flow_cache.clear()

        analysis.run(scenario)

        # 1. Cache growth is bounded.
        assert 1 <= len(_flow_cache) <= 4, "Unexpected cache size"

        # 2. Scenario results contain the expected number of samples.
        total_capacity_frequencies = scenario.results.get(
            "cache_test", "total_capacity_frequencies"
        )
        assert sum(total_capacity_frequencies.values()) == iterations

        # 3. Convert frequencies back to samples for baseline verification
        samples = []
        for capacity, count in total_capacity_frequencies.items():
            samples.extend([capacity] * count)

        # Note: We can't guarantee order in frequency storage, so we just verify
        # that we have the expected number of samples
        assert len(samples) == iterations

    def test_failure_pattern_storage(self) -> None:
        """Test that failure patterns are stored when store_failure_patterns=True."""

        # Assemble scenario components.
        network = self._build_cache_test_network()
        failure_policy = self._build_cache_test_failure_policy()
        fp_set = FailurePolicySet()
        fp_set.add("default", failure_policy)

        scenario = Scenario(network=network, workflow=[], failure_policy_set=fp_set)

        analysis = CapacityEnvelopeAnalysis(
            name="pattern_test",
            source_path="^A$",
            sink_path="^C$",
            mode="combine",
            iterations=5,
            baseline=True,
            parallelism=1,
            store_failure_patterns=True,  # Enable pattern storage
        )

        analysis.run(scenario)

        # Check that failure patterns were stored
        pattern_results = scenario.results.get(
            "pattern_test", "failure_pattern_results"
        )
        assert pattern_results is not None, "Failure pattern results should be stored"

        # Verify pattern results structure
        total_patterns = sum(result["count"] for result in pattern_results.values())
        assert total_patterns == 5, "Should have 5 total pattern instances"

        # Check pattern structure
        for _pattern_key, pattern_data in pattern_results.items():
            assert "excluded_nodes" in pattern_data
            assert "excluded_links" in pattern_data
            assert "capacity_matrix" in pattern_data
            assert "count" in pattern_data
            assert "is_baseline" in pattern_data

            # Verify count is positive
            assert pattern_data["count"] > 0

    def test_failure_pattern_not_stored_by_default(self) -> None:
        """Test that failure patterns are not stored when store_failure_patterns=False."""

        # Assemble scenario components.
        network = self._build_cache_test_network()
        failure_policy = self._build_cache_test_failure_policy()
        fp_set = FailurePolicySet()
        fp_set.add("default", failure_policy)

        scenario = Scenario(network=network, workflow=[], failure_policy_set=fp_set)

        analysis = CapacityEnvelopeAnalysis(
            name="no_pattern_test",
            source_path="^A$",
            sink_path="^C$",
            mode="combine",
            iterations=5,
            baseline=True,
            parallelism=1,
            store_failure_patterns=False,  # Disable pattern storage (default)
        )

        analysis.run(scenario)

        # Check that failure patterns were not stored
        pattern_results = scenario.results.get(
            "no_pattern_test", "failure_pattern_results"
        )
        assert pattern_results is None, (
            "Failure pattern results should not be stored when not requested"
        )

    def test_randomization_across_iterations(self) -> None:
        """Test that failure patterns vary across iterations when using random selection."""

        # Create a larger network to increase randomization possibilities
        network = Network()
        for name in ("A", "B", "C", "D", "E", "F"):
            network.add_node(Node(name))

        # Add more links to increase failure pattern diversity
        links = [
            ("A", "B"),
            ("B", "C"),
            ("C", "D"),
            ("D", "E"),
            ("E", "F"),
            ("A", "F"),
            ("B", "E"),
            ("C", "F"),
            ("A", "D"),
        ]
        for src, dst in links:
            network.add_link(Link(src, dst, capacity=10, cost=1))

        # Use choice rule to select 2 links randomly
        failure_policy = FailurePolicy(
            rules=[FailureRule(entity_scope="link", rule_type="choice", count=2)]
        )
        fp_set = FailurePolicySet()
        fp_set.add("default", failure_policy)

        scenario = Scenario(network=network, workflow=[], failure_policy_set=fp_set)

        analysis = CapacityEnvelopeAnalysis(
            name="randomization_test",
            source_path="^A$",
            sink_path="^F$",
            mode="combine",
            iterations=15,  # More iterations to see variation
            baseline=True,
            parallelism=1,
            store_failure_patterns=True,
            seed=42,  # Fixed seed for reproducible test
        )

        analysis.run(scenario)

        # Check that failure patterns were stored
        pattern_results = scenario.results.get(
            "randomization_test", "failure_pattern_results"
        )
        assert pattern_results is not None, "Failure pattern results should be stored"

        # Verify total patterns
        total_patterns = sum(result["count"] for result in pattern_results.values())
        assert total_patterns == 15, "Should have 15 total pattern instances"

        # Count unique failure sets (excluding baseline)
        unique_failure_sets = set()
        for _pattern_key, pattern_data in pattern_results.items():
            if not pattern_data["is_baseline"]:
                # Create a hashable representation of the failure set
                failure_set = tuple(sorted(pattern_data["excluded_links"]))
                unique_failure_sets.add(failure_set)

        # We should see multiple unique failure patterns
        # With 9 links and choosing 2, there are C(9,2) = 36 possible combinations
        # Even with a small sample, we should see some variation
        assert len(unique_failure_sets) > 1, (
            f"Expected multiple unique patterns, got {len(unique_failure_sets)}"
        )

        # Should see at least 3 different patterns in 14 non-baseline iterations
        assert len(unique_failure_sets) >= 3, (
            f"Expected at least 3 unique patterns, got {len(unique_failure_sets)}"
        )
