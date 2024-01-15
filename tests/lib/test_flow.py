# pylint: disable=protected-access,invalid-name
from ngraph.lib.common import (
    EdgeSelect,
    init_flow_graph,
    PathAlg,
    FlowPlacement,
)
from ngraph.lib.flow import Flow, FlowIndex
from ngraph.lib.path_bundle import PathBundle
from ngraph.lib.common import MIN_FLOW

from ..sample_data.sample_graphs import *


class TestFlow:
    def test_flow_1(self, square1):
        flow_graph = init_flow_graph(square1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, ("A", "C", "test_flow"))
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 0, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 0
        assert remaining_flow == 0

    def test_flow_2(self, square1):
        flow_graph = init_flow_graph(square1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, ("A", "C", "test_flow"))
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 1, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 1
        assert remaining_flow == 0

    def test_flow_3(self, square1):
        flow_graph = init_flow_graph(square1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, ("A", "C", "test_flow"))
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 1, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 1
        assert flow.placed_flow == 1
        assert remaining_flow == 0
        assert flow_graph.get_edge_attr(0)["flow"] == 1
        flow.remove_flow(flow_graph)
        assert flow.placed_flow == 0
        assert flow_graph.get_edge_attr(0)["flow"] == 0
