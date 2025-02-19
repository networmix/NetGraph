from typing import Optional
import networkx as nx

from ngraph.lib.graph import StrictMultiDiGraph


def to_digraph(
    graph: StrictMultiDiGraph, edge_func=None, revertible=True
) -> nx.DiGraph:
    """
    Convert a StrictMultiDiGraph to a NetworkX DiGraph
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

            if revertible:
                # store original edges in a consolidated edge
                nx_graph.edges[u, v].setdefault("_uv_edges", [])
                nx_graph.edges[u, v]["_uv_edges"].append((u, v, edges))
    return nx_graph


def from_digraph(nx_graph: nx.DiGraph) -> StrictMultiDiGraph:
    """
    Convert a revertible NetworkX DiGraph to a StrictMultiDiGraph
    """
    graph = StrictMultiDiGraph()
    graph.add_nodes_from(nx_graph.nodes)

    # restore original edges from the consolidated edge
    for u, v, data in nx_graph.edges(data=True):
        uv_edges = data.get("_uv_edges", [])
        for u, v, edges in uv_edges:
            for edge_id, edge_data in edges.items():
                graph.add_edge(u, v, edge_id, **edge_data)
    return graph


def to_graph(graph: StrictMultiDiGraph, edge_func=None, revertible=True) -> nx.Graph:
    """
    Convert a StrictMultiDiGraph to a NetworkX Graph
    """
    nx_graph = nx.Graph()
    nx_graph.add_nodes_from(graph.get_nodes())

    # consolidate multi-edges into a single edge
    for u, neighbors in graph._adj.items():
        for v, edges in neighbors.items():
            # if edge_func is provided, use it to create data for consolidated edge
            if edge_func:
                nx_graph.add_edge(u, v, **edge_func(graph, u, v, edges))
            else:
                nx_graph.add_edge(u, v)

            if revertible:
                # store original edges in a consolidated edge
                nx_graph.edges[u, v].setdefault("_uv_edges", [])
                nx_graph.edges[u, v]["_uv_edges"].append((u, v, edges))
    return nx_graph


def from_graph(nx_graph: nx.Graph) -> StrictMultiDiGraph:
    """
    Convert a revertible NetworkX Graph to a StrictMultiDiGraph
    """
    graph = StrictMultiDiGraph()
    graph.add_nodes_from(nx_graph.nodes)

    # restore original edges from the consolidated edge
    for u, v, data in nx_graph.edges(data=True):
        uv_edges = data.get("_uv_edges", [])
        for u, v, edges in uv_edges:
            for edge_id, edge_data in edges.items():
                graph.add_edge(u, v, edge_id, **edge_data)
    return graph
