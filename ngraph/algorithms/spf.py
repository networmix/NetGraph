from heapq import heappop, heappush
from typing import Hashable, Tuple, Dict, Callable

from ngraph.graph import MultiDiGraph
from ngraph.algorithms.common import min_cost_edges_func_fabric, DEFAULT_COST_ATTRIBUTE


def spf(
    graph: MultiDiGraph,
    src_node: Hashable,
    edge_selection_func: Callable = min_cost_edges_func_fabric(DEFAULT_COST_ATTRIBUTE),
) -> Tuple[Dict, Dict]:
    """
    Implementation of the Dijkstra's Shortest Path First algorithm for finding shortest paths in the graph.
    Implemented using a min-priority queue:
    https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm#Using_a_priority_queue
    Args:
        src_node: source node identifier.
    Returns:
        costs: a dict with destination nodes mapped into the cost of the shortest path to that destination
        pred: a dict with nodes mapped into their preceeding nodes (predecessors) and edges
    """

    # Initialization
    G_succ = graph.get_adj_out()
    min_pq = []  # min-priority queue
    costs = {src_node: 0}  # source node has has zero cost to itself
    pred = {src_node: {}}  # source node has no preceeding nodes

    heappush(
        min_pq, (0, src_node)
    )  # push source node onto the min-priority queue using cost as priority

    while min_pq:
        # pop the node with the minimal cost from the source node
        src_to_node_cost, node_id = heappop(min_pq)

        # iterate over all the neighbors of the node we're looking at
        for neighbor_id, edges in G_succ[node_id].items():
            min_edge_cost, edges_list = edge_selection_func(
                graph, node_id, neighbor_id, edges
            )

            if edges_list:
                src_to_neigh_cost = src_to_node_cost + min_edge_cost

                if neighbor_id not in costs or src_to_neigh_cost < costs[neighbor_id]:
                    # have not seen this neighbor yet or better path found
                    costs[neighbor_id] = src_to_neigh_cost
                    pred[neighbor_id] = {node_id: edges_list}
                    heappush(min_pq, (src_to_neigh_cost, neighbor_id))

                elif costs[neighbor_id] == src_to_neigh_cost:
                    # have met this neighbor, but new equal cost path found
                    pred[neighbor_id][node_id] = edges_list

    return costs, pred
