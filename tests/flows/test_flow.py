from ngraph.algorithms.base import FlowPlacement
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.flows.flow import Flow, FlowIndex
from ngraph.paths.bundle import PathBundle


class TestFlow:
    def test_flow_place_and_remove(self, square1):
        flow_graph = init_flow_graph(square1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, FlowIndex("A", "C", "test_flow", 0))

        # No placement below threshold
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 0, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 0
        assert remaining_flow == 0

        # Place positive amount
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 1, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 1
        assert flow.placed_flow == 1
        assert remaining_flow == 0
        assert flow_graph.get_edge_attr(0)["flow"] == 1

        # Remove flow from graph
        flow.remove_flow(flow_graph)
        assert flow.placed_flow == 0
        assert flow_graph.get_edge_attr(0)["flow"] == 0
