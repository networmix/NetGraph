import pytest
from unittest.mock import MagicMock

from ngraph.network import Network, Node, Link
from ngraph.workflow.capacity_probe import CapacityProbe
from ngraph.lib.algorithms.base import FlowPlacement


@pytest.fixture
def mock_scenario():
    """
    Provides a mock Scenario object with a simple Network and a mocked results.
    """
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()
    return scenario


def test_capacity_probe_simple_flow(mock_scenario):
    """
    Tests a simple A->B network to confirm CapacityProbe calculates the correct flow
    and stores it in scenario.results with the expected label.
    """
    # Create a 2-node network (A->B capacity=5)
    mock_scenario.network.add_node(Node("A"))
    mock_scenario.network.add_node(Node("B"))
    mock_scenario.network.add_link(Link("A", "B", capacity=5))

    # Instantiate the step
    step = CapacityProbe(
        name="MyCapacityProbe",
        source_path="A",
        sink_path="B",
        shortest_path=False,
        flow_placement=FlowPlacement.PROPORTIONAL,
    )

    step.run(mock_scenario)

    # The flow from A to B should be 5
    expected_flow = 5.0

    # Validate scenario.results.put call
    # The step uses the label: "max_flow:[A -> B]"
    mock_scenario.results.put.assert_called_once()
    call_args = mock_scenario.results.put.call_args[0]
    # call_args format => (step_name, result_label, flow_value)
    assert call_args[0] == "MyCapacityProbe"
    assert call_args[1] == "max_flow:[A -> B]"
    assert call_args[2] == expected_flow


def test_capacity_probe_no_source(mock_scenario):
    """
    Tests that CapacityProbe raises ValueError if no source nodes match.
    """
    # The network only has node "X"; no node matches "A".
    mock_scenario.network.add_node(Node("X"))
    mock_scenario.network.add_node(Node("B"))
    mock_scenario.network.add_link(Link("X", "B", capacity=10))

    step = CapacityProbe(name="MyCapacityProbe", source_path="A", sink_path="B")

    with pytest.raises(ValueError, match="No source nodes found matching path 'A'"):
        step.run(mock_scenario)


def test_capacity_probe_no_sink(mock_scenario):
    """
    Tests that CapacityProbe raises ValueError if no sink nodes match.
    """
    # The network only has node "A"; no node matches "B".
    mock_scenario.network.add_node(Node("A"))
    mock_scenario.network.add_link(
        Link("A", "A", capacity=10)
    )  # silly link for completeness

    step = CapacityProbe(name="MyCapacityProbe", source_path="A", sink_path="B")

    with pytest.raises(ValueError, match="No sink nodes found matching path 'B'"):
        step.run(mock_scenario)


def test_capacity_probe_parallel_paths(mock_scenario):
    """
    Tests a scenario with two parallel paths from A->C: A->B->C and A->D->C,
    each with capacity=5, ensuring the total flow is 10.
    """
    # Create a 4-node network
    mock_scenario.network.add_node(Node("A"))
    mock_scenario.network.add_node(Node("B"))
    mock_scenario.network.add_node(Node("C"))
    mock_scenario.network.add_node(Node("D"))

    mock_scenario.network.add_link(Link("A", "B", capacity=5))
    mock_scenario.network.add_link(Link("B", "C", capacity=5))
    mock_scenario.network.add_link(Link("A", "D", capacity=5))
    mock_scenario.network.add_link(Link("D", "C", capacity=5))

    step = CapacityProbe(
        name="MyCapacityProbe",
        source_path="A",
        sink_path="C",
        shortest_path=False,
        flow_placement=FlowPlacement.PROPORTIONAL,
    )
    step.run(mock_scenario)

    mock_scenario.results.put.assert_called_once()
    call_args = mock_scenario.results.put.call_args[0]
    assert call_args[0] == "MyCapacityProbe"
    assert call_args[1] == "max_flow:[A -> C]"
    assert call_args[2] == 10.0
