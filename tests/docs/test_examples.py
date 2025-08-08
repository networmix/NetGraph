"""
Test code examples from documentation examples directory.

This module tests examples from:
- docs/examples/basic.md
- docs/examples/clos-fabric.md

These are practical examples showing how to use NetGraph features.
"""

from ngraph.algorithms.base import FlowPlacement
from ngraph.algorithms.max_flow import run_sensitivity, saturated_edges
from ngraph.scenario import Scenario


class TestBasicMdExamples:
    """Test examples from docs/examples/basic.md"""

    def test_flow_analysis_variants(self):
        """Test different flow analysis approaches from basic.md"""
        scenario_yaml = """
network:
  name: "fundamentals_example"
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 1
        cost: 1
    - source: A
      target: B
      link_params:
        capacity: 2
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 1
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 2
        cost: 1
    - source: A
      target: D
      link_params:
        capacity: 3
        cost: 2
    - source: D
      target: C
      link_params:
        capacity: 3
        cost: 2
"""

        scenario = Scenario.from_yaml(scenario_yaml)
        network = scenario.network

        # Test "true" maximum flow (uses all available paths)
        max_flow_all = network.max_flow(source_path="A", sink_path="C")
        assert isinstance(max_flow_all, dict)
        assert len(max_flow_all) == 1
        flow_value = list(max_flow_all.values())[0]
        # Should be 6.0 (3 from A→B→C path + 3 from A→D→C path)
        assert flow_value == 6.0

        # Test flow along shortest paths only
        max_flow_shortest = network.max_flow(
            source_path="A", sink_path="C", shortest_path=True
        )
        assert isinstance(max_flow_shortest, dict)
        flow_value_shortest = list(max_flow_shortest.values())[0]
        # Should be 3.0 (only uses A→B→C path, ignoring higher-cost A→D→C)
        assert flow_value_shortest == 3.0

        # Test with EQUAL_BALANCED flow placement
        max_flow_balanced = network.max_flow(
            source_path="A",
            sink_path="C",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )
        assert isinstance(max_flow_balanced, dict)
        flow_value_balanced = list(max_flow_balanced.values())[0]
        # Should be limited by equal distribution across parallel paths
        assert flow_value_balanced <= flow_value_shortest

    def test_advanced_sensitivity_analysis(self):
        """Test the advanced sensitivity analysis section from basic.md"""
        scenario_yaml = """
network:
  name: "fundamentals_example"
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 1
        cost: 1
    - source: A
      target: B
      link_params:
        capacity: 2
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 1
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 2
        cost: 1
    - source: A
      target: D
      link_params:
        capacity: 3
        cost: 2
    - source: D
      target: C
      link_params:
        capacity: 3
        cost: 2
"""

        scenario = Scenario.from_yaml(scenario_yaml)
        network = scenario.network

        # Get the underlying graph for low-level analysis
        graph = network.to_strict_multidigraph()

        # Identify bottleneck (saturated) edges
        bottlenecks = saturated_edges(graph, "A", "C")
        assert isinstance(bottlenecks, list)
        assert len(bottlenecks) > 0

        # Perform sensitivity analysis - test increasing capacity by 1 unit
        sensitivity_increase = run_sensitivity(graph, "A", "C", change_amount=1.0)
        assert isinstance(sensitivity_increase, dict)
        assert len(sensitivity_increase) > 0

        # All values should be non-negative (increasing capacity shouldn't decrease flow)
        for flow_change in sensitivity_increase.values():
            assert flow_change >= 0

        # Test sensitivity to capacity decreases
        sensitivity_decrease = run_sensitivity(graph, "A", "C", change_amount=-1.0)
        assert isinstance(sensitivity_decrease, dict)
        assert len(sensitivity_decrease) > 0

        # All values should be non-positive (decreasing capacity shouldn't increase flow)
        for flow_change in sensitivity_decrease.values():
            assert flow_change <= 0


class TestClosFabricMdExamples:
    """Test examples from docs/examples/clos-fabric.md (if any specific examples exist)"""

    def test_clos_fabric_max_flow_analysis(self):
        """Test the max flow analysis example from clos-fabric.md"""
        # Using a simplified version of the hierarchical structure for testing
        scenario_yaml = """
blueprints:
  brick_2tier:
    groups:
      t1:
        node_count: 2
        name_template: t1-{node_num}
      t2:
        node_count: 2
        name_template: t2-{node_num}

    adjacency:
      - source: /t1
        target: /t2
        pattern: mesh
        link_params:
          capacity: 2
          cost: 1

  3tier_clos:
    groups:
      b1:
        use_blueprint: brick_2tier
      b2:
        use_blueprint: brick_2tier
      spine:
        node_count: 4
        name_template: t3-{node_num}

    adjacency:
      - source: b1/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1
      - source: b2/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1

network:
  name: "3tier_clos_network"
  version: 1.0

  groups:
    my_clos1:
      use_blueprint: 3tier_clos

    my_clos2:
      use_blueprint: 3tier_clos

  adjacency:
    - source: my_clos1/spine
      target: my_clos2/spine
      pattern: one_to_one
      link_count: 4
      link_params:
        capacity: 1
        cost: 1
"""

        scenario = Scenario.from_yaml(scenario_yaml)
        network = scenario.network

        # Test the max flow calculation as shown in the documentation
        # Note: using simplified regex patterns for the test
        max_flow_result = network.max_flow(
            source_path=r"my_clos1.*(b[0-9]*)/t1",
            sink_path=r"my_clos2.*(b[0-9]*)/t1",
            mode="combine",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        # Verify the result structure matches documentation expectations
        assert isinstance(max_flow_result, dict)
        assert len(max_flow_result) == 1

        # The key should be a tuple representing the combined source/sink groups
        flow_key = list(max_flow_result.keys())[0]
        assert isinstance(flow_key, tuple)
        assert len(flow_key) == 2

        # Verify flow value is positive (actual value depends on topology)
        flow_value = list(max_flow_result.values())[0]
        assert flow_value > 0
