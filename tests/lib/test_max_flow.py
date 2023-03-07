# pylint: disable=protected-access,invalid-name
import pytest

from ngraph.lib.graph import MultiDiGraph

from ngraph.lib.max_flow import calc_max_flow
from ..sample_data.sample_graphs import *


class TestMaxFlow:
    def test_max_flow_line1_1(self, line1):
        max_flow = calc_max_flow(line1, "A", "C")
        assert max_flow == 5

    def test_max_flow_line1_2(self, line1):
        max_flow = calc_max_flow(line1, "A", "C", shortest_path=True)
        assert max_flow == 4

    def test_max_flow_square4_1(self, square4):
        max_flow = calc_max_flow(square4, "A", "B")
        assert max_flow == 350

    def test_max_flow_square4_2(self, square4):
        max_flow = calc_max_flow(square4, "A", "B", shortest_path=True)
        assert max_flow == 100

    def test_max_flow_graph5_1(self, graph5):
        max_flow = calc_max_flow(graph5, "A", "B")
        assert max_flow == 4

    def test_max_flow_graph5_2(self, graph5):
        max_flow = calc_max_flow(graph5, "A", "B", shortest_path=True)
        assert max_flow == 1
