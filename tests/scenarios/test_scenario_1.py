import pytest
import networkx as nx
from pathlib import Path

from ngraph.scenario import Scenario


def test_scenario_1_build_graph() -> None:
    """
    Integration test that verifies we can parse scenario_1.yaml,
    run the BuildGraph step, and produce a valid NetworkX MultiDiGraph.
    Also checks traffic demands and failure policy.
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
        graph, nx.MultiDiGraph
    ), "Expected a MultiDiGraph in scenario.results."

    # 5) Check the total number of nodes matches what's listed in scenario_1.yaml
    assert len(graph.nodes) == 19, f"Expected 19 nodes, found {len(graph.nodes)}"

    # 6) Each physical link becomes 2 directed edges in the MultiDiGraph.
    #    The YAML has 28 total link lines (including one duplicate SAT->AUS entry).
    #    So expected edges = 2 * 28 = 56.
    expected_links = 28
    expected_nx_edges = expected_links * 2
    actual_edges = len(graph.edges)
    assert (
        actual_edges == expected_nx_edges
    ), f"Expected {expected_nx_edges} directed edges, found {actual_edges}"

    # 7) Verify the traffic demands
    assert len(scenario.traffic_demands) == 2, "Expected 2 traffic demands."
    demand_map = {(td.source, td.target): td.demand for td in scenario.traffic_demands}
    # scenario_1.yaml has demands: (JFK->LAX=50), (SAN->SEA=30)
    assert demand_map[("JFK", "LAX")] == 50
    assert demand_map[("SAN", "SEA")] == 30

    # 8) Check the failure policy from YAML
    assert scenario.failure_policy.failure_probabilities["node"] == 0.001
    assert scenario.failure_policy.failure_probabilities["link"] == 0.002
