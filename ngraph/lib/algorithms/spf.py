from heapq import heappop, heappush
from typing import (
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)
from ngraph.lib.graph import (
    AttrDict,
    NodeID,
    EdgeID,
    StrictMultiDiGraph,
)
from ngraph.lib.algorithms.base import (
    Cost,
    EdgeSelect,
)
from ngraph.lib.algorithms.edge_select import edge_select_fabric
from ngraph.lib.algorithms.path_utils import resolve_to_paths


def spf(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    edge_select_func: Callable[
        [
            StrictMultiDiGraph,
            NodeID,
            NodeID,
            Dict[EdgeID, AttrDict],
            Set[EdgeID],
            Set[NodeID],
        ],
        Tuple[Cost, List[EdgeID]],
    ] = edge_select_fabric(EdgeSelect.ALL_MIN_COST),
    multipath: bool = True,
    excluded_edges: Optional[Set[EdgeID]] = None,
    excluded_nodes: Optional[Set[NodeID]] = None,
) -> Tuple[Dict[NodeID, Cost], Dict[NodeID, Dict[NodeID, List[EdgeID]]]]:
    """
    Compute shortest paths (and their costs) from a source node using Dijkstra's algorithm.

    This function implements a single-source shortest-path (Dijkstra’s) algorithm
    that can optionally allow multiple equal-cost paths to the same destination
    if ``multipath=True``. It uses a min-priority queue to efficiently retrieve
    the next closest node to expand. Excluded edges or excluded nodes can be
    supplied to remove them from path consideration.

    Args:
        graph: The directed graph (StrictMultiDiGraph) on which to run SPF.
        src_node: The source node from which to compute shortest paths.
        edge_select_func: A function that, given the graph, current node, neighbor node,
            a dictionary of edges, the set of excluded edges, and the set of excluded nodes,
            returns a tuple of (cost, list_of_edges) representing the minimal edge cost
            and the edges to use.
            Defaults to an edge selection function that finds edges with the minimal cost.
        multipath: If True, multiple paths with the same cost to the same node are recorded.
        excluded_edges: An optional set of edges (by EdgeID) to exclude from the graph.
        excluded_nodes: An optional set of nodes (by NodeID) to exclude from the graph.

    Returns:
        A tuple of:
            - costs: A dictionary mapping each reachable node to the cost of the shortest path
              from ``src_node`` to that node.
            - pred: A dictionary mapping each reachable node to another dictionary. The inner
              dictionary maps a predecessor node to the list of edges taken from the predecessor
              to the key node. Multiple predecessors may be stored if ``multipath=True``.

    Raises:
        KeyError: If ``src_node`` is not present in ``graph``.

    Examples:
        >>> costs, pred = spf(my_graph, src_node="A")
        >>> print(costs)
        {"A": 0, "B": 2.5, "C": 3.2}
        >>> print(pred)
        {
            "A": {},
            "B": {"A": [("A", "B")]},
            "C": {"B": [("B", "C")]}
        }
    """
    if excluded_edges is None:
        excluded_edges = set()
    if excluded_nodes is None:
        excluded_nodes = set()

    # Access adjacency once to avoid repeated lookups.
    # _adj is assumed to be a dict of dicts: {node: {neighbor: {edge_id: AttrDict}}}
    outgoing_adjacencies = graph._adj

    # Initialize data structures
    costs: Dict[NodeID, Cost] = {src_node: 0}  # cost from src_node to itself is 0
    pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]] = {
        src_node: {}
    }  # no predecessor for src_node

    # Min-priority queue of (cost, node). The cost is used as the priority.
    min_pq: List[Tuple[Cost, NodeID]] = []
    heappush(min_pq, (0, src_node))

    while min_pq:
        current_cost, node_id = heappop(min_pq)

        # Skip if we've already found a better path to node_id
        if current_cost > costs[node_id]:
            continue

        # If the node is excluded, skip expanding it
        if node_id in excluded_nodes:
            continue

        # Explore each neighbor of node_id
        for neighbor_id, edges_dict in outgoing_adjacencies[node_id].items():
            if neighbor_id in excluded_nodes:
                continue

            # Select best edges to neighbor
            edge_cost, selected_edges = edge_select_func(
                graph,
                node_id,
                neighbor_id,
                edges_dict,
                excluded_edges,
                excluded_nodes,
            )

            if not selected_edges:
                # No valid edges to this neighbor (e.g., all excluded)
                continue

            new_cost = current_cost + edge_cost

            # Check if this is a strictly better path or an equal-cost path (if multipath=True)
            if neighbor_id not in costs or new_cost < costs[neighbor_id]:
                # Found a new strictly better path
                costs[neighbor_id] = new_cost
                pred[neighbor_id] = {node_id: selected_edges}
                heappush(min_pq, (new_cost, neighbor_id))

            elif multipath and new_cost == costs[neighbor_id]:
                # Found an additional path of the same minimal cost
                pred[neighbor_id][node_id] = selected_edges

    return costs, pred


def ksp(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    edge_select_func: Callable[
        [StrictMultiDiGraph, NodeID, NodeID, Dict[EdgeID, AttrDict]],
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
