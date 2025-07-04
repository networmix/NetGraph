from unittest.mock import MagicMock

import pytest

from ngraph.network import Link, Network, Node
from ngraph.workflow.network_stats import NetworkStats


@pytest.fixture
def mock_scenario():
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()

    scenario.network.add_node(Node("A"))
    scenario.network.add_node(Node("B"))
    scenario.network.add_node(Node("C"))

    scenario.network.add_link(Link("A", "B", capacity=10))
    scenario.network.add_link(Link("A", "C", capacity=5))
    scenario.network.add_link(Link("C", "A", capacity=7))
    return scenario


def test_network_stats_collects_statistics(mock_scenario):
    step = NetworkStats(name="stats")

    step.run(mock_scenario)

    assert mock_scenario.results.put.call_count == 4

    keys = {call.args[1] for call in mock_scenario.results.put.call_args_list}
    assert keys == {"link_capacity", "node_capacity", "node_degree", "per_node"}

    link_data = next(
        call.args[2]
        for call in mock_scenario.results.put.call_args_list
        if call.args[1] == "link_capacity"
    )
    assert link_data["values"] == [5, 7, 10]
    assert link_data["min"] == 5
    assert link_data["max"] == 10
    assert link_data["median"] == 7
    assert link_data["mean"] == pytest.approx((5 + 7 + 10) / 3)

    per_node = next(
        call.args[2]
        for call in mock_scenario.results.put.call_args_list
        if call.args[1] == "per_node"
    )
    assert set(per_node.keys()) == {"A", "B", "C"}
