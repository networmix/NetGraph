from enum import IntEnum
import math
from typing import Any, Dict, Hashable, List, Optional, Tuple, Generator
from ngraph.graph import MultiDiGraph
from ngraph.algorithms import spf, bfs, common


class PathAlgType(IntEnum):
    """
    Types of path finding algorithms
    """

    SPF = 1
    BFS = 2


class FlowPlacement(IntEnum):
    # load balancing across parallel edges proportional to remaining capacity
    PROPORTIONAL = 1
    # use edge with max remaining capacity, no load balancing across parallel edges
    MAX_SINGLE_FLOW = 2
    # equal load balancing across parallel edges
    MAX_BALANCED_FLOW = 3


from typing import NamedTuple


class PathElementCapacity(NamedTuple):
    total_cap: float
    max_edge_cap: float
    min_edge_cap: float
    max_edge_cap_id: int
    min_edge_cap_id: int
    total_rem_cap: float
    max_edge_rem_cap: float
    min_edge_rem_cap: float
    max_edge_rem_cap_id: int
    min_edge_rem_cap_id: int
    edge_count: int


class PathCapacity(NamedTuple):
    max_flow: float
    max_single_flow: float
    max_balanced_flow: float


def calc_path_capacity(
    residual_graph: MultiDiGraph,
    path: Tuple,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Tuple[PathCapacity, List[PathElementCapacity]]:
    """
    Determine capacity of a given path.
    """
    R_edges = residual_graph.get_edges()
    path_element_capacities: List[PathElementCapacity] = []
    max_flow = float("inf")
    max_single_flow = float("inf")
    max_balanced_flow = float("inf")

    for node_id, edge_tuple in path[:-1]:
        edge_cap_list = [R_edges[edge_id][3][capacity_attr] for edge_id in edge_tuple]
        edge_rem_cap_list = [
            R_edges[edge_id][3][capacity_attr] - R_edges[edge_id][3][flow_attr]
            for edge_id in edge_tuple
        ]

        total_cap = sum(edge_cap_list)
        max_edge_cap = max(edge_cap_list)
        min_edge_cap = min(edge_cap_list)
        max_edge_cap_id = edge_cap_list.index(max_edge_cap)
        min_edge_cap_id = edge_cap_list.index(min_edge_cap)
        total_rem_cap = sum(edge_rem_cap_list)
        max_edge_rem_cap = max(edge_rem_cap_list)
        min_edge_rem_cap = min(edge_rem_cap_list)
        max_edge_rem_cap_id = edge_rem_cap_list.index(max_edge_rem_cap)
        min_edge_rem_cap_id = edge_rem_cap_list.index(min_edge_rem_cap)
        edge_count = len(edge_cap_list)

        path_element_capacities.append(
            PathElementCapacity(
                total_cap,
                max_edge_cap,
                min_edge_cap,
                max_edge_cap_id,
                min_edge_cap_id,
                total_rem_cap,
                max_edge_rem_cap,
                min_edge_rem_cap,
                max_edge_rem_cap_id,
                min_edge_rem_cap_id,
                edge_count,
            )
        )

        max_flow = min(max_flow, total_rem_cap)
        max_single_flow = min(max_flow, max_edge_rem_cap)
        max_balanced_flow = min(max_flow, min_edge_rem_cap * edge_count)
    return (
        PathCapacity(max_flow, max_single_flow, max_balanced_flow),
        path_element_capacities,
    )


def calc_capacity_balanced(
    residual_graph: MultiDiGraph,
    path_iter: Generator,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Tuple[float, int]:
    total_subflow_count = 0
    total_cap = 0
    for flow_idx, path in enumerate(path_iter):
        path_subflow_count = math.prod([len(edges) for _, edges in path[:-1]])
        total_subflow_count += path_subflow_count
        placed_flow, _ = place_flow(
            residual_graph,
            path,
            float("inf"),
            flow_idx,
            capacity_attr,
            flow_attr,
            flow_placement=FlowPlacement.MAX_BALANCED_FLOW,
        )
        total_cap += placed_flow
    return total_cap, total_subflow_count


def place_flow_balanced(
    residual_graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    flow: float = float("inf"),
    flow_index: Optional[Any] = None,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> Tuple[float, float]:

    _, pred = spf.spf(residual_graph, src_node)
    tmp_residual_graph = init_residual_graph(residual_graph.copy())
    max_flow, total_subflow_count = calc_capacity_balanced(
        tmp_residual_graph,
        common.resolve_paths_to_nodes_edges(src_node, dst_node, pred),
        capacity_attr,
        flow_attr,
    )
    flow_index = flow_index if flow_index is not None else (src_node, dst_node)
    path_iter = common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)
    R_edges = residual_graph.get_edges()
    R_nodes = residual_graph.get_nodes()

    placed_flow = min(max_flow, flow)
    remaining_flow = max(flow - max_flow if flow != float("inf") else float("inf"), 0)

    for path in path_iter:
        path_subflow_count = math.prod([len(edges) for _, edges in path[:-1]])
        placed_subflows = placed_flow / total_subflow_count * path_subflow_count
        for node_edge_tuple in path[:-1]:
            node_id, edge_tuple = node_edge_tuple
            R_nodes[node_id][flow_attr] = placed_subflows
            R_nodes[node_id][flows_attr][flow_index] = (
                src_node,
                dst_node,
                placed_subflows,
            )
            subflow_fraction = placed_subflows / len(edge_tuple)
            for edge_id in edge_tuple:
                R_edges[edge_id][3][flow_attr] += subflow_fraction
                R_edges[edge_id][3][flows_attr][flow_index] = (
                    src_node,
                    dst_node,
                    subflow_fraction,
                )
    return placed_flow, remaining_flow


def place_flow(
    residual_graph: MultiDiGraph,
    path: Tuple,
    flow: float = float("inf"),
    flow_index: Optional[Any] = None,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
) -> Tuple[float, float]:
    """
    Place flow along the given path from source to destinaton.
    """
    # Determine remaining path capacity
    path_capacity, path_element_capacities = calc_path_capacity(
        residual_graph, path, capacity_attr, flow_attr
    )

    # Place flow along the path
    if flow_placement == FlowPlacement.PROPORTIONAL:
        max_flow = path_capacity.max_flow
    elif flow_placement == FlowPlacement.MAX_SINGLE_FLOW:
        max_flow = path_capacity.max_single_flow
    elif flow_placement == FlowPlacement.MAX_BALANCED_FLOW:
        max_flow = path_capacity.max_balanced_flow
    else:
        raise RuntimeError(f"Unknown flow_placement {flow_placement}")

    remaining_flow = max(flow - max_flow if flow != float("inf") else float("inf"), 0)
    placed_flow = min(max_flow, flow)
    if not placed_flow > 0:
        return 0, flow

    flow_src = path[0][0]
    flow_dst = path[-1][0]
    flow_index = flow_index if flow_index is not None else (flow_src, flow_dst)
    R_edges = residual_graph.get_edges()
    R_nodes = residual_graph.get_nodes()
    for node_edge_tuple, path_element_cap in zip(path, path_element_capacities):
        node_id, edge_tuple = node_edge_tuple
        R_nodes[node_id][flow_attr] = placed_flow
        R_nodes[node_id][flows_attr][flow_index] = (
            flow_src,
            flow_dst,
            placed_flow,
        )
        for edge_id in edge_tuple:
            if flow_placement == FlowPlacement.PROPORTIONAL:
                flow_fraction = (
                    placed_flow
                    / path_element_cap.total_rem_cap
                    * (
                        R_edges[edge_id][3][capacity_attr]
                        - R_edges[edge_id][3][flow_attr]
                    )
                )
            elif flow_placement == FlowPlacement.MAX_SINGLE_FLOW:
                flow_fraction = (
                    placed_flow
                    if edge_id == path_element_cap.max_edge_rem_cap_id
                    else 0
                )

            elif flow_placement == FlowPlacement.MAX_BALANCED_FLOW:
                flow_fraction = (
                    path_element_cap.min_edge_rem_cap * path_element_cap.edge_count
                )
            if flow_fraction:
                R_edges[edge_id][3][flow_attr] += flow_fraction
                R_edges[edge_id][3][flows_attr][flow_index] = (
                    flow_src,
                    flow_dst,
                    flow_fraction,
                )
    return placed_flow, remaining_flow


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


def calc_max_flow(
    graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    cutoff: float = float("inf"),
    residual_graph: Optional[MultiDiGraph] = None,
    cost_attr: str = "metric",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    shortest_path: bool = False,
    shortest_path_balanced: bool = False,
    path_alg: PathAlgType = PathAlgType.BFS,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    reset_residual_graph: bool = True,
) -> Tuple[float, MultiDiGraph]:
    residual_graph = residual_graph if residual_graph is not None else graph.copy()
    init_residual_graph(
        residual_graph,
        flow_attr=flow_attr,
        flows_attr=flows_attr,
        reset_residual_graph=reset_residual_graph,
    )

    if shortest_path_balanced:
        max_flow, _ = place_flow_balanced(
            residual_graph,
            src_node,
            dst_node,
            flow=float("inf"),
            flow_index=(src_node, dst_node, 0),
            capacity_attr=capacity_attr,
            flow_attr=flow_attr,
            flows_attr=flows_attr,
        )
        return max_flow, residual_graph

    max_flow = edmonds_karp_core(
        residual_graph,
        src_node,
        dst_node,
        cutoff,
        cost_attr,
        capacity_attr,
        flow_attr,
        shortest_path,
        path_alg,
        flow_placement,
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
    path_alg: PathAlgType = PathAlgType.BFS,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
) -> float:
    """
    Implementation of the Edmonds-Karp algorithm.
    """

    def edge_selection_bfs(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        edge_tuple = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            if edge_attributes[flow_attr] < edge_attributes[capacity_attr]:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                edge_tuple.append(edge_id)
        return min_cost, edge_tuple

    def edge_selection_spf(
        graph: MultiDiGraph, src_node: Hashable, dst_node: Hashable, edges: Dict
    ) -> Tuple[int, List[int]]:
        edge_tuple = []
        min_cost = None
        for edge_id, edge_attributes in edges.items():
            if edge_attributes[flow_attr] < edge_attributes[capacity_attr]:
                cost = edge_attributes[cost_attr]

                if min_cost is None or cost < min_cost:
                    min_cost = cost
                    edge_tuple = [edge_id]
                elif cost == min_cost:
                    edge_tuple.append(edge_id)

        return min_cost, edge_tuple

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
    flow_idx = 0
    while True:
        if (path_iter := get_path_iter()) is None:
            break
        for path in path_iter:
            placed_flow, flow_to_place = place_flow(
                residual_graph,
                path,
                flow=flow_to_place,
                flow_index=flow_idx,
                capacity_attr=capacity_attr,
                flow_attr=flow_attr,
                flow_placement=flow_placement,
            )
            flow_value += placed_flow
            flow_idx += 1
            if not flow_to_place:
                break
        if shortest_path or not flow_to_place:
            break
    return flow_value
