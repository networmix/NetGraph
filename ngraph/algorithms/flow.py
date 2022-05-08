from typing import Dict, Hashable, List, Optional, Tuple
from ngraph.graph import MultiDiGraph
from ngraph.algorithms import spf, bfs, common


def edmonds_karp(
    graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    cutoff: float = float("inf"),
    residual_graph: Optional[MultiDiGraph] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    shortest_path: bool = False,
) -> Tuple[float, MultiDiGraph]:
    residual_graph = residual_graph if residual_graph is not None else graph.copy()
    for edge_tuple in residual_graph.get_edges().values():
        edge_tuple[3][flow_attr] = 0
    max_flow = edmonds_karp_core(
        residual_graph,
        src_node,
        dst_node,
        cutoff,
        cost_attr,
        capacity_attr,
        flow_attr,
        shortest_path,
    )
    return max_flow, residual_graph


def edmonds_karp_core(
    residual_graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    cutoff: float,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    shortest_path: bool = False,
) -> float:
    """
    Implementation of the Edmonds-Karp algorithm.
    """

    R_edges = residual_graph.get_edges()
    inf = float("inf")

    def augment(path):
        """
        Augment flow along a path from source to destinaton.
        """
        # Determine the path residual capacity.
        edge_list_capacities = []
        flow = inf
        for _, edge_list in path[:-1]:
            remaining_edge_list_capacity = 0
            for edge_id in edge_list:
                remaining_edge_list_capacity += (
                    R_edges[edge_id][3][capacity_attr] - R_edges[edge_id][3][flow_attr]
                )
            flow = min(flow, remaining_edge_list_capacity)
            edge_list_capacities.append(remaining_edge_list_capacity)

        # Augment flow along the path.
        for node_edge_list, remaining_edge_list_capacity in zip(
            path, edge_list_capacities
        ):
            _, edge_list = node_edge_list
            for edge_id in edge_list:
                R_edges[edge_id][3][flow_attr] += (
                    R_edges[edge_id][3][capacity_attr]
                    / remaining_edge_list_capacity
                    * flow
                )
        return flow

    def edge_selection_bfs(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        edge_list = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            if edge_attributes[flow_attr] < edge_attributes[capacity_attr]:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                edge_list.append(edge_id)
        return min_cost, edge_list

    def edge_selection_spf(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        edge_list = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            if edge_attributes[flow_attr] < edge_attributes[capacity_attr]:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                    edge_list = [edge_id]
                elif cost == min_cost:
                    edge_list.append(edge_id)

        return min_cost, edge_list

    def get_bfs_path_iter():
        _, pred = bfs.bfs(
            residual_graph, src_node=src_node, edge_selection_func=edge_selection_bfs
        )
        if dst_node in pred:
            return common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)

    def get_spf_path_iter():
        _, pred = spf.spf(
            residual_graph, src_node=src_node, edge_selection_func=edge_selection_spf
        )
        if dst_node in pred:
            return common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)

    get_path_iter = get_bfs_path_iter if not shortest_path else get_spf_path_iter
    flow_value = 0
    while flow_value < cutoff:
        if (path_iter := get_path_iter()) is None:
            break
        for path in path_iter:
            flow_value += augment(path)
        if shortest_path:
            break
    return flow_value
