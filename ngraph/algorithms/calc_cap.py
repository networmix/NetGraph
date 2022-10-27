from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import (
    Dict,
    List,
    Set,
    Tuple,
    NamedTuple,
)
from ngraph.graph import DstNodeID, EdgeID, MultiDiGraph, NodeID, SrcNodeID


@dataclass
class NodeCapacity:
    node_id: NodeID
    edges: Set[EdgeID] = field(default_factory=set)
    edges_max_flow: Dict[Tuple[EdgeID], MaxFlow] = field(default_factory=dict)
    max_balanced_flow: float = 0
    max_single_flow: float = 0
    max_total_flow: float = 0
    downstream_nodes: Dict[Tuple[EdgeID], Set[NodeID]] = field(default_factory=dict)
    flow_fraction_balanced: float = 0
    flow_fraction_total: float = 0


class MaxFlow(NamedTuple):
    max_total_flow: float
    max_single_flow: float
    max_balanced_flow: float


def calc_graph_cap(
    flow_graph: MultiDiGraph,
    src_node: SrcNodeID,
    dst_node: DstNodeID,
    pred: Dict[DstNodeID, Dict[SrcNodeID, List[EdgeID]]],
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Tuple[MaxFlow, Dict[NodeID, NodeCapacity]]:
    """
    Calculate capacity between src_node and dst_node in a flow graph
    using all the paths encoded in the dict of predecessors
    """
    edges = flow_graph.get_edges()
    node_capacities: Dict[NodeID, NodeCapacity] = {}
    succ: Dict[SrcNodeID, Dict[DstNodeID, Tuple[EdgeID]]] = {}

    # Find node capacities and build successors
    # BFS from the dst to src across the pred
    queue = deque([dst_node])
    while queue:
        node = queue.popleft()
        for prev_hop, edge_list in pred[node].items():
            edge_tuple = tuple(edge_list)
            succ.setdefault(prev_hop, {})[node] = edge_tuple

            prev_hop_node_cap = (
                node_capacities[prev_hop]
                if prev_hop in node_capacities
                else NodeCapacity(prev_hop)
            )
            prev_hop_node_cap.downstream_nodes.setdefault(edge_tuple, set()).add(node)
            prev_hop_node_cap.edges.update(edge_tuple)

            edge_rem_cap_list = [
                edges[edge_id][3][capacity_attr] - edges[edge_id][3][flow_attr]
                for edge_id in edge_tuple
            ]

            max_total_flow = sum(edge_rem_cap_list)
            max_single_flow = max(edge_rem_cap_list)
            max_balanced_flow = min(edge_rem_cap_list) * len(edge_rem_cap_list)
            if node in node_capacities:
                max_total_flow = min(
                    max_total_flow, node_capacities[node].max_total_flow
                )
                max_single_flow = min(
                    max_single_flow, node_capacities[node].max_single_flow
                )
                max_balanced_flow = min(
                    max_balanced_flow, node_capacities[node].max_balanced_flow
                )

                for node_set in node_capacities[node].downstream_nodes.values():
                    prev_hop_node_cap.downstream_nodes[edge_tuple].update(node_set)

            prev_hop_node_cap.edges_max_flow[edge_tuple] = MaxFlow(
                max_total_flow, max_single_flow, max_balanced_flow
            )

            prev_hop_node_cap.max_balanced_flow = min(
                [
                    edges_max_flow.max_balanced_flow / len(edge_tuple)
                    for edge_tuple, edges_max_flow in prev_hop_node_cap.edges_max_flow.items()
                ]
            ) * len(prev_hop_node_cap.edges)
            prev_hop_node_cap.max_single_flow = max(
                [
                    edges_max_flow.max_single_flow
                    for edges_max_flow in prev_hop_node_cap.edges_max_flow.values()
                ]
            )
            prev_hop_node_cap.max_total_flow = sum(
                [
                    edges_max_flow.max_total_flow
                    for edges_max_flow in prev_hop_node_cap.edges_max_flow.values()
                ]
            )
            node_capacities[prev_hop] = prev_hop_node_cap
            if prev_hop != src_node:
                queue.append(prev_hop)

    # Place a flow of 1.0 and see how it balances
    # BFS from the src to dst across the succ
    queue = deque([(src_node, 1, 1)])
    while queue:
        node, flow_fraction_total, flow_fraction_balanced = queue.popleft()
        node_capacities[node].flow_fraction_total += flow_fraction_total
        node_capacities[node].flow_fraction_balanced += flow_fraction_balanced
        for next_hop, edge_tuple in succ[node].items():
            if next_hop != dst_node:
                if node_capacities[node].max_total_flow > 0:
                    next_hop_flow_fraction_total = flow_fraction_total * (
                        node_capacities[node].edges_max_flow[edge_tuple].max_total_flow
                        / node_capacities[node].max_total_flow
                    )
                else:
                    next_hop_flow_fraction_total = 0
                next_hop_flow_fraction_balanced = (
                    flow_fraction_balanced
                    / len(node_capacities[node].edges)
                    * len(edge_tuple)
                )
                queue.append(
                    (
                        next_hop,
                        next_hop_flow_fraction_total,
                        next_hop_flow_fraction_balanced,
                    )
                )

    max_balanced_flow = min(
        [
            node.max_balanced_flow / node.flow_fraction_balanced
            for node in node_capacities.values()
        ]
    )
    max_flow = MaxFlow(
        node_capacities[src_node].max_total_flow,
        node_capacities[src_node].max_single_flow,
        max_balanced_flow,
    )
    return max_flow, node_capacities
