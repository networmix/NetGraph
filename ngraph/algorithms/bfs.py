from typing import Callable, Dict, Hashable, Tuple
from collections import deque

from ngraph.graph import MultiDiGraph
from ngraph.algorithms.common import edge_select_fabric, EdgeSelect


def bfs(
    graph: MultiDiGraph,
    src_node: Hashable,
    edge_select_func: Callable = edge_select_fabric(EdgeSelect.ALL_MIN_COST),
    multipath: bool = True,
) -> Tuple[Dict, Dict]:
    """
    Breadth-first search.
    """
    G_succ = graph.get_adj_out()
    costs = {src_node: 0}  # source node has has zero cost to itself
    pred = {src_node: {}}  # source node has no preceeding nodes
    queue = deque([(0, src_node)])
    visited_nodes = {src_node}
    while queue:
        src_to_node_cost, node_id = queue.popleft()
        visited_nodes.add(node_id)
        for neighbor_id, edges in G_succ[node_id].items():
            min_edge_cost, edges_list = edge_select_func(
                graph, node_id, neighbor_id, edges
            )

            if neighbor_id != src_node and edges_list:
                # neighbor is not the source node and we have selected edges
                src_to_neigh_cost = src_to_node_cost + min_edge_cost
                if neighbor_id not in costs or src_to_neigh_cost < costs[neighbor_id]:
                    # the first or better path found, updating minimal path cost
                    costs[neighbor_id] = src_to_neigh_cost

                    if not multipath:
                        pred[neighbor_id] = {node_id: edges_list}
                    else:
                        pred.setdefault(neighbor_id, {})[node_id] = edges_list

                elif multipath:
                    pred[neighbor_id][node_id] = edges_list

                if neighbor_id not in visited_nodes:
                    queue.append((src_to_neigh_cost, neighbor_id))
    return costs, pred
