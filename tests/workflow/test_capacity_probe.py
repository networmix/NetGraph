import pytest
from unittest.mock import MagicMock, call

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
    and stores it in scenario.results with the expected label (no mode specified => "combine").
    """
    # Create a 2-node network (A->B capacity=5)
    mock_scenario.network.add_node(Node("A"))
    mock_scenario.network.add_node(Node("B"))
    mock_scenario.network.add_link(Link("A", "B", capacity=5))

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

    mock_scenario.results.put.assert_called_once()
    call_args = mock_scenario.results.put.call_args[0]
    # call_args => (step_name, result_label, flow_value)
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

    with pytest.raises(ValueError, match="No source nodes found matching 'A'"):
        step.run(mock_scenario)


def test_capacity_probe_no_sink(mock_scenario):
    """
    Tests that CapacityProbe raises ValueError if no sink nodes match.
    """
    # The network only has node "A"; no node matches "B".
    mock_scenario.network.add_node(Node("A"))
    mock_scenario.network.add_link(Link("A", "A", capacity=10))

    step = CapacityProbe(name="MyCapacityProbe", source_path="A", sink_path="B")

    with pytest.raises(ValueError, match="No sink nodes found matching 'B'"):
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


def test_capacity_probe_mode_combine_multiple_groups(mock_scenario):
    """
    Tests 'combine' mode with multiple source groups and sink groups.
    The flow is combined into a single entry. We confirm there's only
    one result label and it has the expected flow.
    """
    # Network:
    #   S1 -> M -> T1
    #   S2 -> M -> T2
    # Capacity = 2 on each link
    mock_scenario.network.add_node(Node("S1"))
    mock_scenario.network.add_node(Node("S2"))
    mock_scenario.network.add_node(Node("M"))
    mock_scenario.network.add_node(Node("T1"))
    mock_scenario.network.add_node(Node("T2"))

    for src in ("S1", "S2"):
        mock_scenario.network.add_link(Link(src, "M", capacity=2))
    mock_scenario.network.add_link(Link("M", "T1", capacity=2))
    mock_scenario.network.add_link(Link("M", "T2", capacity=2))

    step = CapacityProbe(
        name="MyCapacityProbeCombine",
        source_path="^S",  # matches S1, S2
        sink_path="^T",  # matches T1, T2
        mode="combine",
        shortest_path=False,
    )

    step.run(mock_scenario)
    mock_scenario.results.put.assert_called_once()

    call_args = mock_scenario.results.put.call_args[0]
    # We only expect one "combine" result
    assert call_args[0] == "MyCapacityProbeCombine"
    # The label might look like "max_flow:[S1 -> T1]" or "max_flow:[S|S2 -> T|T2]",
    # but we only check the final flow value.
    # The combined capacity is effectively 2 + 2 => 4 from S1 & S2 into M,
    # and 2 + 2 => 4 from M to T1 & T2. So total flow is 4.
    assert call_args[2] == 4.0


def test_capacity_probe_mode_pairwise_multiple_groups(mock_scenario):
    """
    Tests 'pairwise' mode with multiple source groups and sink groups.
    We confirm multiple result entries are stored, one per (src_label, snk_label).
    To ensure distinct group labels, we use capturing groups in the regex
    (e.g. ^S(\d+)$), so S1 => group '1', S2 => group '2', etc.
    """
    # Network:
    #   S1 -> M -> T1
    #   S2 -> M -> T2
    # Each link capacity=2
    mock_scenario.network.add_node(Node("S1"))
    mock_scenario.network.add_node(Node("S2"))
    mock_scenario.network.add_node(Node("M"))
    mock_scenario.network.add_node(Node("T1"))
    mock_scenario.network.add_node(Node("T2"))

    mock_scenario.network.add_link(Link("S1", "M", capacity=2))
    mock_scenario.network.add_link(Link("M", "T1", capacity=2))
    mock_scenario.network.add_link(Link("S2", "M", capacity=2))
    mock_scenario.network.add_link(Link("M", "T2", capacity=2))

    step = CapacityProbe(
        name="MyCapacityProbePairwise",
        # Use capturing groups so S1 => group "1", S2 => group "2", T1 => group "1", T2 => group "2"
        source_path=r"^S(\d+)$",
        sink_path=r"^T(\d+)$",
        mode="pairwise",
        shortest_path=False,
    )

    step.run(mock_scenario)
    # Expect 2 x 2 = 4 result entries, since pairwise => (S1->T1, S1->T2, S2->T1, S2->T2)

    assert mock_scenario.results.put.call_count == 4

    # Gather calls
    calls = mock_scenario.results.put.call_args_list
    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        assert step_name == "MyCapacityProbePairwise"
        flows[label] = flow_val

    expected_labels = {
        "max_flow:[1 -> 1]",
        "max_flow:[1 -> 2]",
        "max_flow:[2 -> 1]",
        "max_flow:[2 -> 2]",
    }
    assert set(flows.keys()) == expected_labels

    # Each path (S1->M->T1, etc.) has capacity 2, so we expect flows = 2.0
    for label in expected_labels:
        assert flows[label] == 2.0


def test_capacity_probe_probe_reverse(mock_scenario):
    """
    Tests that probe_reverse=True computes flow in both directions. We expect
    two sets of results: forward and reverse.
    """
    # Simple A->B link with capacity=3
    mock_scenario.network.add_node(Node("A"))
    mock_scenario.network.add_node(Node("B"))
    mock_scenario.network.add_link(Link("A", "B", capacity=3))

    step = CapacityProbe(
        name="MyCapacityProbeReversed",
        source_path="A",
        sink_path="B",
        probe_reverse=True,
        mode="combine",
    )

    step.run(mock_scenario)

    # Expect 2 calls: forward flow (A->B) and reverse flow (B->A).
    assert mock_scenario.results.put.call_count == 2
    calls = mock_scenario.results.put.call_args_list

    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        assert step_name == "MyCapacityProbeReversed"
        flows[label] = flow_val

    # We expect "max_flow:[A -> B]" = 3, and "max_flow:[B -> A]" = 3
    assert "max_flow:[A -> B]" in flows
    assert "max_flow:[B -> A]" in flows
    assert flows["max_flow:[A -> B]"] == 3.0
    assert flows["max_flow:[B -> A]"] == 3.0
