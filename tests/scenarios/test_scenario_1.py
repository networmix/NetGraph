import pytest
from pathlib import Path

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.scenario import Scenario
from ngraph.failure_policy import FailurePolicy


def test_scenario_1_build_graph() -> None:
    """
    Integration test that verifies we can parse scenario_1.yaml,
    run the BuildGraph step, and produce a valid StrictMultiDiGraph.
    Checks:
      - The expected number of nodes and links are correctly parsed.
      - The traffic demands are loaded.
      - The multi-rule failure policy matches "anySingleLink".
    """

    # 1) Load the YAML file
    scenario_path = Path(__file__).parent / "scenario_1.yaml"
    yaml_text = scenario_path.read_text()

    # 2) Parse into a Scenario object
    scenario = Scenario.from_yaml(yaml_text)

    # 3) Run the scenario's workflow (in this YAML, there's only "BuildGraph")
    scenario.run()

    # 4) Retrieve the graph built by BuildGraph
    graph = scenario.results.get("build_graph", "graph")
    assert isinstance(
        graph, StrictMultiDiGraph
    ), "Expected a StrictMultiDiGraph in scenario.results under key ('build_graph', 'graph')."

    # 5) Check the total number of nodes matches what's listed in scenario_1.yaml
    #    For a 6-node scenario, we expect 6 nodes in the final Nx graph.
    expected_nodes = 6
    actual_nodes = len(graph.nodes)
    assert (
        actual_nodes == expected_nodes
    ), f"Expected {expected_nodes} nodes, found {actual_nodes}"

    # 6) Each physical link from the YAML becomes 2 directed edges in MultiDiGraph.
    #    If the YAML has 10 link definitions, we expect 2 * 10 = 20 directed edges.
    expected_links = 10
    expected_nx_edges = expected_links * 2
    actual_edges = len(graph.edges)
    assert (
        actual_edges == expected_nx_edges
    ), f"Expected {expected_nx_edges} directed edges, found {actual_edges}"

    # 7) Verify the traffic demands.
    expected_demands = 4
    assert (
        len(scenario.traffic_demands) == expected_demands
    ), f"Expected {expected_demands} traffic demands."

    # 8) Check the multi-rule failure policy for "any single link".
    #    This should have exactly 1 rule that picks exactly 1 link from all links.
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
