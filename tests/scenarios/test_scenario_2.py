import pytest
from pathlib import Path

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.scenario import Scenario
from ngraph.failure_policy import FailurePolicy


def test_scenario_2_build_graph() -> None:
    """
    Integration test that verifies we can parse scenario_2.yaml,
    run the BuildGraph step, and produce a valid StrictMultiDiGraph.

    Checks:
      - The expected number of expanded nodes and links (including blueprint subgroups).
      - The presence of key expanded nodes (e.g., overridden spine nodes).
      - The traffic demands are loaded.
      - The multi-rule failure policy matches "anySingleLink".
    """
    # 1) Load the YAML file
    scenario_path = Path(__file__).parent / "scenario_2.yaml"
    yaml_text = scenario_path.read_text()

    # 2) Parse into a Scenario object (this calls blueprint expansion)
    scenario = Scenario.from_yaml(yaml_text)

    # 3) Run the scenario's workflow (in this YAML, there's only "BuildGraph")
    scenario.run()

    # 4) Retrieve the graph built by BuildGraph
    graph = scenario.results.get("build_graph", "graph")
    assert isinstance(
        graph, StrictMultiDiGraph
    ), "Expected a StrictMultiDiGraph in scenario.results under key ('build_graph', 'graph')."

    # 5) Verify total node count after blueprint expansion
    #    city_cloud blueprint: (4 leaves + 6 spines + 4 edge_nodes) = 14
    #    single_node blueprint: 1 node
    #    plus 4 standalone global nodes (DEN, DFW, JFK, DCA)
    #    => 14 + 1 + 4 = 19 total
    expected_nodes = 19
    actual_nodes = len(graph.nodes)
    assert (
        actual_nodes == expected_nodes
    ), f"Expected {expected_nodes} nodes, found {actual_nodes}"

    # 6) Verify total physical links before direction is applied to Nx
    #    - clos_2tier adjacency: 4 leaf * 6 spine = 24
    #    - city_cloud adjacency: clos_instance/leaf(4) -> edge_nodes(4) => 16
    #      => total within blueprint = 24 + 16 = 40
    #    - top-level adjacency:
    #         SFO(1) -> DEN(1) => 1
    #         SFO(1) -> DFW(1) => 1
    #         SEA/edge_nodes(4) -> DEN(1) => 4
    #         SEA/edge_nodes(4) -> DFW(1) => 4
    #      => 1 + 1 + 4 + 4 = 10
    #    - sum so far = 40 + 10 = 50
    #    - plus 6 direct link definitions => total physical links = 56
    #    - each link becomes 2 directed edges in MultiDiGraph => 112 edges
    expected_links = 56
    expected_nx_edges = expected_links * 2
    actual_edges = len(graph.edges)
    assert (
        actual_edges == expected_nx_edges
    ), f"Expected {expected_nx_edges} directed edges, found {actual_edges}"

    # 7) Verify the traffic demands (should have 4)
    expected_demands = 4
    assert (
        len(scenario.traffic_demands) == expected_demands
    ), f"Expected {expected_demands} traffic demands."

    # 8) Check the single-rule failure policy "anySingleLink"
    policy: FailurePolicy = scenario.failure_policy
    assert len(policy.rules) == 1, "Should only have 1 rule for 'anySingleLink'."

    rule = policy.rules[0]
    assert rule.entity_scope == "link"
    assert rule.logic == "any"
    assert rule.rule_type == "choice"
    assert rule.count == 1
    assert policy.attrs.get("name") == "anySingleLink"
    assert (
        policy.attrs.get("description")
        == "Evaluate traffic routing under any single link failure."
    )

    # 9) Check presence of key expanded nodes
    #    For example: the overridden spine node "myspine-6" under "SEA/clos_instance/spine"
    #    and the single node blueprint "SFO/single/single-1".
    assert (
        "SEA/clos_instance/spine/myspine-6" in scenario.network.nodes
    ), "Missing expected overridden spine node (myspine-6) in expanded blueprint."
    assert (
        "SFO/single/single-1" in scenario.network.nodes
    ), "Missing expected single-node blueprint expansion under SFO."
