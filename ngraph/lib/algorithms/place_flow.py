from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Hashable, List, Optional, Set

from ngraph.lib.algorithms.calc_capacity import calc_graph_capacity
from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.graph import EdgeID, NodeID, StrictMultiDiGraph


@dataclass
class FlowPlacementMeta:
    """
    Metadata capturing how flow was placed on the graph.

    Attributes:
        placed_flow: The amount of flow actually placed.
        remaining_flow: The portion of flow that could not be placed due to capacity limits.
        nodes: Set of node IDs that participated in the flow.
        edges: Set of edge IDs that carried some portion of this flow.
    """

    placed_flow: float
    remaining_flow: float
    nodes: Set[NodeID] = field(default_factory=set)
    edges: Set[EdgeID] = field(default_factory=set)


def place_flow_on_graph(
    flow_graph: StrictMultiDiGraph,
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
    """Place flow from `src_node` to `dst_node` on the given `flow_graph`.

    Uses a precomputed `flow_dict` from `calc_graph_capacity` to figure out how
    much flow can be placed. Updates the graph's edges and nodes with the placed flow.

    Args:
        flow_graph: The graph on which flow will be placed.
        src_node: The source node.
        dst_node: The destination node.
        pred: A dictionary of node->(adj_node->list_of_edge_IDs) giving path adjacency.
        flow: Requested flow amount; can be infinite.
        flow_index: Identifier for this flow (used to track multiple flows).
        flow_placement: Strategy for distributing flow among parallel equal cost paths.
        capacity_attr: Attribute name on edges for capacity.
        flow_attr: Attribute name on edges/nodes for aggregated flow.
        flows_attr: Attribute name on edges/nodes for per-flow tracking.

    Returns:
        FlowPlacementMeta: Contains the placed flow amount, remaining flow amount,
            and sets of touched nodes/edges.
    """
    # 1) Determine the maximum feasible flow via calc_graph_capacity.
    rem_cap, flow_dict = calc_graph_capacity(
        flow_graph, src_node, dst_node, pred, flow_placement, capacity_attr, flow_attr
    )

    # 2) Decide how much flow we can place, given the request and the remaining capacity.
    placed_flow = min(rem_cap, flow)
    remaining_flow = max(flow - rem_cap if flow != float("inf") else float("inf"), 0.0)
    if placed_flow <= 0:
        # If no flow can be placed, return early with zero placement.
        return FlowPlacementMeta(0.0, flow)

    # Track the placement metadata.
    flow_placement_meta = FlowPlacementMeta(placed_flow, remaining_flow)

    # For convenience, get direct references to edges and nodes structures.
    edges = flow_graph.get_edges()
    nodes = flow_graph.get_nodes()

    # Ensure we capture source and destination in the metadata.
    flow_placement_meta.nodes.add(src_node)
    flow_placement_meta.nodes.add(dst_node)

    # 3) Distribute the feasible flow across the nodes/edges according to flow_dict.
    for node_a, to_dict in flow_dict.items():
        for node_b, flow_fraction in to_dict.items():
            if flow_fraction > 0.0:
                # Mark these nodes as active in the flow.
                flow_placement_meta.nodes.add(node_a)
                flow_placement_meta.nodes.add(node_b)

                # Update node flow attributes.
                node_a_attr = nodes[node_a]
                node_a_attr[flow_attr] += flow_fraction * placed_flow
                node_a_attr[flows_attr].setdefault(flow_index, 0.0)
                node_a_attr[flows_attr][flow_index] += flow_fraction * placed_flow

                # The edges from node_b->node_a in `pred` carry the flow in forward direction.
                edge_list = pred[node_b][node_a]

                if flow_placement == FlowPlacement.PROPORTIONAL:
                    # Distribute proportionally to each edge's unused capacity.
                    total_rem_cap = sum(
                        edges[eid][3][capacity_attr] - edges[eid][3][flow_attr]
                        for eid in edge_list
                    )
                    if total_rem_cap > 0.0:
                        for eid in edge_list:
                            edge_cap = edges[eid][3][capacity_attr]
                            edge_flow = edges[eid][3][flow_attr]
                            unused = edge_cap - edge_flow
                            if unused > 0:
                                edge_subflow = (
                                    flow_fraction * placed_flow / total_rem_cap * unused
                                )
                                if edge_subflow > 0.0:
                                    flow_placement_meta.edges.add(eid)
                                    edges[eid][3][flow_attr] += edge_subflow
                                    edges[eid][3][flows_attr].setdefault(
                                        flow_index, 0.0
                                    )
                                    edges[eid][3][flows_attr][
                                        flow_index
                                    ] += edge_subflow

                elif flow_placement == FlowPlacement.EQUAL_BALANCED:
                    # Split equally across all parallel edges in edge_list.
                    if len(edge_list) > 0:
                        edge_subflow = (flow_fraction * placed_flow) / len(edge_list)
                        for eid in edge_list:
                            flow_placement_meta.edges.add(eid)
                            edges[eid][3][flow_attr] += edge_subflow
                            edges[eid][3][flows_attr].setdefault(flow_index, 0.0)
                            edges[eid][3][flows_attr][flow_index] += edge_subflow

    return flow_placement_meta


def remove_flow_from_graph(
    flow_graph: StrictMultiDiGraph,
    flow_index: Optional[Hashable] = None,
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> None:
    """Remove one (or all) flows from the given graph.

    Args:
        flow_graph: The graph from which flow(s) should be removed.
        flow_index: If provided, only remove the specified flow. If None,
            remove all flows entirely.
        flow_attr: The aggregate flow attribute name on edges.
        flows_attr: The per-flow attribute name on edges.
    """
    edges = flow_graph.get_edges()
    for edge_id, (_, _, _, edge_attr) in edges.items():
        if flow_index is not None and flow_index in edge_attr[flows_attr]:
            # Subtract only the specified flow
            removed = edge_attr[flows_attr][flow_index]
            edge_attr[flow_attr] -= removed
            del edge_attr[flows_attr][flow_index]
        elif flow_index is None:
            # Remove all flows
            edge_attr[flow_attr] = 0.0
            edge_attr[flows_attr] = {}
