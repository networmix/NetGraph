import pytest
from pathlib import Path

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.scenario import Scenario
from ngraph.failure_policy import FailurePolicy


def test_scenario_3_build_graph_and_capacity_probe() -> None:
    """
    Integration test verifying we can parse scenario_3.yaml, run the workflow
    (BuildGraph + CapacityProbe), and check results.

    Checks:
      1) The correct number of expanded nodes and links (two interconnected 3-tier CLOS fabrics).
      2) Presence of certain expanded node names.
      3) No traffic demands in this scenario.
      4) An empty failure policy by default.
      5) The max flow from my_clos1/b -> my_clos2/b (and reverse) is as expected.
    """
    # 1) Load the YAML file
    scenario_path = Path(__file__).parent / "scenario_3.yaml"
    yaml_text = scenario_path.read_text()

    # 2) Parse into a Scenario object (this also expands blueprints)
    scenario = Scenario.from_yaml(yaml_text)

    # 3) Run the scenario's workflow (BuildGraph then CapacityProbe)
    scenario.run()

    # 4) Retrieve the graph from the BuildGraph step
    graph = scenario.results.get("build_graph", "graph")
    assert isinstance(
        graph, StrictMultiDiGraph
    ), "Expected a StrictMultiDiGraph in scenario.results under key ('build_graph', 'graph')."

    # 5) Verify total node count:
    #    Each 3-tier CLOS instance has 32 nodes -> 2 instances => 64 total.
    expected_nodes = 64
    actual_nodes = len(graph.nodes)
    assert (
        actual_nodes == expected_nodes
    ), f"Expected {expected_nodes} nodes, found {actual_nodes}"

    # 6) Verify total physical links (before direction):
    #    Each 3-tier CLOS has 64 links internally => 2 instances => 128
    #    Plus 16 links connecting my_clos1/spine -> my_clos2/spine => 144 total physical links
    #    Each link => 2 directed edges in the digraph => 288 edges in the final MultiDiGraph
    expected_links = 144
    expected_directed_edges = expected_links * 2
    actual_edges = len(graph.edges)
    assert (
        actual_edges == expected_directed_edges
    ), f"Expected {expected_directed_edges} edges, found {actual_edges}"

    # 7) Verify no traffic demands in this scenario
    assert len(scenario.traffic_demands) == 0, "Expected zero traffic demands."

    # 8) Verify the default (empty) failure policy
    policy: FailurePolicy = scenario.failure_policy
    assert len(policy.rules) == 0, "Expected an empty failure policy."

    # 9) Check presence of some expanded nodes
    assert (
        "my_clos1/b1/t1/t1-1" in scenario.network.nodes
    ), "Missing expected node 'my_clos1/b1/t1/t1-1' in expanded blueprint."
    assert (
        "my_clos2/spine/t3-16" in scenario.network.nodes
    ), "Missing expected node 'my_clos2/spine/t3-16' in expanded blueprint."

    # 10) The capacity probe step computed forward and reverse flows in 'combine' mode
    flow_result_label_fwd = "max_flow:[my_clos1/b.*/t1 -> my_clos2/b.*/t1]"
    flow_result_label_rev = "max_flow:[my_clos2/b.*/t1 -> my_clos1/b.*/t1]"

    # Retrieve the forward flow
    forward_flow = scenario.results.get("capacity_probe", flow_result_label_fwd)
    # Retrieve the reverse flow
    reverse_flow = scenario.results.get("capacity_probe", flow_result_label_rev)

    # 11) Assert the expected flows
    #     The main bottleneck is the 16 spine-to-spine links of capacity=2 => total 32
    #     (same in both forward and reverse).
    expected_flow = 32.0
    assert forward_flow == expected_flow, (
        f"Expected forward max flow of {expected_flow}, got {forward_flow}. "
        "Check blueprint or link capacities if this fails."
    )
    assert reverse_flow == expected_flow, (
        f"Expected reverse max flow of {expected_flow}, got {reverse_flow}. "
        "Check blueprint or link capacities if this fails."
    )
