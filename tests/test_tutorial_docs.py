"""
Test code examples from tutorial documentation.

This module tests examples from:
- docs/getting-started/tutorial.md

These are step-by-step tutorial examples for new users.
"""

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.scenario import Scenario


class TestTutorialMdExamples:
    """Test examples from docs/getting-started/tutorial.md"""

    def test_first_scenario_creation(self):
        """Test the first scenario example from tutorial.md"""
        # This should match the YAML from the tutorial
        yaml_content = """
network:
  name: "tutorial_clos"

  groups:
    servers:
      node_count: 4
      name_template: "s{node_num}"
      attrs:
        hw_type: "server"

    leaf:
      node_count: 4
      name_template: "l{node_num}"
      attrs:
        hw_type: "leaf_switch"

    spine:
      node_count: 2
      name_template: "sp{node_num}"
      attrs:
        hw_type: "spine_switch"

  adjacency:
    # Pod structure
    - source: "s[0-1].*"
      target: "l[0-1].*"
      pattern: "mesh"
      link_params:
        capacity: 10
        cost: 1

    - source: "s[2-3].*"
      target: "l[2-3].*"
      pattern: "mesh"
      link_params:
        capacity: 10
        cost: 1

    # Leaf to spine
    - source: "leaf"
      target: "spine"
      pattern: "mesh"
      link_params:
        capacity: 40
        cost: 1
"""

        scenario = Scenario.from_yaml(yaml_content)
        network = scenario.network

        # Verify the network was created correctly
        assert len(network.nodes) == 10  # 4 servers + 4 leaf + 2 spine

        # Check node naming convention
        server_nodes = [n for n in network.nodes if n.startswith("servers/")]
        leaf_nodes = [n for n in network.nodes if n.startswith("leaf/")]
        spine_nodes = [n for n in network.nodes if n.startswith("spine/")]

        assert len(server_nodes) == 4
        assert len(leaf_nodes) == 4
        assert len(spine_nodes) == 2

    def test_analyzing_maximum_flow_capacity(self):
        """Test the maximum flow analysis examples from tutorial.md"""
        # Use a simpler version for testing
        yaml_content = """
network:
  name: "tutorial_clos"

  groups:
    pod1_servers:
      node_count: 2
      name_template: "pod1_s{node_num}"

    pod2_servers:
      node_count: 2
      name_template: "pod2_s{node_num}"

    pod1_leaf:
      node_count: 2
      name_template: "pod1_l{node_num}"

    pod2_leaf:
      node_count: 2
      name_template: "pod2_l{node_num}"

    pod1_spine:
      node_count: 1
      name_template: "pod1_sp{node_num}"

    pod2_spine:
      node_count: 1
      name_template: "pod2_sp{node_num}"

  adjacency:
    # Pod 1 connections
    - source: "pod1_servers"
      target: "pod1_leaf"
      pattern: "mesh"
      link_params:
        capacity: 10
        cost: 1

    - source: "pod1_leaf"
      target: "pod1_spine"
      pattern: "mesh"
      link_params:
        capacity: 20
        cost: 1

    # Pod 2 connections
    - source: "pod2_servers"
      target: "pod2_leaf"
      pattern: "mesh"
      link_params:
        capacity: 10
        cost: 1

    - source: "pod2_leaf"
      target: "pod2_spine"
      pattern: "mesh"
      link_params:
        capacity: 20
        cost: 1

    # Inter-pod connection
    - source: "pod1_spine"
      target: "pod2_spine"
      pattern: "mesh"
      link_params:
        capacity: 40
        cost: 1
"""

        scenario = Scenario.from_yaml(yaml_content)
        network = scenario.network

        # Test max flow calculations like in the tutorial

        # Calculate MaxFlow from pod1 servers to pod2 servers
        max_flow_result = network.max_flow(
            source_path="pod1_servers",
            sink_path="pod2_servers",
        )
        assert isinstance(max_flow_result, dict)
        assert len(max_flow_result) == 1

        # Calculate MaxFlow from pod1 leaf to pod2 leaf
        max_flow_leaf = network.max_flow(
            source_path="pod1_leaf",
            sink_path="pod2_leaf",
        )
        assert isinstance(max_flow_leaf, dict)

        # Calculate MaxFlow from pod1 spine to pod2 spine
        max_flow_spine = network.max_flow(
            source_path="pod1_spine",
            sink_path="pod2_spine",
        )
        assert isinstance(max_flow_spine, dict)

    def test_understanding_maxflow_results(self):
        """Test the MaxFlow results interpretation section."""
        yaml_content = """
network:
  name: "simple_test"

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
"""

        scenario = Scenario.from_yaml(yaml_content)
        network = scenario.network

        # Test shortest_path parameter
        max_flow_all = network.max_flow(source_path="A", sink_path="C")
        max_flow_shortest = network.max_flow(
            source_path="A", sink_path="C", shortest_path=True
        )

        # In this simple case, they should be the same
        assert max_flow_all == max_flow_shortest

        # Test flow_placement parameter with shortest_path=True
        max_flow_proportional = network.max_flow(
            source_path="A",
            sink_path="C",
            shortest_path=True,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        max_flow_balanced = network.max_flow(
            source_path="A",
            sink_path="C",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        # Both should work without error
        assert isinstance(max_flow_proportional, dict)
        assert isinstance(max_flow_balanced, dict)

    def test_flow_placement_policies(self):
        """Test FlowPlacement policies mentioned in tutorial."""
        # Test that FlowPlacement enum works as expected
        assert hasattr(FlowPlacement, "PROPORTIONAL")
        assert hasattr(FlowPlacement, "EQUAL_BALANCED")

        # Test they can be used in max_flow calls
        yaml_content = """
network:
  name: "parallel_test"

  nodes:
    A: {}
    B: {}

  links:
    - source: A
      target: B
      link_params:
        capacity: 10
        cost: 1
    - source: A
      target: B
      link_params:
        capacity: 20
        cost: 1
"""

        scenario = Scenario.from_yaml(yaml_content)
        network = scenario.network

        # Test both flow placement policies
        result_prop = network.max_flow(
            source_path="A",
            sink_path="B",
            shortest_path=True,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        result_balanced = network.max_flow(
            source_path="A",
            sink_path="B",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        # Both should work and potentially give different results
        assert isinstance(result_prop, dict)
        assert isinstance(result_balanced, dict)

        # Flow values should be positive
        flow_prop = list(result_prop.values())[0]
        flow_balanced = list(result_balanced.values())[0]
        assert flow_prop > 0
        assert flow_balanced > 0

    def test_pseudo_node_concept(self):
        """Test that pseudo-source/sink concept works as described."""
        yaml_content = """
network:
  name: "multi_source_sink"

  groups:
    sources:
      node_count: 3
      name_template: "src{node_num}"

    sinks:
      node_count: 2
      name_template: "sink{node_num}"

    middle:
      node_count: 1
      name_template: "mid{node_num}"

  adjacency:
    - source: "sources"
      target: "middle"
      pattern: "mesh"
      link_params:
        capacity: 10
        cost: 1
    - source: "middle"
      target: "sinks"
      pattern: "mesh"
      link_params:
        capacity: 15
        cost: 1
"""

        scenario = Scenario.from_yaml(yaml_content)
        network = scenario.network

        # Test that max_flow works with multiple sources and sinks
        # (This tests the pseudo-node concept mentioned in tutorial)
        max_flow_result = network.max_flow(source_path="sources", sink_path="sinks")

        assert isinstance(max_flow_result, dict)
        assert len(max_flow_result) == 1

        # Should aggregate flow from all sources to all sinks
        total_flow = list(max_flow_result.values())[0]
        assert total_flow > 0
