from enum import IntEnum
from typing import Any, Dict, Hashable, List, Optional, Tuple, Generator
from ngraph.graph import MultiDiGraph
from ngraph.algorithms import spf, bfs, common


class PathAlgType(IntEnum):
    """
    Types of path finding algorithms
    """

    SPF = 1
    BFS = 2


def place_flow(
    residual_graph: MultiDiGraph,
    path: Tuple,
    flow: float = float("inf"),
    flow_index: Optional[str] = None,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> Tuple[float, float]:
    """
    Place flow along the given path from source to destinaton.
    """
    # Determine the path residual capacity.
    R_edges = residual_graph.get_edges()
    R_nodes = residual_graph.get_nodes()
    path_element_capacities = []
    max_flow = flow
    for node_id, edge_list in path[:-1]:
        remaining_capacity = 0
        for edge_id in edge_list:
            remaining_capacity += (
                R_edges[edge_id][3][capacity_attr] - R_edges[edge_id][3][flow_attr]
            )
        max_flow = min(max_flow, remaining_capacity)
        path_element_capacities.append(remaining_capacity)

    # Place flow along the path.
    for node_edge_list, remaining_capacity in zip(path, path_element_capacities):
        node_id, edge_list = node_edge_list
        R_nodes[node_id][flow_attr] = max_flow
        R_nodes[node_id][flows_attr][flow_index] = (path[0][0], path[-1][0], max_flow)
        for edge_id in edge_list:
            R_edges[edge_id][3][flow_attr] += (
                R_edges[edge_id][3][capacity_attr] / remaining_capacity * max_flow
            )
            R_edges[edge_id][3][flows_attr][flow_index] = (
                path[0][0],
                path[-1][0],
                max_flow,
            )
    residual_flow = flow - max_flow if flow != float("inf") else float("inf")
    return max_flow, max(residual_flow, 0)


def init_residual_graph(
    residual_graph: MultiDiGraph,
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    reset_residual_graph: bool = True,
) -> MultiDiGraph:
    for edge_tuple in residual_graph.get_edges().values():
        edge_tuple[3].setdefault(flow_attr, 0)
        if reset_residual_graph:
            edge_tuple[3][flow_attr] = 0
        edge_tuple[3].setdefault(flows_attr, {})

    for node_dict in residual_graph.get_nodes().values():
        node_dict.setdefault(flow_attr, 0)
        if reset_residual_graph:
            node_dict[flow_attr] = 0
        node_dict.setdefault(flows_attr, {})
    return residual_graph


def edmonds_karp(
    graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    cutoff: float = float("inf"),
    flow_index: Optional[str] = None,
    residual_graph: Optional[MultiDiGraph] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    shortest_path: bool = False,
    path_alg: PathAlgType = PathAlgType.SPF,
    reset_residual_graph: bool = True,
) -> Tuple[float, MultiDiGraph]:
    residual_graph = residual_graph if residual_graph is not None else graph.copy()
    init_residual_graph(
        residual_graph,
        flow_attr=flow_attr,
        flows_attr=flows_attr,
        reset_residual_graph=reset_residual_graph,
    )

    max_flow = edmonds_karp_core(
        residual_graph,
        src_node,
        dst_node,
        cutoff,
        flow_index,
        cost_attr,
        capacity_attr,
        flow_attr,
        shortest_path,
        path_alg,
    )
    return max_flow, residual_graph


def edmonds_karp_core(
    residual_graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    cutoff: float,
    flow_index: Optional[str] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    shortest_path: bool = False,
    path_alg: PathAlgType = PathAlgType.SPF,
) -> float:
    """
    Implementation of the Edmonds-Karp algorithm.
    """

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

    def get_bfs_path_iter() -> Optional[Generator]:
        _, pred = bfs.bfs(
            residual_graph, src_node=src_node, edge_selection_func=edge_selection_bfs
        )
        if dst_node in pred:
            return common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)

    def get_spf_path_iter() -> Optional[Generator]:
        _, pred = spf.spf(
            residual_graph, src_node=src_node, edge_selection_func=edge_selection_spf
        )
        if dst_node in pred:
            return common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)

    PATH_ALG_SEL = {
        PathAlgType.SPF: get_spf_path_iter,
        PathAlgType.BFS: get_bfs_path_iter,
    }

    get_path_iter = PATH_ALG_SEL[path_alg]
    flow_value = 0
    flow_to_place = cutoff
    while True:
        if (path_iter := get_path_iter()) is None:
            break
        for path in path_iter:
            placed_flow, flow_to_place = place_flow(
                residual_graph,
                path,
                flow=flow_to_place,
                flow_index=flow_index,
                capacity_attr=capacity_attr,
                flow_attr=flow_attr,
            )
            flow_value += placed_flow
            if not flow_to_place:
                break
        if shortest_path or not flow_to_place:
            break
    return flow_value
