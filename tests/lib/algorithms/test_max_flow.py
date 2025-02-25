import pytest
from pytest import approx

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.algorithms.max_flow import calc_max_flow
from tests.lib.algorithms.sample_graphs import (
    line1,
    square4,
    graph5,
)


class TestMaxFlowBasic:
    """
    Tests that directly verify specific flow values on known small graphs.
    """

    def test_max_flow_line1_full_flow(self, line1):
        """
        On line1 fixture:
         - Full iterative max flow from A to C should be 5.
        """
        max_flow = calc_max_flow(line1, "A", "C")
        assert max_flow == 5

    def test_max_flow_line1_shortest_path(self, line1):
        """
        On line1 fixture:
         - With shortest_path=True (single augmentation), expect flow=4.
        """
        max_flow = calc_max_flow(line1, "A", "C", shortest_path=True)
        assert max_flow == 4

    def test_max_flow_square4_full_flow(self, square4):
        """
        On square4 fixture:
         - Full iterative max flow from A to B should be 350 by default.
        """
        max_flow = calc_max_flow(square4, "A", "B")
        assert max_flow == 350

    def test_max_flow_square4_shortest_path(self, square4):
        """
        On square4 fixture:
         - With shortest_path=True, only one flow augmentation => 100.
        """
        max_flow = calc_max_flow(square4, "A", "B", shortest_path=True)
        assert max_flow == 100

    def test_max_flow_graph5_full_flow(self, graph5):
        """
        On graph5 (fully connected 5 nodes with capacity=1 on each edge):
         - Full iterative max flow from A to B = 4.
        """
        max_flow = calc_max_flow(graph5, "A", "B")
        assert max_flow == 4

    def test_max_flow_graph5_shortest_path(self, graph5):
        """
        On graph5:
         - With shortest_path=True => flow=1 for a single augmentation.
        """
        max_flow = calc_max_flow(graph5, "A", "B", shortest_path=True)
        assert max_flow == 1


class TestMaxFlowCopyBehavior:
    """
    Tests verifying how flow is (or isn't) preserved when copy_graph=False.
    """

    def test_max_flow_graph_copy_disabled(self, graph5):
        """
        - The first call saturates flow from A to B => 4.
        - A second call on the same graph (copy_graph=False) expects 0
          because the flow is already placed.
        """
        graph5_copy = graph5.copy()
        max_flow1 = calc_max_flow(graph5_copy, "A", "B", copy_graph=False)
        assert max_flow1 == 4

        max_flow2 = calc_max_flow(graph5_copy, "A", "B", copy_graph=False)
        assert max_flow2 == 0

    def test_max_flow_reset_flow(self, line1):
        """
        Ensures that reset_flow_graph=True zeroes out existing flow
        before computing again.
        """
        # First run places flow on line1:
        calc_max_flow(line1, "A", "C", copy_graph=False)

        # Now run again with reset_flow_graph=True:
        max_flow_after_reset = calc_max_flow(
            line1, "A", "C", copy_graph=False, reset_flow_graph=True
        )
        # Should return the same result as a fresh run (5)
        assert max_flow_after_reset == 5


class TestMaxFlowShortestPathRepeated:
    """
    Verifies that repeated shortest-path calls do not accumulate flow
    when copy_graph=False.
    """

    def test_shortest_path_repeated_calls(self, line1):
        """
        First call with shortest_path=True => 4
        Second call => 1 (since there is a longer path found after saturation of the shortest).
        """
        flow1 = calc_max_flow(line1, "A", "C", shortest_path=True, copy_graph=False)
        assert flow1 == 4

        flow2 = calc_max_flow(line1, "A", "C", shortest_path=True, copy_graph=False)
        assert flow2 == 1


@pytest.mark.parametrize(
    "placement", [FlowPlacement.PROPORTIONAL, FlowPlacement.EQUAL_BALANCED]
)
def test_square4_flow_placement(square4, placement):
    """
    Example showing how to test different FlowPlacement modes on the same fixture.
    For square4, the PROPORTIONAL and EQUAL_BALANCED results might differ,
    but here we simply check if we get the original tested value or not.
    Adjust as needed if the EQUAL_BALANCED result is known to differ.
    """
    max_flow = calc_max_flow(square4, "A", "B", flow_placement=placement)

    if placement == FlowPlacement.PROPORTIONAL:
        # Known from above
        assert max_flow == 350
    else:
        # If equal-balanced yields a different known answer, verify that here.
        # If it's actually the same, use the same assertion or approx check:
        assert max_flow == approx(350, abs=1e-9)


class TestMaxFlowEdgeCases:
    """
    Additional tests for error conditions or graphs with no feasible flow.
    """

    def test_missing_src_node(self, line1):
        """
        Trying to compute flow with a non-existent source raises KeyError.
        """
        with pytest.raises(KeyError):
            calc_max_flow(line1, "Z", "C")

    def test_missing_dst_node(self, line1):
        """
        Trying to compute flow with a non-existent destination raises ValueError.
        """
        with pytest.raises(ValueError):
            calc_max_flow(line1, "A", "Z")

    def test_zero_capacity_edges(self):
        """
        Graph with edges that all have zero capacity => max flow=0.
        """
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_edge("A", "B", capacity=0.0, cost=1)
        max_flow = calc_max_flow(g, "A", "B")
        assert max_flow == 0.0

    def test_disconnected_graph(self):
        """
        Graph with no edges => disconnected => max flow=0.
        """
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        max_flow = calc_max_flow(g, "A", "B")
        assert max_flow == 0.0
