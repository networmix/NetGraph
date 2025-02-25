import pytest
from pathlib import Path

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.scenario import Scenario
from ngraph.failure_policy import FailurePolicy


def test_scenario_3_build_graph() -> None:
    """
    Integration test that verifies we can parse scenario_3.yaml,
    run the BuildGraph step, and produce a valid StrictMultiDiGraph.

    Checks:
      - The expected number of expanded nodes and links (two interconnected 3-tier CLOS fabrics).
      - The presence of key expanded nodes.
      - The traffic demands are empty in this scenario.
      - The failure policy is empty by default.
    """
    # 1) Load the YAML file
    scenario_path = Path(__file__).parent / "scenario_3.yaml"
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

    # 5) Verify total node count
    #    Each 3-tier CLOS instance has 32 nodes (2 sub-bricks of 8 nodes each + 16 spine),
    #    so with 2 instances => 64 nodes total.
    expected_nodes = 64
    actual_nodes = len(graph.nodes)
    assert (
        actual_nodes == expected_nodes
    ), f"Expected {expected_nodes} nodes, found {actual_nodes}"

    # 6) Verify total physical links before direction is applied to Nx
    #    Each 3-tier CLOS has 64 links internally. With 2 instances => 128 links,
    #    plus 16 links connecting my_clos1/spine to my_clos2/spine (one_to_one).
    #    => total physical links = 128 + 16 = 144
    #    => each link becomes 2 directed edges in MultiDiGraph => 288 edges
    expected_links = 144
    expected_nx_edges = expected_links * 2
    actual_edges = len(graph.edges)
    assert (
        actual_edges == expected_nx_edges
    ), f"Expected {expected_nx_edges} directed edges, found {actual_edges}"

    # 7) Verify that there are no traffic demands in this scenario
    assert len(scenario.traffic_demands) == 0, "Expected zero traffic demands."

    # 8) Verify the default (empty) failure policy
    policy: FailurePolicy = scenario.failure_policy
    assert len(policy.rules) == 0, "Expected an empty failure policy."

    # 9) Check presence of a few key expanded nodes
    #    For example: a t1 node in my_clos1/b1 and a spine node in my_clos2.
    assert (
        "my_clos1/b1/t1/t1-1" in scenario.network.nodes
    ), "Missing expected node 'my_clos1/b1/t1/t1-1' in expanded blueprint."
    assert (
        "my_clos2/spine/t3-16" in scenario.network.nodes
    ), "Missing expected spine node 'my_clos2/spine/t3-16' in expanded blueprint."

    print(scenario.results.get("capacity_probe", "max_flow"))
    raise
