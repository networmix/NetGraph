"""
Test code examples from documentation examples directory.

This module tests examples from:
- docs/examples/basic.md
- docs/examples/clos-fabric.md

These are practical examples showing how to use NetGraph features.
"""

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.algorithms.max_flow import run_sensitivity, saturated_edges
from ngraph.scenario import Scenario


class TestBasicMdExamples:
    """Test examples from docs/examples/basic.md"""

    def test_basic_network_creation(self):
        """Test the basic network topology example."""
        # Create a simple network based on the basic.md example
        scenario_yaml = """
network:
  name: "fundamentals_example"

  # Create individual nodes
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}

  # Create links with different capacities and costs
  links:
    # Parallel edges between A→B
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

    # Parallel edges between B→C
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

    # Alternative path A→D→C
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

        # Create the network
        scenario = Scenario.from_yaml(scenario_yaml)
        network = scenario.network

        # Verify network structure
        assert len(network.nodes) == 4
        assert "A" in network.nodes
        assert "B" in network.nodes
        assert "C" in network.nodes
        assert "D" in network.nodes

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

    def test_results_interpretation(self):
        """Test that the documented behavior matches actual results."""
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

        # Test documented behavior:
        # - "True" MaxFlow: Uses all available paths regardless of cost
        max_flow_all = network.max_flow(source_path="A", sink_path="C")
        flow_all = list(max_flow_all.values())[0]

        # - Shortest Path: Only uses paths with minimum cost
        max_flow_shortest = network.max_flow(
            source_path="A", sink_path="C", shortest_path=True
        )
        flow_shortest = list(max_flow_shortest.values())[0]

        # True max flow should be >= shortest path flow
        assert flow_all >= flow_shortest

        # In this topology:
        # - A→B→C has cost 2 and capacity 3 (sum of parallel edges)
        # - A→D→C has cost 4 and capacity 3
        # So shortest path should only use A→B→C
        assert flow_shortest == 3.0
        # And true max flow should use both paths
        assert flow_all == 6.0


class TestClosFabricMdExamples:
    """Test examples from docs/examples/clos-fabric.md (if any specific examples exist)"""

    def test_clos_fabric_imports(self):
        """Test that we can import everything needed for Clos fabric examples."""
        # This is a basic test to ensure the example dependencies work
        from ngraph.lib.algorithms.base import FlowPlacement
        from ngraph.scenario import Scenario

        # These should import without errors
        assert Scenario is not None
        assert FlowPlacement is not None
        assert hasattr(FlowPlacement, "PROPORTIONAL")
        assert hasattr(FlowPlacement, "EQUAL_BALANCED")

    def test_clos_fabric_hierarchical_blueprint(self):
        """Test the hierarchical blueprint structure from clos-fabric.md"""
        # This matches the actual example shown in clos-fabric.md
        scenario_yaml = """
blueprints:
  brick_2tier:
    groups:
      t1:
        node_count: 8
        name_template: t1-{node_num}
      t2:
        node_count: 8
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
        node_count: 64
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

        # Verify the complex hierarchical structure was created
        # Each 3tier_clos has: 2 * (8 t1 + 8 t2) + 64 spine = 96 nodes
        # Two 3tier_clos instances = 192 nodes total
        assert len(network.nodes) == 192

        # Verify we have nodes with the expected hierarchical naming
        node_names = list(network.nodes.keys())

        # Check for nodes from the first Clos fabric
        my_clos1_t1_nodes = [
            name
            for name in node_names
            if name.startswith("my_clos1/b1/t1/t1-")
            or name.startswith("my_clos1/b2/t1/t1-")
        ]
        my_clos1_spine_nodes = [
            name for name in node_names if name.startswith("my_clos1/spine/t3-")
        ]

        # Check for nodes from the second Clos fabric
        my_clos2_t1_nodes = [
            name
            for name in node_names
            if name.startswith("my_clos2/b1/t1/t1-")
            or name.startswith("my_clos2/b2/t1/t1-")
        ]
        my_clos2_spine_nodes = [
            name for name in node_names if name.startswith("my_clos2/spine/t3-")
        ]

        # Verify node counts match the blueprint structure
        assert len(my_clos1_t1_nodes) == 16  # 8 from b1 + 8 from b2
        assert len(my_clos1_spine_nodes) == 64
        assert len(my_clos2_t1_nodes) == 16  # 8 from b1 + 8 from b2
        assert len(my_clos2_spine_nodes) == 64

        # Verify inter-fabric connectivity exists (64 spine nodes * 4 parallel links = 256 total links)
        inter_fabric_links = [
            link
            for link in network.links.values()
            if (
                "my_clos1/spine/t3-" in link.source
                and "my_clos2/spine/t3-" in link.target
            )
            or (
                "my_clos2/spine/t3-" in link.source
                and "my_clos1/spine/t3-" in link.target
            )
        ]
        # With one_to_one pattern + link_count=4: 64 spine pairs * 4 links each = 256 total links
        assert len(inter_fabric_links) == 256

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
