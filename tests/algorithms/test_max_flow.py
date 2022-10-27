# pylint: disable=protected-access,invalid-name
import pytest

from ngraph.graph import MultiDiGraph
from ngraph.algorithms.calc_cap import (
    MaxFlow,
)
from ngraph.algorithms.max_flow import calc_max_flow


@pytest.fixture
def graph_square_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)
    g.add_edge("A", "C", metric=3, capacity=3)
    return g


class TestMaxFlow:
    def test_max_flow_1(self, graph_square_1):
        max_flow = calc_max_flow(graph_square_1, "A", "C")
        assert max_flow == MaxFlow(
            max_total_flow=6, max_single_flow=3, max_balanced_flow=1
        )

    def test_max_flow_2(self, graph_square_1):
        max_flow = calc_max_flow(graph_square_1, "A", "C", shortest_path=True)
        assert max_flow == MaxFlow(
            max_total_flow=1, max_single_flow=1, max_balanced_flow=1
        )
