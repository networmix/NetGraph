from typing import Optional, Callable, Any
import networkx as nx

from ngraph.lib.graph import StrictMultiDiGraph, NodeID


def to_digraph(
    graph: StrictMultiDiGraph,
    edge_func: Optional[
        Callable[[StrictMultiDiGraph, NodeID, NodeID, dict], dict]
    ] = None,
    revertible: bool = True,
) -> nx.DiGraph:
    """
    Convert a StrictMultiDiGraph to a NetworkX DiGraph.

    This function consolidates multi-edges between nodes into a single edge.
    Optionally, a custom edge function can be provided to compute edge attributes.
    If `revertible` is True, the original multi-edge data is stored in the '_uv_edges'
    attribute of each consolidated edge, allowing for later reversion.

    Args:
        graph: The StrictMultiDiGraph to convert.
        edge_func: Optional function to compute consolidated edge attributes.
                   Should accept (graph, u, v, edges) and return a dict.
        revertible: If True, store the original multi-edge data.

    Returns:
        A NetworkX DiGraph representing the input graph.
    """
    nx_graph = nx.DiGraph()
    nx_graph.add_nodes_from(graph.get_nodes())

    # Iterate over nodes and their neighbors using the internal _adj attribute.
    for u, neighbors in graph._adj.items():
        for v, edges in neighbors.items():
            if edge_func:
                edge_data = edge_func(graph, u, v, edges)
                nx_graph.add_edge(u, v, **edge_data)
            else:
                nx_graph.add_edge(u, v)

            if revertible:
                # Store the original multi-edge data in the '_uv_edges' attribute.
                edge_attr = nx_graph.edges[u, v]
                edge_attr.setdefault("_uv_edges", [])
                edge_attr["_uv_edges"].append((u, v, edges))
    return nx_graph


def from_digraph(nx_graph: nx.DiGraph) -> StrictMultiDiGraph:
    """
    Convert a revertible NetworkX DiGraph to a StrictMultiDiGraph.

    This function reconstructs the original StrictMultiDiGraph by restoring
    multi-edge information from the '_uv_edges' attribute of each edge.

    Args:
        nx_graph: A revertible NetworkX DiGraph with '_uv_edges' attributes.

    Returns:
        A StrictMultiDiGraph reconstructed from the input DiGraph.
    """
    graph = StrictMultiDiGraph()
    graph.add_nodes_from(nx_graph.nodes)

    # Restore original multi-edges from the consolidated edge attribute.
    for u, v, data in nx_graph.edges(data=True):
        uv_edges = data.get("_uv_edges", [])
        for orig_u, orig_v, edges in uv_edges:
            for edge_id, edge_data in edges.items():
                graph.add_edge(orig_u, orig_v, edge_id, **edge_data)
    return graph


def to_graph(
    graph: StrictMultiDiGraph,
    edge_func: Optional[
        Callable[[StrictMultiDiGraph, NodeID, NodeID, dict], dict]
    ] = None,
    revertible: bool = True,
) -> nx.Graph:
    """
    Convert a StrictMultiDiGraph to a NetworkX Graph.

    This function works similarly to `to_digraph` but returns an undirected graph.

    Args:
        graph: The StrictMultiDiGraph to convert.
        edge_func: Optional function to compute consolidated edge attributes.
        revertible: If True, store the original multi-edge data.

    Returns:
        A NetworkX Graph representing the input graph.
    """
    nx_graph = nx.Graph()
    nx_graph.add_nodes_from(graph.get_nodes())

    # Iterate over the internal _adj attribute to consolidate edges.
    for u, neighbors in graph._adj.items():
        for v, edges in neighbors.items():
            if edge_func:
                edge_data = edge_func(graph, u, v, edges)
                nx_graph.add_edge(u, v, **edge_data)
            else:
                nx_graph.add_edge(u, v)

            if revertible:
                edge_attr = nx_graph.edges[u, v]
                edge_attr.setdefault("_uv_edges", [])
                edge_attr["_uv_edges"].append((u, v, edges))
    return nx_graph


def from_graph(nx_graph: nx.Graph) -> StrictMultiDiGraph:
    """
    Convert a revertible NetworkX Graph to a StrictMultiDiGraph.

    Restores the original multi-edge structure from the '_uv_edges' attribute stored
    in each consolidated edge.

    Args:
        nx_graph: A revertible NetworkX Graph with '_uv_edges' attributes.

    Returns:
        A StrictMultiDiGraph reconstructed from the input Graph.
    """
    graph = StrictMultiDiGraph()
    graph.add_nodes_from(nx_graph.nodes)

    # Restore multi-edge data from each edge's '_uv_edges' attribute.
    for u, v, data in nx_graph.edges(data=True):
        uv_edges = data.get("_uv_edges", [])
        for orig_u, orig_v, edges in uv_edges:
            for edge_id, edge_data in edges.items():
                graph.add_edge(orig_u, orig_v, edge_id, **edge_data)
    return graph
