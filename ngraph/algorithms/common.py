from typing import Any, Hashable, Optional, Set, Tuple, List, Dict, Callable, Generator

from ngraph.graph import MultiDiGraph


DEFAULT_COST_ATTRIBUTE = "metric"


def min_cost_edges_func_fabric(attr_to_use: str) -> Callable:
    """
    Fabric producing a function to find the min-cost edges between a pair of adjacent nodes in a graph.
    Args:
        attr_to_use: name of the integer attribute that will be used to determine the cost.
    Returns:
        get_min_cost_edges_func: a callable function
    """

    def get_min_cost_edges_func(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        """
        Returns the min-cost edges between a pair of adjacent nodes in a graph.
        Args:
            graph: MultiDiGraph object.
            src_node: node_id of the source node.
            dst_node: node_id of the destination node.
            edges: dict {edge_id: {edge_attr}}
        Returns:
            min_cost: minimal cost of the edge between src_node and dst_node
            edge_list: list of all edge_ids with the min_cost
        """
        edge_list = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            cost = edge_attributes[attr_to_use]

            if min_cost is None or cost < min_cost:
                min_cost = cost
                edge_list = [edge_id]
            elif cost == min_cost:
                edge_list.append(edge_id)

        return min_cost, edge_list

    return get_min_cost_edges_func


def resolve_paths_to_nodes_edges(
    src_node: Hashable, dst_node: Hashable, pred: Dict[Any, Dict[Any, List[int]]]
) -> Optional[Generator[Tuple, None, None]]:
    if dst_node not in pred:
        return
    pred = {
        node: [(nbr, nbr_edges) for nbr, nbr_edges in nbrs_dict.items()]
        for node, nbrs_dict in pred.items()
    }
    seen = {dst_node}
    stack = [[(dst_node, []), 0]]
    top = 0
    while top >= 0:
        node_edges, nbr_idx = stack[top]
        if node_edges[0] == src_node:
            yield tuple(node_edges for node_edges, _ in reversed(stack[: top + 1]))
        if len(pred[node_edges[0]]) > nbr_idx:
            stack[top][1] = nbr_idx + 1
            next_node_edges = pred[node_edges[0]][nbr_idx]
            if next_node_edges[0] in seen:
                continue
            else:
                seen.add(next_node_edges[0])
            top += 1
            if top == len(stack):
                stack.append([next_node_edges, 0])
            else:
                stack[top][:] = [next_node_edges, 0]
        else:
            seen.discard(node_edges[0])
            top -= 1
