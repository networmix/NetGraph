from enum import IntEnum
from itertools import product
from typing import Any, Iterator, Optional, Tuple, List, Dict, Callable, Union

from ngraph.graph import (
    AttrDict,
    DstNodeID,
    EdgeID,
    MultiDiGraph,
    NodeID,
    SrcNodeID,
)


Cost = Union[int, float]
PathElement = Tuple[NodeID, Tuple[EdgeID]]
PathTuple = Tuple[PathElement]
MIN_CAP = 2 ** (-12)


class EdgeSelect(IntEnum):
    """
    Edge selection criteria
    """

    ALL_MIN_COST = 1
    ALL_MIN_COST_WITH_CAP_REMAINING = 2
    ALL_ANY_COST_WITH_CAP_REMAINING = 3
    SINGLE_MIN_COST = 4
    SINGLE_MIN_COST_WITH_CAP_REMAINING = 5
    USER_DEFINED = 99


class EdgeFilter(IntEnum):
    """
    Edge filtering criteria
    """

    CAP_REMAINING = 1
    COST_LT = 2
    USER_DEFINED = 99


def init_flow_graph(
    flow_graph: MultiDiGraph,
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    reset_flow_graph: bool = True,
) -> MultiDiGraph:
    for edge_tuple in flow_graph.get_edges().values():
        edge_tuple[3].setdefault(flow_attr, 0)
        edge_tuple[3].setdefault(flows_attr, {})
        if reset_flow_graph:
            edge_tuple[3][flow_attr] = 0
            edge_tuple[3][flows_attr] = {}

    for node_dict in flow_graph.get_nodes().values():
        node_dict.setdefault(flow_attr, 0)
        node_dict.setdefault(flows_attr, {})
        if reset_flow_graph:
            node_dict[flow_attr] = 0
            node_dict[flows_attr] = {}
    return flow_graph


def edge_select_fabric(
    edge_select: EdgeSelect,
    select_value: Optional[Any] = None,
    edge_select_func: Optional[
        Callable[
            [MultiDiGraph, SrcNodeID, DstNodeID, Dict[EdgeID, AttrDict]],
            Tuple[Cost, List[EdgeID]],
        ]
    ] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Callable[
    [MultiDiGraph, SrcNodeID, DstNodeID, Dict[EdgeID, AttrDict]],
    Tuple[Cost, List[EdgeID]],
]:
    """
    Fabric producing a function to select edges between a pair of adjacent nodes in a graph.

    Args:
        edge_select: EdgeSelect enum with selection criteria
        edge_select_func: Optional user-defined function
        cost_attr: name of the integer attribute that will be used to determine the cost.
        capacity_attr:
        flow_attr:
    Returns:
        get_min_cost_edges_func: a callable function returning a list of selected edges
    """

    def get_all_min_cost_edges(
        graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        edges: Dict[EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        """
        Returns all min-cost edges between a pair of adjacent nodes in a graph.
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

    def get_single_min_cost_edge(
        graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        edges: Dict[EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        """
        Returns a list containing a single min-cost edge between a pair of adjacent nodes in a graph.
        Args:
            graph: MultiDiGraph object.
            src_node: node_id of the source node.
            dst_node: node_id of the destination node.
            edges: dict {edge_id: {edge_attr}}
        Returns:
            min_cost: minimal cost of the edge between src_node and dst_node
            edge_list: a list with the edge_id of the min_cost edge
        """
        edge_list = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            cost = edge_attributes[cost_attr]

            if min_cost is None or cost < min_cost:
                min_cost = cost
                edge_list = [edge_id]

        return min_cost, edge_list

    def get_all_edges_with_cap_remaining(
        graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        edges: Dict[EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        edge_list = []
        min_cost = None
        min_cap = select_value if select_value is not None else MIN_CAP
        for edge_id, edge_attributes in edges.items():
            if (edge_attributes[capacity_attr] - edge_attributes[flow_attr]) > min_cap:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                edge_list.append(edge_id)
        return min_cost, edge_list

    def get_all_min_cost_edges_with_cap_remaining(
        graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        edges: Dict[EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        edge_list = []
        min_cost = None
        min_cap = select_value if select_value is not None else MIN_CAP
        for edge_id, edge_attributes in edges.items():
            if (edge_attributes[capacity_attr] - edge_attributes[flow_attr]) > min_cap:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                    edge_list = [edge_id]
                elif cost == min_cost:
                    edge_list.append(edge_id)
        return min_cost, edge_list

    def get_single_min_cost_edge_with_cap_remaining(
        graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        edges: Dict[EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        edge_list = []
        min_cost = None
        min_cap = select_value if select_value is not None else MIN_CAP
        for edge_id, edge_attributes in edges.items():
            if (edge_attributes[capacity_attr] - edge_attributes[flow_attr]) > min_cap:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                    edge_list = [edge_id]
        return min_cost, edge_list

    if edge_select == EdgeSelect.ALL_MIN_COST:
        return get_all_min_cost_edges
    elif edge_select == EdgeSelect.SINGLE_MIN_COST:
        return get_single_min_cost_edge
    elif edge_select == EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING:
        return get_all_min_cost_edges_with_cap_remaining
    elif edge_select == EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING:
        return get_all_edges_with_cap_remaining
    elif edge_select == EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING:
        return get_single_min_cost_edge_with_cap_remaining
    elif edge_select == EdgeSelect.USER_DEFINED:
        return edge_select_func


def edge_filter_fabric(
    edge_filter: EdgeFilter,
    filter_value: Optional[Any] = None,
    edge_filter_func: Optional[Callable[[Tuple[EdgeID, AttrDict]], bool]] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Callable[[Tuple[EdgeID, AttrDict]], bool]:
    """
    Fabric producing a function to filter edges out from a graph.

    Args:
        edge_filter: EdgeFilter enum with filter criteria
        edge_filter_func: Optional user-defined function
        cost_attr: name of the cost attribute
        capacity_attr: name of the capacity attribute
        flow_attr: name of the flow attribute
    Returns:
        edge_filter_func: a callable function returning a boolean (False - remove a given edge)
    """

    def edges_with_cap_remaining(
        edge_id: EdgeID,
        edge_tuple: Tuple[SrcNodeID, DstNodeID, EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        edge_attributes = edge_tuple[-1]
        return (
            edge_attributes[capacity_attr] - edge_attributes[flow_attr] >= filter_value
        )

    def edges_with_cost_lt(
        edge_id: EdgeID,
        edge_tuple: Tuple[SrcNodeID, DstNodeID, EdgeID, AttrDict],
    ) -> Tuple[Cost, List[int]]:
        edge_attributes = edge_tuple[-1]
        return edge_attributes[cost_attr] < filter_value

    if edge_filter == EdgeFilter.CAP_REMAINING:
        return edges_with_cap_remaining
    elif edge_filter == EdgeFilter.COST_LT:
        return edges_with_cost_lt
    elif edge_filter == EdgeFilter.USER_DEFINED:
        return edge_filter_func


def resolve_to_paths(
    src_node: SrcNodeID,
    dst_node: DstNodeID,
    pred: Dict[DstNodeID, Dict[SrcNodeID, List[EdgeID]]],
    split_parallel_edges: bool = False,
) -> Optional[Iterator[PathTuple]]:
    """
    Resolve a directed acyclic graph of predecessors into individual paths between
    src_node and dst_node.

    Args:
        src_node: node_id of the source node.
        dst_node: node_id of the destination node.
        pred: predecessors encoded as {dst_node: {src_node: [edge_ids]}}
        split_parallel_edges: if True split parallel edges into separate paths
    Returns:
        An iterator iterating over all paths between src_node and dst_node.
        A path is a tuple of tuples: ((node_id, (edge_ids)), (node_id, (edge_ids))...)
    """
    if dst_node not in pred:
        return
    pred: Dict[DstNodeID, List[Tuple[SrcNodeID, Tuple[EdgeID]]]] = {
        node: [(nbr, tuple(nbr_edges)) for nbr, nbr_edges in nbrs_dict.items()]
        for node, nbrs_dict in pred.items()
    }
    seen = {dst_node}
    stack = [[(dst_node, tuple()), 0]]
    top_pointer = 0
    while top_pointer >= 0:
        node_edges, nbr_idx = stack[top_pointer]
        if node_edges[0] == src_node:
            node_edges_path = tuple(
                node_edges for node_edges, _ in reversed(stack[: top_pointer + 1])
            )
            if not split_parallel_edges:
                yield node_edges_path
            else:
                for edge_seq in product(
                    *[range(len(node_edges[1])) for node_edges in node_edges_path[:-1]]
                ):
                    yield tuple(
                        (
                            node_edges[0],
                            (node_edges[1][edge_seq[idx]],)
                            if len(edge_seq) > idx
                            else tuple(),
                        )
                        for idx, node_edges in enumerate(node_edges_path)
                    )

        if len(pred[node_edges[0]]) > nbr_idx:
            stack[top_pointer][1] = nbr_idx + 1
            next_node_edges = pred[node_edges[0]][nbr_idx]
            if next_node_edges[0] in seen:
                continue
            else:
                seen.add(next_node_edges[0])
            top_pointer += 1
            if top_pointer == len(stack):
                stack.append([next_node_edges, 0])
            else:
                stack[top_pointer][:] = [next_node_edges, 0]
        else:
            seen.discard(node_edges[0])
            top_pointer -= 1
