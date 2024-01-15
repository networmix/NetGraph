from heapq import heappop, heappush
from typing import Iterator, List, Optional, Set, Tuple, Dict, Callable

from ngraph.lib.graph import (
    AttrDict,
    NodeID,
    EdgeID,
    MultiDiGraph,
)
from ngraph.lib.common import (
    Cost,
    edge_select_fabric,
    EdgeSelect,
    resolve_to_paths,
)


def spf(
    graph: MultiDiGraph,
    src_node: NodeID,
    edge_select_func: Callable[
        [MultiDiGraph, NodeID, NodeID, Dict[EdgeID, AttrDict]],
        Tuple[Cost, List[EdgeID]],
    ] = edge_select_fabric(EdgeSelect.ALL_MIN_COST),
    multipath: bool = True,
    excluded_edges: Optional[Set[EdgeID]] = None,
    excluded_nodes: Optional[Set[NodeID]] = None,
) -> Tuple[Dict[NodeID, Cost], Dict[NodeID, Dict[NodeID, List[EdgeID]]]]:
    """
    Implementation of the Dijkstra's Shortest Path First algorithm for finding shortest paths in the graph.
    Implemented using a min-priority queue.

    Args:
        src_node: source node identifier.
        edge_select_func: function to select the edges between a pair of nodes
        multipath: if True multiple equal-cost paths to the same destination node are allowed
    Returns:
        costs: a dict with destination nodes mapped into the cost of the shortest path to that destination
        pred: a dict with nodes mapped into their preceeding nodes (predecessors) and edges
    """

    # Initialization
    excluded_edges = excluded_edges or set()
    excluded_nodes = excluded_nodes or set()
    outgoing_adjacencies = graph._adj
    min_pq = []  # min-priority queue
    costs: Dict[NodeID, Cost] = {src_node: 0}  # source node has has zero cost to itself
    pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]] = {
        src_node: {}
    }  # source node has no preceeding nodes

    heappush(
        min_pq, (0, src_node)
    )  # push source node onto the min-priority queue using cost as priority

    while min_pq:
        # pop the node with the minimal cost from the source node
        src_to_node_cost, node_id = heappop(min_pq)

        # iterate over all the neighbors of the node we're looking at
        for neighbor_id, edges in outgoing_adjacencies[node_id].items():
            # select the edges between the node and its neighbor
            min_edge_cost, edges_list = edge_select_func(
                graph, node_id, neighbor_id, edges, excluded_edges, excluded_nodes
            )

            if edges_list:
                src_to_neigh_cost = src_to_node_cost + min_edge_cost

                if neighbor_id not in costs or src_to_neigh_cost < costs[neighbor_id]:
                    # have not seen this neighbor yet or better path found
                    costs[neighbor_id] = src_to_neigh_cost
                    pred[neighbor_id] = {node_id: edges_list}
                    heappush(min_pq, (src_to_neigh_cost, neighbor_id))

                elif multipath and costs[neighbor_id] == src_to_neigh_cost:
                    # have met this neighbor, but new equal cost path found
                    pred[neighbor_id][node_id] = edges_list

    return costs, pred


def ksp(
    graph: MultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    edge_select_func: Callable[
        [MultiDiGraph, NodeID, NodeID, Dict[EdgeID, AttrDict]],
        Tuple[Cost, List[EdgeID]],
    ] = edge_select_fabric(EdgeSelect.ALL_MIN_COST),
    max_k: Optional[int] = None,
    max_path_cost: Optional[Cost] = float("inf"),
    max_path_cost_factor: Optional[float] = None,
    multipath: bool = True,
    excluded_edges: Optional[Set[EdgeID]] = None,
    excluded_nodes: Optional[Set[NodeID]] = None,
) -> Iterator[Tuple[Dict[NodeID, Cost], Dict[NodeID, Dict[NodeID, List[EdgeID]]]]]:
    """
    Implementation of the Yen's algorithm for finding k shortest paths in the graph.
    """
    excluded_edges = excluded_edges or set()
    excluded_nodes = excluded_nodes or set()

    shortest_paths = []  # container A
    candidates = []  # container B, heap-based
    visited = set()

    costs, pred = spf(graph, src_node, edge_select_func, multipath)
    if dst_node not in pred:
        return

    shortest_path_cost = costs[dst_node]
    if max_path_cost_factor:
        max_path_cost = min(max_path_cost, shortest_path_cost * max_path_cost_factor)

    if shortest_path_cost > max_path_cost:
        return

    shortest_paths.append((costs, pred, excluded_edges.copy(), excluded_nodes.copy()))
    yield costs, pred

    candidate_id = 0
    while True:
        if max_k and len(shortest_paths) >= max_k:
            break

        root_costs, root_pred, excluded_edges, excluded_nodes = shortest_paths[-1]
        for path in resolve_to_paths(src_node, dst_node, root_pred):
            # iterate over each concrete path in the last shortest path

            for idx, spur_tuple in enumerate(path[:-1]):
                # iterate over each node in the path, except the last one

                spur_node, edges_list = spur_tuple
                root_path = path[:idx]
                excluded_edges_tmp = excluded_edges.copy()
                excluded_nodes_tmp = excluded_nodes.copy()

                # remove the edges of the spur node that were used in the previous paths
                # also remove all the nodes that are on the current root path up to the spur node (loop avoidance)
                for (
                    path_costs,
                    path_pred,
                    path_excluded_edges,
                    path_excluded_nodes,
                ) in shortest_paths:
                    for p in resolve_to_paths(src_node, dst_node, path_pred):
                        if p[:idx] == root_path:
                            excluded_edges_tmp.update(path_excluded_edges)
                            excluded_edges_tmp.update(p[idx][1])
                            excluded_nodes_tmp.update(path_excluded_nodes)
                            excluded_nodes_tmp.update(
                                node_edges[0] for node_edges in p[:idx]
                            )

                # calculate the shortest path from the spur node to the destination
                spur_costs, spur_pred = spf(
                    graph,
                    spur_node,
                    edge_select_func,
                    multipath,
                    excluded_edges_tmp,
                    excluded_nodes_tmp,
                )

                if dst_node in spur_pred:
                    spur_cost = root_costs[spur_node]
                    for k, v in spur_costs.items():
                        spur_costs[k] = v + spur_cost
                    total_costs = {k: v for k, v in root_costs.items()}
                    total_costs.update(spur_costs)

                    total_pred = {k: v for k, v in root_pred.items()}
                    for k, v in spur_pred.items():
                        if k != spur_node:
                            total_pred[k] = v

                    edge_ids = tuple(
                        sorted(
                            [
                                edge_id
                                for _, v1 in total_pred.items()
                                for _, edge_list in v1.items()
                                for edge_id in edge_list
                            ]
                        )
                    )
                    if edge_ids not in visited:
                        if total_costs[dst_node] > max_path_cost:
                            continue

                        # add the path to the candidates
                        heappush(
                            candidates,
                            (
                                total_costs[dst_node],
                                candidate_id,
                                total_costs,
                                total_pred,
                                excluded_edges_tmp,
                                excluded_nodes_tmp,
                            ),
                        )
                        visited.add(edge_ids)
                        candidate_id += 1

        if not candidates:
            break
        # select the best candidate
        _, _, costs, pred, excluded_edges_tmp, excluded_nodes_tmp = heappop(candidates)
        shortest_paths.append((costs, pred, excluded_edges_tmp, excluded_nodes_tmp))
        yield costs, pred
