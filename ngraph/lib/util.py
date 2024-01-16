from typing import Optional
import networkx as nx

from ngraph.lib.graph import MultiDiGraph


def to_digraph(graph: MultiDiGraph, edge_func=None) -> nx.DiGraph:
    """
    Convert a MultiDiGraph to a NetworkX DiGraph
    """
    nx_graph = nx.DiGraph()
    nx_graph.add_nodes_from(graph.get_nodes())

    # consolidate multi-edges into a single edge
    for u, neighbors in graph._adj.items():
        for v, edges in neighbors.items():
            # if edge_func is provided, use it to create data for consolidated edge
            if edge_func:
                nx_graph.add_edge(u, v, **edge_func(graph, u, v, edges))
            else:
                nx_graph.add_edge(u, v)
            # store original edges in a consolidated edge
            nx_graph.edges[u, v]["_edges"] = edges
    return nx_graph


def from_digraph(nx_graph: nx.DiGraph) -> MultiDiGraph:
    """
    Convert a NetworkX DiGraph to a MultiDiGraph
    """
    graph = MultiDiGraph()
    graph.add_nodes_from(nx_graph.nodes)

    # restore original edges from the consolidated edge
    for u, v, data in nx_graph.edges(data=True):
        edges = data.get("_edges", {})
        for edge_id, edge_data in edges.items():
            graph.add_edge(u, v, edge_id, **edge_data)
    return graph
