from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import (
    Dict,
    Hashable,
    List,
    Optional,
    Set,
)

from ngraph.lib.calc_cap import CalculateCapacity
from ngraph.lib.common import FlowPlacement
from ngraph.lib.graph import EdgeID, MultiDiGraph, NodeID


@dataclass
class FlowPlacementMeta:
    placed_flow: float
    remaining_flow: float
    nodes: Set[NodeID] = field(default_factory=set)
    edges: Set[EdgeID] = field(default_factory=set)


def place_flow_on_graph(
    flow_graph: MultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]],
    flow: float = float("inf"),
    flow_index: Optional[Hashable] = None,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> FlowPlacementMeta:
    # Calculate remaining capacity
    rem_cap, flow_dict = CalculateCapacity.calc_graph_cap(
        flow_graph, src_node, dst_node, pred, flow_placement, capacity_attr, flow_attr
    )

    edges = flow_graph.get_edges()
    nodes = flow_graph.nodes

    placed_flow = min(rem_cap, flow)
    remaining_flow = max(flow - rem_cap if flow != float("inf") else float("inf"), 0)
    if placed_flow <= 0:
        return FlowPlacementMeta(0, flow)

    flow_placement_meta = FlowPlacementMeta(placed_flow, remaining_flow)

    for node_a in flow_dict:
        for node_b in flow_dict[node_a]:
            flow_fraction = flow_dict[node_a][node_b]
            if flow_fraction > 0:
                flow_placement_meta.nodes.add(node_a)
                flow_placement_meta.nodes.add(node_b)
                nodes[node_a][flow_attr] += flow_fraction * placed_flow
                nodes[node_a][flows_attr].setdefault(flow_index, 0)

                edge_list = pred[node_b][node_a]
                if flow_placement == FlowPlacement.PROPORTIONAL:
                    total_rem_cap = sum(
                        edges[edge_id][3][capacity_attr] - edges[edge_id][3][flow_attr]
                        for edge_id in edge_list
                    )
                    for edge_id in edge_list:
                        edge_subflow = (
                            flow_fraction
                            * placed_flow
                            / total_rem_cap
                            * (
                                edges[edge_id][3][capacity_attr]
                                - edges[edge_id][3][flow_attr]
                            )
                        )
                        if edge_subflow:
                            flow_placement_meta.edges.add(edge_id)
                            edges[edge_id][3][flow_attr] += edge_subflow
                            edges[edge_id][3][flows_attr].setdefault(flow_index, 0)
                            edges[edge_id][3][flows_attr][flow_index] += edge_subflow

                elif flow_placement == FlowPlacement.EQUAL_BALANCED:
                    edge_subflow = flow_fraction * placed_flow / len(edge_list)
                    for edge_id in edge_list:
                        flow_placement_meta.edges.add(edge_id)
                        edges[edge_id][3][flow_attr] += edge_subflow
                        edges[edge_id][3][flows_attr].setdefault(flow_index, 0)
                        edges[edge_id][3][flows_attr][flow_index] += edge_subflow

    flow_placement_meta.nodes.add(dst_node)
    return flow_placement_meta


def remove_flow_from_graph(
    flow_graph: MultiDiGraph,
    flow_index: Optional[Hashable] = None,
    flow_attr: str = "flow",
    flows_attr: str = "flows",
):
    edges_to_clear = set()
    for edge_id, edge_tuple in flow_graph.get_edges().items():
        edge_attr = edge_tuple[3]

        if flow_index and flow_index in edge_attr[flows_attr]:
            # Remove flow with given index from edge
            edge_attr[flow_attr] -= edge_attr[flows_attr][flow_index]
            del edge_attr[flows_attr][flow_index]
        elif not flow_index:
            # Remove all flows from edge
            edge_attr[flow_attr] = 0
            edge_attr[flows_attr] = {}
