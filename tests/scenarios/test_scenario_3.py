import pytest
from pathlib import Path

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.scenario import Scenario
from ngraph.failure_policy import FailurePolicy


def test_scenario_3_build_graph_and_capacity_probe() -> None:
    """
    Integration test that verifies we can parse scenario_3.yaml, run the workflow
    (BuildGraph + CapacityProbe), and check results.

    Checks:
      - The expected number of expanded nodes and links (two interconnected 3-tier CLOS fabrics).
      - Presence of key expanded nodes.
      - The traffic demands are empty in this scenario.
      - The failure policy is empty by default.
      - The max flow from my_clos1/b -> my_clos2/b matches the expected capacity.
    """
    # 1) Load the YAML file
    scenario_path = Path(__file__).parent / "scenario_3.yaml"
    yaml_text = scenario_path.read_text()

    # 2) Parse into a Scenario object (this calls blueprint expansion)
    scenario = Scenario.from_yaml(yaml_text)

    # 3) Run the scenario's workflow (BuildGraph then CapacityProbe)
    scenario.run()

    # 4) Retrieve the graph built by BuildGraph
    graph = scenario.results.get("build_graph", "graph")
    assert isinstance(
        graph, StrictMultiDiGraph
    ), "Expected a StrictMultiDiGraph in scenario.results under key ('build_graph', 'graph')."

    # 5) Verify total node count
    #    Each 3-tier CLOS instance has 32 nodes -> 2 instances => 64 total.
    expected_nodes = 64
    actual_nodes = len(graph.nodes)
    assert (
        actual_nodes == expected_nodes
    ), f"Expected {expected_nodes} nodes, found {actual_nodes}"

    # 6) Verify total physical links before direction is applied to Nx
    #    Each 3-tier CLOS has 64 links internally -> 2 instances => 128
    #    Plus 16 links connecting my_clos1/spine -> my_clos2/spine => 144 total physical links
    #    Each link => 2 directed edges => 288 total edges in MultiDiGraph
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
    assert (
        "my_clos1/b1/t1/t1-1" in scenario.network.nodes
    ), "Missing expected node 'my_clos1/b1/t1/t1-1' in expanded blueprint."
    assert (
        "my_clos2/spine/t3-16" in scenario.network.nodes
    ), "Missing expected spine node 'my_clos2/spine/t3-16' in expanded blueprint."

    # 10) Retrieve max flow result from the CapacityProbe step
    #     The probe is configured with source_path="my_clos1/b" and sink_path="my_clos2/b".
    flow_result_label = "max_flow:[my_clos1/b -> my_clos2/b]"
    flow_value = scenario.results.get("capacity_probe", flow_result_label)

    # 11) Assert the expected max flow value
    #     The bottleneck is the 16 spine-to-spine links of capacity=2 => total 32.
    expected_flow = 32.0
    assert flow_value == expected_flow, (
        f"Expected max flow of {expected_flow}, got {flow_value}. "
        "Check blueprint or link capacities if this fails."
    )
