from __future__ import annotations

from ngraph.algorithms.spf import spf
from ngraph.algorithms.place_flow import place_flow_on_graph
from ngraph.algorithms.calc_cap import calc_graph_cap, MaxFlow
from ngraph.algorithms.common import EdgeSelect, edge_select_fabric, init_flow_graph
from ngraph.graph import DstNodeID, MultiDiGraph, SrcNodeID


def calc_max_flow(
    graph: MultiDiGraph,
    src_node: SrcNodeID,
    dst_node: DstNodeID,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> MaxFlow:

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
    max_flow, _ = calc_graph_cap(
        flow_graph, src_node, dst_node, pred, capacity_attr, flow_attr
    )

    if shortest_path:
        return max_flow

    else:
        max_total_flow = 0
        max_single_flow = max_flow.max_single_flow
        flow_graph_orig = flow_graph.copy()

        while dst_node in pred:
            max_flow_local, _ = calc_graph_cap(
                flow_graph_orig, src_node, dst_node, pred, capacity_attr, flow_attr
            )

            max_single_flow = max(max_single_flow, max_flow_local.max_single_flow)
            flow_meta = place_flow_on_graph(flow_graph, src_node, dst_node, pred)

            max_total_flow += flow_meta.placed_flow
            _, pred = spf(
                flow_graph,
                src_node,
                edge_select_func=edge_select_fabric(
                    EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING
                ),
            )
        return MaxFlow(max_total_flow, max_single_flow, max_flow.max_balanced_flow)
