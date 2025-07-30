"""Test scenario seeding functionality."""

from typing import TYPE_CHECKING

import pytest

from ngraph.failure_policy import FailurePolicy, FailureRule
from ngraph.network import Network, Node
from ngraph.scenario import Scenario
from ngraph.workflow.transform.enable_nodes import EnableNodesTransform

if TYPE_CHECKING:
    pass


class TestScenarioSeeding:
    """Test seeding functionality in scenarios."""

    @pytest.fixture
    def basic_scenario_yaml(self):
        """A basic scenario with seeding enabled."""
        return """
seed: 42

network:
  nodes:
    node_a:
      attrs: {type: "router"}
    node_b:
      attrs: {type: "router"}
    node_c:
      attrs: {type: "router"}
      disabled: true
    node_d:
      attrs: {type: "router"}
      disabled: true
    node_e:
      attrs: {type: "router"}
      disabled: true

failure_policy_set:
  default:
    rules:
      - entity_scope: node
        rule_type: choice
        count: 1

workflow:
  - step_type: EnableNodes
    path: "^node_[de]$"
    count: 1
    order: "random"
"""

    def test_scenario_has_seed_manager(self, basic_scenario_yaml):
        """Test that scenario creates a seed manager."""
        scenario = Scenario.from_yaml(basic_scenario_yaml)
        assert scenario.seed_manager is not None
        assert scenario.seed_manager.master_seed == 42

    def test_scenario_without_seed(self):
        """Test that scenario without seed still works."""
        yaml_no_seed = """
network:
  nodes:
    node_a:
      attrs: {type: "router"}
"""
        scenario = Scenario.from_yaml(yaml_no_seed)
        assert scenario.seed_manager is not None
        assert scenario.seed_manager.master_seed is None

    def test_failure_policy_seeding(self, basic_scenario_yaml):
        """Test that failure policy receives seed from scenario."""
        scenario = Scenario.from_yaml(basic_scenario_yaml)

        # The failure policy should have been seeded
        policy = scenario.failure_policy_set.get_policy("default")
        assert policy is not None
        assert policy.seed is not None

    def test_workflow_step_seeding(self, basic_scenario_yaml):
        """Test that workflow steps receive derived seeds."""
        scenario = Scenario.from_yaml(basic_scenario_yaml)

        # Get the EnableNodes step wrapper and access the wrapped transform
        enable_step_wrapper = scenario.workflow[0]
        # Access the wrapped transform using getattr for type safety
        enable_step = getattr(enable_step_wrapper, "_transform", None)
        assert enable_step is not None
        assert isinstance(enable_step, EnableNodesTransform)

        # Check that the transform received a seed
        assert enable_step.seed is not None

    def test_consistent_seeded_results(self):
        """Test that seeded operations produce consistent results."""
        yaml_template = """
seed: 42
network:
  nodes:
    node_a: {disabled: true}
    node_b: {disabled: true}
    node_c: {disabled: true}
    node_d: {disabled: true}
    node_e: {disabled: true}
workflow:
  - step_type: EnableNodes
    path: "^node_"
    count: 2
    order: "random"
"""

        # Run the same scenario multiple times
        results = []
        for _ in range(5):
            scenario = Scenario.from_yaml(yaml_template)
            scenario.run()

            enabled = sorted(
                [n.name for n in scenario.network.nodes.values() if not n.disabled]
            )
            results.append(enabled)

        # All results should be identical (deterministic)
        assert all(result == results[0] for result in results)

    def test_failure_policy_consistent_results(self):
        """Test that seeded failure policies produce consistent results."""
        # Create a simple network for testing
        network = Network()
        for i in range(10):
            network.add_node(Node(f"n{i}", attrs={"type": "router"}))

        # Create policy with seed
        rule = FailureRule(entity_scope="node", rule_type="choice", count=3)
        policy = FailurePolicy(rules=[rule], seed=42)

        nodes = {n.name: n.attrs for n in network.nodes.values()}

        # Generate multiple results
        results = []
        for _ in range(10):
            failed = policy.apply_failures(nodes, {})
            results.append(sorted(failed))

        # All results should be identical (deterministic)
        assert all(result == results[0] for result in results)

    def test_failure_policy_different_seeds_different_results(self):
        """Test that different seeds can produce different results."""
        # Create a simple network for testing
        network = Network()
        for i in range(20):  # More nodes increase probability of difference
            network.add_node(Node(f"n{i:02d}", attrs={"type": "router"}))

        # Create policies with different seeds
        rule = FailureRule(
            entity_scope="node",
            rule_type="choice",
            count=5,  # More selections
        )

        # Test multiple seed pairs to increase chance of finding difference
        seed_pairs = [(42, 123), (100, 200), (1, 999), (777, 888)]
        found_difference = False

        nodes = {n.name: n.attrs for n in network.nodes.values()}

        for seed1, seed2 in seed_pairs:
            policy1 = FailurePolicy(rules=[rule], seed=seed1)
            policy2 = FailurePolicy(rules=[rule], seed=seed2)

            failed1 = policy1.apply_failures(nodes, {})
            failed2 = policy2.apply_failures(nodes, {})

            if sorted(failed1) != sorted(failed2):
                found_difference = True
                break

        # At least one seed pair should produce different results
        assert found_difference, (
            "No seed pairs produced different results - seeding may not be working properly"
        )

    def test_scenario_different_seeds_different_results(self):
        """Test that scenarios with different seeds produce different results."""
        yaml_seed1 = """
seed: 42
network:
  nodes:
    node_a: {disabled: true}
    node_b: {disabled: true}
    node_c: {disabled: true}
    node_d: {disabled: true}
    node_e: {disabled: true}
workflow:
  - step_type: EnableNodes
    path: "^node_"
    count: 2
    order: "random"
"""

        yaml_seed2 = """
seed: 123
network:
  nodes:
    node_a: {disabled: true}
    node_b: {disabled: true}
    node_c: {disabled: true}
    node_d: {disabled: true}
    node_e: {disabled: true}
workflow:
  - step_type: EnableNodes
    path: "^node_"
    count: 2
    order: "random"
"""

        # Run scenarios with different seeds
        scenario1 = Scenario.from_yaml(yaml_seed1)
        scenario2 = Scenario.from_yaml(yaml_seed2)

        scenario1.run()
        scenario2.run()

        enabled1 = sorted(
            [n.name for n in scenario1.network.nodes.values() if not n.disabled]
        )
        enabled2 = sorted(
            [n.name for n in scenario2.network.nodes.values() if not n.disabled]
        )

        # Should have exactly 2 nodes enabled in each case
        assert len(enabled1) == 2, (
            f"Scenario 1 enabled {len(enabled1)} nodes instead of 2: {enabled1}"
        )
        assert len(enabled2) == 2, (
            f"Scenario 2 enabled {len(enabled2)} nodes instead of 2: {enabled2}"
        )

        # Results should be different (with high probability)
        assert enabled1 != enabled2, (
            f"Different seeds produced identical results: {enabled1}"
        )

    def test_explicit_step_seed_overrides_derived(self):
        """Test that explicit step seeds override scenario-derived seeds."""
        yaml_with_explicit = """
seed: 42
network:
  nodes:
    node_a: {disabled: true}
    node_b: {disabled: true}
workflow:
  - step_type: EnableNodes
    path: "^node_"
    count: 1
    order: "random"
    seed: 999  # Explicit seed
"""

        scenario = Scenario.from_yaml(yaml_with_explicit)
        enable_step_wrapper = scenario.workflow[0]
        enable_step = getattr(enable_step_wrapper, "_transform", None)

        # Cast to correct type and check explicit seed
        assert enable_step is not None
        assert isinstance(enable_step, EnableNodesTransform)
        assert enable_step.seed == 999

    def test_unseeded_scenario_still_works(self):
        """Test that scenarios without seeds still work (non-deterministic)."""
        yaml_no_seed = """
network:
  nodes:
    node_a: {disabled: true}
    node_b: {disabled: true}
    node_c: {disabled: true}
workflow:
  - step_type: EnableNodes
    path: "^node_"
    count: 1
    order: "random"
"""

        scenario = Scenario.from_yaml(yaml_no_seed)

        # Should have no seed in the workflow step
        enable_step_wrapper = scenario.workflow[0]
        enable_step = getattr(enable_step_wrapper, "_transform", None)
        assert enable_step is not None
        assert isinstance(enable_step, EnableNodesTransform)
        assert enable_step.seed is None

        # Should still run successfully
        scenario.run()

        # Exactly one node should be enabled
        enabled_count = sum(
            1 for n in scenario.network.nodes.values() if not n.disabled
        )
        enabled_nodes = [
            n.name for n in scenario.network.nodes.values() if not n.disabled
        ]
        assert enabled_count == 1, (
            f"Expected 1 node enabled, got {enabled_count}: {enabled_nodes}"
        )
