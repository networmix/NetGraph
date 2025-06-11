from unittest.mock import MagicMock

import pytest

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.network import Link, Network, Node
from ngraph.workflow.capacity_probe import CapacityProbe


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
    (e.g. ^S(\\d+)$), so S1 => group '1', S2 => group '2', etc.
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


def test_capacity_probe_pairwise_asymmetric_groups(mock_scenario):
    """
    Tests pairwise mode with different numbers of source and sink groups.
    3 sources, 2 sinks => 3×2 = 6 result entries.
    """
    # Create nodes
    for i in [1, 2, 3]:
        mock_scenario.network.add_node(Node(f"SRC{i}"))
    for i in [1, 2]:
        mock_scenario.network.add_node(Node(f"SINK{i}"))
    mock_scenario.network.add_node(Node("HUB"))

    # Connect all sources to hub with capacity 3, hub to all sinks with capacity 2
    for i in [1, 2, 3]:
        mock_scenario.network.add_link(Link(f"SRC{i}", "HUB", capacity=3))
    for i in [1, 2]:
        mock_scenario.network.add_link(Link("HUB", f"SINK{i}", capacity=2))

    step = CapacityProbe(
        name="AsymmetricPairwise",
        source_path=r"^SRC(\d+)$",  # groups: "1", "2", "3"
        sink_path=r"^SINK(\d+)$",  # groups: "1", "2"
        mode="pairwise",
    )

    step.run(mock_scenario)
    assert mock_scenario.results.put.call_count == 6  # 3×2

    calls = mock_scenario.results.put.call_args_list
    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        flows[label] = flow_val

    expected_labels = {
        "max_flow:[1 -> 1]",
        "max_flow:[1 -> 2]",
        "max_flow:[2 -> 1]",
        "max_flow:[2 -> 2]",
        "max_flow:[3 -> 1]",
        "max_flow:[3 -> 2]",
    }
    assert set(flows.keys()) == expected_labels
    # Each flow should be limited by the hub->sink capacity of 2
    for label in expected_labels:
        assert flows[label] == 2.0


def test_capacity_probe_pairwise_no_capturing_groups(mock_scenario):
    """
    Tests pairwise mode when the regex patterns don't use capturing groups.
    All matching nodes should be grouped under the pattern string itself.
    """
    mock_scenario.network.add_node(Node("SOURCE_A"))
    mock_scenario.network.add_node(Node("SOURCE_B"))
    mock_scenario.network.add_node(Node("TARGET_X"))
    mock_scenario.network.add_node(Node("TARGET_Y"))

    # Create a hub topology
    mock_scenario.network.add_node(Node("HUB"))
    mock_scenario.network.add_link(Link("SOURCE_A", "HUB", capacity=5))
    mock_scenario.network.add_link(Link("SOURCE_B", "HUB", capacity=5))
    mock_scenario.network.add_link(Link("HUB", "TARGET_X", capacity=3))
    mock_scenario.network.add_link(Link("HUB", "TARGET_Y", capacity=3))

    step = CapacityProbe(
        name="NoCapturingGroups",
        source_path="^SOURCE_",  # no capturing groups
        sink_path="^TARGET_",  # no capturing groups
        mode="pairwise",
    )

    step.run(mock_scenario)
    assert mock_scenario.results.put.call_count == 1  # 1×1 since no capturing groups

    call_args = mock_scenario.results.put.call_args[0]
    assert call_args[0] == "NoCapturingGroups"
    assert call_args[1] == "max_flow:[^SOURCE_ -> ^TARGET_]"
    # Combined flow through HUB: min(5+5, 3+3) = 6
    assert call_args[2] == 6.0


def test_capacity_probe_pairwise_multiple_capturing_groups(mock_scenario):
    """
    Tests pairwise mode with multiple capturing groups in the regex pattern.
    Groups should be joined with '|'.
    """
    # Create nodes with two-part naming: DC-Type pattern
    mock_scenario.network.add_node(Node("DC1-WEB1"))
    mock_scenario.network.add_node(Node("DC1-DB1"))
    mock_scenario.network.add_node(Node("DC2-WEB1"))
    mock_scenario.network.add_node(Node("DC2-DB1"))

    # Create hub topology
    mock_scenario.network.add_node(Node("CORE"))
    for dc in [1, 2]:
        for svc in ["WEB", "DB"]:
            mock_scenario.network.add_link(Link(f"DC{dc}-{svc}1", "CORE", capacity=4))

    step = CapacityProbe(
        name="MultiCapture",
        source_path=r"^(DC\d+)-(WEB\d+)$",  # captures: ("DC1", "WEB1"), etc.
        sink_path=r"^(DC\d+)-(DB\d+)$",  # captures: ("DC1", "DB1"), etc.
        mode="pairwise",
    )

    step.run(mock_scenario)
    assert mock_scenario.results.put.call_count == 4  # 2×2

    calls = mock_scenario.results.put.call_args_list
    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        flows[label] = flow_val

    expected_labels = {
        "max_flow:[DC1|WEB1 -> DC1|DB1]",
        "max_flow:[DC1|WEB1 -> DC2|DB1]",
        "max_flow:[DC2|WEB1 -> DC1|DB1]",
        "max_flow:[DC2|WEB1 -> DC2|DB1]",
    }
    assert set(flows.keys()) == expected_labels
    for label in expected_labels:
        assert flows[label] == 4.0


def test_capacity_probe_pairwise_with_disabled_nodes(mock_scenario):
    """
    Tests pairwise mode when some matched nodes are disabled.
    Disabled nodes should not participate in flow computation.
    """
    mock_scenario.network.add_node(Node("S1"))
    mock_scenario.network.add_node(Node("S2", disabled=True))  # disabled
    mock_scenario.network.add_node(Node("T1"))
    mock_scenario.network.add_node(Node("T2"))

    mock_scenario.network.add_node(Node("HUB"))
    mock_scenario.network.add_link(Link("S1", "HUB", capacity=5))
    mock_scenario.network.add_link(Link("S2", "HUB", capacity=5))  # disabled source
    mock_scenario.network.add_link(Link("HUB", "T1", capacity=3))
    mock_scenario.network.add_link(Link("HUB", "T2", capacity=3))

    step = CapacityProbe(
        name="DisabledNodes",
        source_path=r"^S(\d+)$",
        sink_path=r"^T(\d+)$",
        mode="pairwise",
    )

    step.run(mock_scenario)
    assert mock_scenario.results.put.call_count == 4  # still 2×2 pairs

    calls = mock_scenario.results.put.call_args_list
    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        flows[label] = flow_val

    # S2 is disabled, so flows involving group "2" should be 0
    assert flows["max_flow:[1 -> 1]"] == 3.0  # S1->T1
    assert flows["max_flow:[1 -> 2]"] == 3.0  # S1->T2
    assert flows["max_flow:[2 -> 1]"] == 0.0  # S2->T1 (S2 disabled)
    assert flows["max_flow:[2 -> 2]"] == 0.0  # S2->T2 (S2 disabled)


def test_capacity_probe_pairwise_disconnected_topology(mock_scenario):
    """
    Tests pairwise mode when some source-sink pairs have no connectivity.
    Should return 0 flow for disconnected pairs.
    """
    # Create two isolated islands
    mock_scenario.network.add_node(Node("S1"))
    mock_scenario.network.add_node(Node("T1"))
    mock_scenario.network.add_link(Link("S1", "T1", capacity=10))

    mock_scenario.network.add_node(Node("S2"))
    mock_scenario.network.add_node(Node("T2"))
    mock_scenario.network.add_link(Link("S2", "T2", capacity=8))

    # No connectivity between islands

    step = CapacityProbe(
        name="Disconnected",
        source_path=r"^S(\d+)$",
        sink_path=r"^T(\d+)$",
        mode="pairwise",
    )

    step.run(mock_scenario)
    assert mock_scenario.results.put.call_count == 4

    calls = mock_scenario.results.put.call_args_list
    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        flows[label] = flow_val

    # Only same-island connections should have flow
    assert flows["max_flow:[1 -> 1]"] == 10.0  # S1->T1 (connected)
    assert flows["max_flow:[2 -> 2]"] == 8.0  # S2->T2 (connected)
    assert flows["max_flow:[1 -> 2]"] == 0.0  # S1->T2 (disconnected)
    assert flows["max_flow:[2 -> 1]"] == 0.0  # S2->T1 (disconnected)


def test_capacity_probe_pairwise_single_group_each(mock_scenario):
    """
    Tests pairwise mode with only one source group and one sink group.
    Should behave similarly to combine mode but still produce pairwise-style labels.
    """
    mock_scenario.network.add_node(Node("SRC1"))
    mock_scenario.network.add_node(Node("SRC2"))
    mock_scenario.network.add_node(Node("SINK1"))
    mock_scenario.network.add_node(Node("SINK2"))

    mock_scenario.network.add_node(Node("HUB"))
    mock_scenario.network.add_link(Link("SRC1", "HUB", capacity=4))
    mock_scenario.network.add_link(Link("SRC2", "HUB", capacity=6))
    mock_scenario.network.add_link(Link("HUB", "SINK1", capacity=5))
    mock_scenario.network.add_link(Link("HUB", "SINK2", capacity=3))

    step = CapacityProbe(
        name="SingleGroups",
        source_path=r"^SRC",  # no capturing groups, all sources in one group
        sink_path=r"^SINK",  # no capturing groups, all sinks in one group
        mode="pairwise",
    )

    step.run(mock_scenario)
    assert mock_scenario.results.put.call_count == 1  # 1×1

    call_args = mock_scenario.results.put.call_args[0]
    assert call_args[0] == "SingleGroups"
    assert call_args[1] == "max_flow:[^SRC -> ^SINK]"
    # Total flow: min(4+6, 5+3) = min(10, 8) = 8
    assert call_args[2] == 8.0


def test_capacity_probe_pairwise_potential_infinite_loop(mock_scenario):
    """
    Tests that overlapping source and sink patterns are handled gracefully.

    When the same nodes can be both sources and destinations (overlapping regex patterns),
    the max flow calculation should detect this scenario and return 0 flow for overlapping
    cases due to flow conservation principles - no net flow from a set to itself.

    This test verifies that scenarios like N1->N1 (self-loops) and overlapping groups
    are handled correctly without causing infinite loops.

    Expected behavior: Should handle overlapping patterns gracefully and complete quickly,
    returning 0 flow for self-loop cases and appropriate flows for valid paths.
    """
    # Create nodes that match both source and sink patterns
    mock_scenario.network.add_node(Node("N1"))
    mock_scenario.network.add_node(Node("N2"))

    # Simple topology with normal capacity
    mock_scenario.network.add_link(Link("N1", "N2", capacity=1.0))

    step = CapacityProbe(
        name="OverlappingPatternsTest",
        # OVERLAPPING patterns - same nodes match both source and sink
        source_path=r"^N(\d+)$",  # Matches N1, N2
        sink_path=r"^N(\d+)$",  # Matches N1, N2 (SAME NODES!)
        mode="pairwise",  # Test pairwise mode with overlapping patterns
    )

    step.run(mock_scenario)

    # Should return 4 results for 2×2 = N1->N1, N1->N2, N2->N1, N2->N2
    assert mock_scenario.results.put.call_count == 4

    calls = mock_scenario.results.put.call_args_list
    flows = {}
    for c in calls:
        step_name, label, flow_val = c[0]
        assert step_name == "OverlappingPatternsTest"
        flows[label] = flow_val

    expected_labels = {
        "max_flow:[1 -> 1]",  # N1->N1 (self-loop)
        "max_flow:[1 -> 2]",  # N1->N2 (valid path)
        "max_flow:[2 -> 1]",  # N2->N1 (no path)
        "max_flow:[2 -> 2]",  # N2->N2 (self-loop)
    }
    assert set(flows.keys()) == expected_labels

    # Self-loops should have 0 flow due to flow conservation
    assert flows["max_flow:[1 -> 1]"] == 0.0  # N1->N1 self-loop
    assert flows["max_flow:[2 -> 2]"] == 0.0  # N2->N2 self-loop

    # Valid paths should have appropriate flows
    assert flows["max_flow:[1 -> 2]"] == 1.0  # N1->N2 has capacity 1.0
    assert (
        flows["max_flow:[2 -> 1]"] == 1.0
    )  # N2->N1 has reverse edge with capacity 1.0
