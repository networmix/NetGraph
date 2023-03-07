from __future__ import annotations

from ngraph.lib.spf import spf
from ngraph.lib.place_flow import place_flow_on_graph
from ngraph.lib.calc_cap import CalculateCapacity
from ngraph.lib.common import (
    EdgeSelect,
    edge_select_fabric,
    init_flow_graph,
    FlowPlacement,
)
from ngraph.lib.graph import NodeID, MultiDiGraph


def calc_max_flow(
    graph: MultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> float:

    flow_graph = init_flow_graph(
        graph.copy(),
        flow_attr,
        flows_attr,
        reset_flow_graph,
    )

    _, pred = spf(
        flow_graph,
        src_node,
        edge_select_func=edge_select_fabric(EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING),
    )
    flow_meta = place_flow_on_graph(
        flow_graph, src_node, dst_node, pred, flow_placement=flow_placement
    )
    max_flow = flow_meta.placed_flow

    if shortest_path:
        return max_flow

    else:
        while True:
            _, pred = spf(
                flow_graph,
                src_node,
                edge_select_func=edge_select_fabric(
                    EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING
                ),
            )
            if dst_node not in pred:
                break

            flow_meta = place_flow_on_graph(
                flow_graph, src_node, dst_node, pred, flow_placement=flow_placement
            )

            max_flow += flow_meta.placed_flow

        return max_flow
