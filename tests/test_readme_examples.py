"""Tests for examples from README.md to ensure they work correctly."""

import pytest


def test_clos_fabric_readme_example():
    """
    Test the main Clos fabric example from README.md.

    This verifies that the complex scenario with hierarchical blueprints
    and max flow calculation works as documented in the README.
    """
    from ngraph.lib.flow_policy import FlowPlacement
    from ngraph.scenario import Scenario

    # Define two 3-tier Clos networks with inter-fabric connectivity
    # This is the exact YAML from the README
    clos_scenario_yaml = """
seed: 42  # Ensures reproducible results across runs

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

    # Test scenario parsing and network creation
    scenario = Scenario.from_yaml(clos_scenario_yaml)
    network = scenario.network

    # Verify the network structure matches expectations
    assert len(network.nodes) == 192, f"Expected 192 nodes, got {len(network.nodes)}"
    assert len(network.links) == 768, f"Expected 768 links, got {len(network.links)}"

    # Test the max flow calculation as shown in README
    max_flow = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        flow_placement=FlowPlacement.EQUAL_BALANCED,
    )

    # Verify the expected result from README comment
    expected_result = {("b1|b2", "b1|b2"): 256.0}
    assert max_flow == expected_result, f"Expected {expected_result}, got {max_flow}"


def test_readme_example_network_properties():
    """
    Test additional properties of the README Clos fabric example
    to ensure the network is built correctly.
    """
    from ngraph.scenario import Scenario

    clos_scenario_yaml = """
seed: 42

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

    scenario = Scenario.from_yaml(clos_scenario_yaml)
    network = scenario.network

    # Test seed reproducibility
    scenario2 = Scenario.from_yaml(clos_scenario_yaml)
    network2 = scenario2.network

    # With the same seed, networks should be identical
    assert len(network.nodes) == len(network2.nodes)
    assert len(network.links) == len(network2.links)

    # Check that we have the expected node groups
    clos1_nodes = [n for n in network.nodes if n.startswith("my_clos1")]
    clos2_nodes = [n for n in network.nodes if n.startswith("my_clos2")]

    assert len(clos1_nodes) == 96, f"Expected 96 my_clos1 nodes, got {len(clos1_nodes)}"
    assert len(clos2_nodes) == 96, f"Expected 96 my_clos2 nodes, got {len(clos2_nodes)}"

    # Check that inter-fabric links exist
    inter_fabric_links = [
        link
        for link in network.links.values()
        if (link.source.startswith("my_clos1") and link.target.startswith("my_clos2"))
        or (link.source.startswith("my_clos2") and link.target.startswith("my_clos1"))
    ]

    # Should have 4 bidirectional links between each pair of 64 spine nodes (4 * 64 * 2 = 512 links)
    # But since link_count applies to each spine node, we get 256 links total
    assert len(inter_fabric_links) == 256, (
        f"Expected 256 inter-fabric links, got {len(inter_fabric_links)}"
    )


@pytest.mark.slow
def test_readme_example_with_workflow():
    """
    Test the README example integrated with a simple workflow to ensure
    the scenario framework works end-to-end.
    """
    from ngraph.scenario import Scenario

    # Extend the README example with a simple workflow
    scenario_with_workflow_yaml = """
seed: 42

blueprints:
  simple_clos:
    groups:
      leaf:
        node_count: 4
        name_template: leaf-{node_num}
      spine:
        node_count: 2
        name_template: spine-{node_num}
    adjacency:
      - source: /leaf
        target: /spine
        pattern: mesh
        link_params:
          capacity: 10
          cost: 1

network:
  groups:
    fabric:
      use_blueprint: simple_clos

workflow:
  - step_type: BuildGraph
    name: build_topology
"""

    scenario = Scenario.from_yaml(scenario_with_workflow_yaml)

    # Run the workflow
    scenario.run()

    # Verify results
    assert scenario.results is not None

    # Check the built graph
    graph = scenario.results.get("build_topology", "graph")
    assert graph is not None
    assert len(graph.nodes) == 6  # 4 leaf + 2 spine
    assert len(graph.edges) > 0  # Should have mesh connectivity
