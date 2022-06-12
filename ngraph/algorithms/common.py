from enum import IntEnum
from typing import Any, Hashable, Optional, Set, Tuple, List, Dict, Callable, Generator

from ngraph.graph import MultiDiGraph


MIN_CAP = 2 ** (-12)


class EdgeFind(IntEnum):
    """
    Edge finding criteria
    """

    MIN_CAP = 1
    MIN_CAP_REMAINING_NON_ZERO = 2


class EdgeSelect(IntEnum):
    """
    Edge selection criteria
    """

    ALL_MIN_COST = 1
    ALL_MIN_COST_WITH_CAP_REMAINING = 2
    ALL_ANY_COST_WITH_CAP_REMAINING = 3
    USER_DEFINED = 99


def edge_select_fabric(
    edge_select: EdgeSelect,
    edge_select_func: Optional[Callable] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Callable:
    """
    Fabric producing a function to find the min-cost edges between a pair of adjacent nodes in a graph.
    Args:
        cost_attr: name of the integer attribute that will be used to determine the cost.
    Returns:
        get_min_cost_edges_func: a callable function
    """

    def get_min_cost_edges(
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
            cost = edge_attributes[cost_attr]

            if min_cost is None or cost < min_cost:
                min_cost = cost
                edge_list = [edge_id]
            elif cost == min_cost:
                edge_list.append(edge_id)

        return min_cost, edge_list

    def get_edges_with_cap(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        edge_list = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            if (edge_attributes[capacity_attr] - edge_attributes[flow_attr]) > MIN_CAP:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                edge_list.append(edge_id)
        return min_cost, edge_list

    def get_min_cost_edges_with_cap_rem(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        edge_list = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            if (edge_attributes[capacity_attr] - edge_attributes[flow_attr]) > MIN_CAP:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                    edge_list = [edge_id]
                elif cost == min_cost:
                    edge_list.append(edge_id)
        return min_cost, edge_list

    if edge_select == EdgeSelect.ALL_MIN_COST:
        return get_min_cost_edges
    elif edge_select == EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING:
        return get_min_cost_edges_with_cap_rem
    elif edge_select == EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING:
        return get_edges_with_cap
    elif edge_select == EdgeSelect.USER_DEFINED:
        return edge_select_func


def edge_find_fabric(
    edge_find: EdgeFind,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Callable:
    """
    Fabric producing a function to find required edges
    """

    def get_min_cap_edges(
        flow_graph: MultiDiGraph,
    ) -> Tuple:
        min_cap_edges = []
        min_cap = float("inf")
        for edge_tuple in flow_graph.get_edges().values():
            edge_attr = edge_tuple[3]
            if not edge_filter(edge_attr):
                continue
            if (
                cap := get_cap_func(edge_attr[capacity_attr], edge_attr[flow_attr])
            ) < min_cap:
                min_cap = cap
                min_cap_edges = [edge_tuple]
            elif cap == min_cap:
                min_cap_edges.append(edge_tuple)
        return min_cap, min_cap_edges

    if edge_find == EdgeFind.MIN_CAP:
        edge_filter: Callable[[Dict], bool] = lambda edge_attr: True
        get_cap_func: Callable[[float, float], float] = lambda cap, _: cap
        return get_min_cap_edges

    elif edge_find == EdgeFind.MIN_CAP_REMAINING_NON_ZERO:
        edge_filter: Callable[[Dict], bool] = (
            lambda edge_attr: (edge_attr[capacity_attr] - edge_attr[flow_attr])
            > MIN_CAP
        )
        get_cap_func: Callable[[float, float], float] = lambda cap, flow: cap - flow
        return get_min_cap_edges


def resolve_paths_to_nodes_edges(
    src_node: Hashable, dst_node: Hashable, pred: Dict[Any, Dict[Any, List[int]]]
) -> Optional[Generator[Tuple, None, None]]:
    if dst_node not in pred:
        return
    pred = {
        node: [(nbr, tuple(nbr_edges)) for nbr, nbr_edges in nbrs_dict.items()]
        for node, nbrs_dict in pred.items()
    }
    seen = {dst_node}
    stack = [[(dst_node, tuple()), 0]]
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
