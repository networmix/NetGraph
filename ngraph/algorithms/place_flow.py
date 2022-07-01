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

from ngraph.algorithms.calc_cap import calc_graph_cap
from ngraph.graph import DstNodeID, EdgeID, MultiDiGraph, NodeID, SrcNodeID


class FlowPlacement(IntEnum):
    # load balancing proportional to remaining capacity
    PROPORTIONAL = 1
    # equal load balancing
    EQUAL_BALANCED = 2


@dataclass
class FlowPlacementMeta:
    placed_flow: float
    remaining_flow: float
    nodes: Set[NodeID] = field(default_factory=set)
    edges: Set[EdgeID] = field(default_factory=set)


def place_flow_on_graph(
    flow_graph: MultiDiGraph,
    src_node: SrcNodeID,
    dst_node: DstNodeID,
    pred: Dict[DstNodeID, Dict[SrcNodeID, List[EdgeID]]],
    flow: float = float("inf"),
    flow_index: Optional[Hashable] = None,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> FlowPlacementMeta:

    # Calculate remaining capacity
    rem_cap, node_capacities = calc_graph_cap(
        flow_graph, src_node, dst_node, pred, capacity_attr, flow_attr
    )

    edges = flow_graph.get_edges()
    nodes = flow_graph.get_nodes()

    # Select how remaining capacity is used
    if flow_placement == FlowPlacement.PROPORTIONAL:
        max_flow = rem_cap.max_total_flow
    elif flow_placement == FlowPlacement.EQUAL_BALANCED:
        max_flow = rem_cap.max_balanced_flow
    else:
        raise RuntimeError(f"Unknown flow_placement {flow_placement}")

    placed_flow = min(max_flow, flow)
    remaining_flow = max(flow - max_flow if flow != float("inf") else float("inf"), 0)
    if not placed_flow > 0:
        return FlowPlacementMeta(0, flow)

    flow_placement_meta = FlowPlacementMeta(placed_flow, remaining_flow)
    if flow_placement == FlowPlacement.PROPORTIONAL:
        for node_id, node_cap in node_capacities.items():
            node = nodes[node_id]
            if node_cap.flow_fraction_total:
                flow_placement_meta.nodes.add(node_id)
                node[flow_attr] += node_cap.flow_fraction_total * placed_flow
                node[flows_attr].setdefault(flow_index, 0)
                node[flows_attr][flow_index] += (
                    node_cap.flow_fraction_total * placed_flow
                )
                total_rem_cap = sum(
                    edges[edge_id][3][capacity_attr] - edges[edge_id][3][flow_attr]
                    for edge_id in node_cap.edges
                )
                for edge_id in node_cap.edges:
                    edge_subflow = (
                        node_cap.flow_fraction_total
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
        for node_id, node_cap in node_capacities.items():
            flow_placement_meta.edges.add(node_id)
            node = nodes[node_id]
            node[flow_attr] += node_cap.flow_fraction_balanced * placed_flow
            node[flows_attr].setdefault(flow_index, 0)
            node[flows_attr][flow_index] += (
                node_cap.flow_fraction_balanced * placed_flow
            )
            edge_subflow = (
                node_cap.flow_fraction_balanced * placed_flow / len(node_cap.edges)
            )
            for edge_id in node_cap.edges:
                flow_placement_meta.edges.add(edge_id)
                edges[edge_id][3][flow_attr] += edge_subflow
                edges[edge_id][3][flows_attr].setdefault(flow_index, 0)
                edges[edge_id][3][flows_attr][flow_index] += edge_subflow

    flow_placement_meta.nodes.add(dst_node)
    return flow_placement_meta
