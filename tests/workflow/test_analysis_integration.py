"""Tests for workflow analysis components integration."""

import pytest

from ngraph.results.store import Results
from ngraph.scenario import Scenario
from ngraph.workflow.analysis.registry import get_default_registry
from ngraph.workflow.max_flow_step import MaxFlow
from ngraph.workflow.network_stats import NetworkStats


class TestWorkflowAnalysisIntegration:
    """Test integration between workflow steps and analysis components."""

    @pytest.fixture
    def simple_scenario(self):
        """Create a simple scenario for testing."""
        scenario_yaml = """
network:
  name: "test_network"
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}
  links:
    - source: A
      target: B
      link_params: {capacity: 10.0, cost: 1}
    - source: B
      target: C
      link_params: {capacity: 15.0, cost: 1}
    - source: A
      target: D
      link_params: {capacity: 8.0, cost: 2}
    - source: D
      target: C
      link_params: {capacity: 12.0, cost: 1}

failure_policy_set:
  single_link:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: link
            rule_type: choice
            count: 1
  no_failures:
    modes:
      - weight: 1.0
        rules: []

workflow:
  - step_type: NetworkStats
    name: "network_stats"
  - step_type: MaxFlow
    name: "capacity_analysis"
    source_path: "^A$"
    sink_path: "^C$"
    iterations: 1
    baseline: false
    failure_policy: null
"""
        return Scenario.from_yaml(scenario_yaml)

    def test_network_stats_execution(self, simple_scenario):
        """Test NetworkStats workflow step execution."""
        # Execute just the network stats step
        step = NetworkStats(name="test_stats")
        simple_scenario.results = Results()
        step.execute(simple_scenario)

        # Verify results were stored in new schema
        exported = simple_scenario.results.to_dict()
        data = exported["steps"]["test_stats"]["data"]
        assert data.get("node_count") is not None
        assert data.get("link_count") is not None
        assert data["node_count"] > 0
        assert data["link_count"] > 0

    def test_capacity_envelope_execution(self, simple_scenario):
        """Test MaxFlow step execution stores flow_results."""
        # First build the graph
        from ngraph.workflow.build_graph import BuildGraph

        build_step = BuildGraph(name="build")
        simple_scenario.results = Results()
        build_step.execute(simple_scenario)

        # Then run max flow
        envelope_step = MaxFlow(
            name="envelope",
            source_path="^A$",
            sink_path="^C$",
            iterations=1,
            baseline=False,
            failure_policy=None,
        )
        envelope_step.execute(simple_scenario)

        # Verify results
        exported = simple_scenario.results.to_dict()
        data = exported["steps"]["envelope"]["data"]
        assert isinstance(data, dict)
        assert isinstance(data.get("flow_results"), list)

    def test_capacity_envelope_analysis_execution(self, simple_scenario):
        """Test MaxFlow execution with explicit no-failure policy."""
        # Build graph first
        from ngraph.workflow.build_graph import BuildGraph

        build_step = BuildGraph(name="build")
        simple_scenario.results = Results()
        build_step.execute(simple_scenario)

        # Run MaxFlow
        envelope_step = MaxFlow(
            name="envelope",
            source_path="^A$",  # Use regex pattern to match node A exactly
            sink_path="^C$",  # Use regex pattern to match node C exactly
            failure_policy="no_failures",  # Use policy with no failures to avoid exclusions
            iterations=1,  # Single iteration since no failures
            parallelism=1,
            seed=42,
        )
        envelope_step.execute(simple_scenario)

        # Verify results
        exported = simple_scenario.results.to_dict()
        data = exported["steps"]["envelope"]["data"]
        assert data and isinstance(data.get("flow_results"), list)

    def test_workflow_step_metadata_storage(self, simple_scenario):
        """Test that workflow steps store metadata correctly."""
        step = NetworkStats(name="meta_test")
        simple_scenario.results = Results()
        step.execute(simple_scenario)  # Use execute() not run() to test metadata

        # Check metadata was stored
        metadata = simple_scenario.results.get_step_metadata("meta_test")
        assert metadata is not None
        assert metadata.step_type == "NetworkStats"
        # Seed metadata presence (scenario has seed set in helper scenarios)
        assert hasattr(metadata, "scenario_seed")
        assert hasattr(metadata, "step_seed")
        assert hasattr(metadata, "seed_source")
        assert metadata.step_name == "meta_test"
        assert metadata.execution_order >= 0

    def test_analysis_registry_integration(self, simple_scenario):
        """Test analysis registry mapping workflow steps to analyzers."""
        registry = get_default_registry()

        # Test registry contains expected mappings
        step_types = registry.get_all_step_types()
        assert "NetworkStats" in step_types
        assert "MaxFlow" in step_types

    def test_full_workflow_execution(self, simple_scenario):
        """Test execution of complete workflow with multiple steps."""
        # Run the complete workflow
        simple_scenario.run()

        # Verify all workflow steps executed
        exported = simple_scenario.results.to_dict()
        # NetworkStats stores individual metrics
        data = exported["steps"]["network_stats"]["data"]
        assert data.get("node_count") is not None
        assert data.get("link_count") is not None

        # MaxFlow stores data.flow_results
        flow_data = exported["steps"]["capacity_analysis"]["data"]
        assert isinstance(flow_data, dict)
        assert isinstance(flow_data.get("flow_results"), list)
