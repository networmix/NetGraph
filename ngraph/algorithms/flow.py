from typing import Hashable
from ngraph.graph import MultiDiGraph


def edmonds_karp(
    graph: MultiDiGraph, s: Hashable, t: Hashable, cutoff: float = float("inf")
) -> MultiDiGraph:
    residual_graph = graph.copy()
    for edge_tuple in residual_graph.get_edges().values():
        edge_tuple[3]["flow"] = 0
    residual_graph.get_attr()["flow_value"] = edmonds_karp_core(
        residual_graph, s, t, cutoff
    )
    return residual_graph


def edmonds_karp_core(
    residual_graph: MultiDiGraph, s: Hashable, t: Hashable, cutoff
) -> float:
    """
    Implementation of the Edmonds-Karp algorithm.
    """

    R_pred = residual_graph.get_adj_in()
    R_succ = residual_graph.get_adj_out()

    inf = float("inf")

    def augment(path):
        """
        Augment flow along a path from s to t.
        """
        # Determine the path residual capacity.
        flow = inf
        it = iter(path)
        u = next(it)
        for v in it:
            edges = R_succ[u][v]
            total_remaining_capacity = 0
            for edge_dict in edges.values():
                total_remaining_capacity += edge_dict["capacity"] - edge_dict["flow"]
            flow = min(flow, total_remaining_capacity)
            u = v

        # Augment flow along the path.
        it = iter(path)
        u = next(it)
        for v in it:
            edges = R_succ[u][v]
            total_remaining_capacity = 0
            for edge_dict in edges.values():
                total_remaining_capacity += edge_dict["capacity"] - edge_dict["flow"]
            for edge_dict in edges.values():
                remaining_capacity = edge_dict["capacity"] - edge_dict["flow"]
                edge_dict["flow"] += (
                    remaining_capacity / total_remaining_capacity * flow
                )
            u = v
        return flow

    def bfs():
        """
        Breadth-first search for an augmenting path.
        """
        succ = {t: None}
        queue = [t]
        while queue:
            u = queue.pop()
            for v, edges in R_pred[u].items():
                for edge_dict in edges.values():
                    if v not in succ and edge_dict["flow"] < edge_dict["capacity"]:
                        succ[v] = u
                        if v == s:
                            return succ
                        queue.append(v)
        return {}

    # Look for shortest augmenting paths using breadth-first search
    flow_value = 0
    while flow_value < cutoff:
        succ = bfs()
        if not succ:
            break
        path = [s]
        # Trace the path from s to t
        u = s
        while u != t:
            u = succ[u]
            path.append(u)
        flow_value += augment(path)
    return flow_value
