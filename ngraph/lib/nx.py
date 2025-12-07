"""NetworkX graph conversion utilities.

This module provides functions to convert between NetworkX graphs and the
internal graph representation used by ngraph for high-performance algorithms.

Example:
    >>> import networkx as nx
    >>> from ngraph.lib.nx import from_networkx, to_networkx
    >>>
    >>> # Create a NetworkX graph
    >>> G = nx.DiGraph()
    >>> G.add_edge("A", "B", capacity=100.0, cost=10)
    >>> G.add_edge("B", "C", capacity=50.0, cost=5)
    >>>
    >>> # Convert to ngraph format for analysis
    >>> graph, node_map, edge_map = from_networkx(G)
    >>>
    >>> # Use with ngraph algorithms...
    >>>
    >>> # Convert back to NetworkX
    >>> G_out = to_networkx(graph, node_map)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Hashable, List, Optional, Tuple, Union

import netgraph_core
import numpy as np

if TYPE_CHECKING:
    import networkx as nx

    NxGraph = Union[nx.DiGraph, nx.MultiDiGraph, nx.Graph, nx.MultiGraph]
else:
    NxGraph = Any


@dataclass
class NodeMap:
    """Bidirectional mapping between node names and integer indices.

    When converting a NetworkX graph to the internal representation, node names
    (which can be any hashable type) are mapped to contiguous integer indices
    starting from 0. This class preserves the mapping for result interpretation
    and back-conversion.

    Attributes:
        to_index: Maps original node names to integer indices
        to_name: Maps integer indices back to original node names

    Example:
        >>> node_map = NodeMap.from_names(["A", "B", "C"])
        >>> node_map.to_index["A"]
        0
        >>> node_map.to_name[1]
        'B'
    """

    to_index: Dict[Hashable, int] = field(default_factory=dict)
    to_name: Dict[int, Hashable] = field(default_factory=dict)

    @classmethod
    def from_names(cls, names: List[Hashable]) -> "NodeMap":
        """Create a NodeMap from a list of node names.

        Args:
            names: List of node names in index order

        Returns:
            NodeMap with bidirectional mapping
        """
        to_index = {name: i for i, name in enumerate(names)}
        to_name = {i: name for i, name in enumerate(names)}
        return cls(to_index=to_index, to_name=to_name)

    def __len__(self) -> int:
        """Return the number of nodes in the mapping."""
        return len(self.to_index)


# Type alias for edge references: (source_node, target_node, edge_key)
EdgeRef = Tuple[Hashable, Hashable, Any]


@dataclass
class EdgeMap:
    """Bidirectional mapping between internal edge IDs and original edge references.

    When converting a NetworkX graph, each edge is assigned an internal integer ID
    (ext_edge_id). This class preserves the mapping for interpreting algorithm
    results and updating the original graph.

    Attributes:
        to_ref: Maps internal edge ID to original (source, target, key) tuple
        from_ref: Maps original (source, target, key) to list of internal edge IDs
            (list because bidirectional=True creates two IDs per edge)

    Example:
        >>> graph, node_map, edge_map = from_networkx(G)
        >>> # After running algorithms, map flow results back to original edges
        >>> for ext_id, flow in enumerate(flow_state.edge_flow_view()):
        ...     if flow > 0:
        ...         u, v, key = edge_map.to_ref[ext_id]
        ...         G.edges[u, v, key]["flow"] = flow
    """

    to_ref: Dict[int, EdgeRef] = field(default_factory=dict)
    from_ref: Dict[EdgeRef, List[int]] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return the number of edge mappings."""
        return len(self.to_ref)


def from_networkx(
    G: NxGraph,
    *,
    capacity_attr: str = "capacity",
    cost_attr: str = "cost",
    default_capacity: float = 1.0,
    default_cost: int = 1,
    bidirectional: bool = False,
) -> Tuple[netgraph_core.StrictMultiDiGraph, NodeMap, EdgeMap]:
    """Convert a NetworkX graph to ngraph's internal graph format.

    Converts any NetworkX graph (DiGraph, MultiDiGraph, Graph, MultiGraph) to
    netgraph_core.StrictMultiDiGraph. Node names are mapped to integer indices;
    the returned NodeMap and EdgeMap preserve mappings for result interpretation.

    Args:
        G: NetworkX graph (DiGraph, MultiDiGraph, Graph, or MultiGraph)
        capacity_attr: Edge attribute name for capacity (default: "capacity")
        cost_attr: Edge attribute name for cost (default: "cost")
        default_capacity: Capacity value when attribute is missing (default: 1.0)
        default_cost: Cost value when attribute is missing (default: 1)
        bidirectional: If True, add reverse edge for each edge. Useful for
            undirected connectivity analysis. (default: False)

    Returns:
        Tuple of (graph, node_map, edge_map) where:
        - graph: netgraph_core.StrictMultiDiGraph ready for algorithms
        - node_map: NodeMap for converting node indices back to names
        - edge_map: EdgeMap for converting edge IDs back to (u, v, key) refs

    Raises:
        TypeError: If G is not a NetworkX graph
        ValueError: If graph has no nodes

    Example:
        >>> import networkx as nx
        >>> G = nx.DiGraph()
        >>> G.add_edge("src", "dst", capacity=100.0, cost=10)
        >>> graph, node_map, edge_map = from_networkx(G)
        >>> graph.num_nodes()
        2
        >>> node_map.to_index["src"]
        0
        >>> edge_map.to_ref[0]  # First edge
        ('dst', 'src', 0)  # sorted node order: dst < src
    """
    import networkx as nx

    if not isinstance(G, (nx.DiGraph, nx.MultiDiGraph, nx.Graph, nx.MultiGraph)):
        raise TypeError(
            f"Expected NetworkX graph (DiGraph, MultiDiGraph, Graph, MultiGraph), "
            f"got {type(G).__name__}"
        )

    if G.number_of_nodes() == 0:
        raise ValueError("Graph has no nodes")

    # Build node mapping (sorted for deterministic ordering)
    node_names = sorted(G.nodes(), key=str)
    node_map = NodeMap.from_names(node_names)
    num_nodes = len(node_names)

    # Collect edges and build edge mapping
    src_list: List[int] = []
    dst_list: List[int] = []
    capacity_list: List[float] = []
    cost_list: List[int] = []
    ext_id_list: List[int] = []

    edge_to_ref: Dict[int, EdgeRef] = {}
    ref_to_edges: Dict[EdgeRef, List[int]] = {}

    edge_id = 0
    is_multigraph = isinstance(G, (nx.MultiDiGraph, nx.MultiGraph))

    # Iterate edges based on graph type
    if is_multigraph:
        edges_iter = G.edges(keys=True, data=True)
    else:
        edges_iter = ((u, v, 0, d) for u, v, d in G.edges(data=True))

    for u, v, key, data in edges_iter:
        src_idx = node_map.to_index[u]
        dst_idx = node_map.to_index[v]
        cap = float(data.get(capacity_attr, default_capacity))
        cst = int(data.get(cost_attr, default_cost))
        edge_ref: EdgeRef = (u, v, key)

        # Forward edge
        src_list.append(src_idx)
        dst_list.append(dst_idx)
        capacity_list.append(cap)
        cost_list.append(cst)
        ext_id_list.append(edge_id)
        edge_to_ref[edge_id] = edge_ref
        ref_to_edges.setdefault(edge_ref, []).append(edge_id)
        edge_id += 1

        # Reverse edge (if bidirectional)
        if bidirectional:
            src_list.append(dst_idx)
            dst_list.append(src_idx)
            capacity_list.append(cap)
            cost_list.append(cst)
            ext_id_list.append(edge_id)
            # Reverse edge maps to same original edge reference
            edge_to_ref[edge_id] = edge_ref
            ref_to_edges.setdefault(edge_ref, []).append(edge_id)
            edge_id += 1

    edge_map = EdgeMap(to_ref=edge_to_ref, from_ref=ref_to_edges)

    # Handle graphs with nodes but no edges
    if not src_list:
        # Create minimal arrays for empty edge set
        src_arr = np.array([], dtype=np.int32)
        dst_arr = np.array([], dtype=np.int32)
        capacity_arr = np.array([], dtype=np.float64)
        cost_arr = np.array([], dtype=np.int64)
        ext_id_arr = np.array([], dtype=np.int64)
    else:
        src_arr = np.array(src_list, dtype=np.int32)
        dst_arr = np.array(dst_list, dtype=np.int32)
        capacity_arr = np.array(capacity_list, dtype=np.float64)
        cost_arr = np.array(cost_list, dtype=np.int64)
        ext_id_arr = np.array(ext_id_list, dtype=np.int64)

    graph = netgraph_core.StrictMultiDiGraph.from_arrays(
        num_nodes=num_nodes,
        src=src_arr,
        dst=dst_arr,
        capacity=capacity_arr,
        cost=cost_arr,
        ext_edge_ids=ext_id_arr,
    )

    return graph, node_map, edge_map


def to_networkx(
    graph: netgraph_core.StrictMultiDiGraph,
    node_map: Optional[NodeMap] = None,
    *,
    capacity_attr: str = "capacity",
    cost_attr: str = "cost",
) -> "nx.MultiDiGraph":
    """Convert ngraph's internal graph format back to NetworkX MultiDiGraph.

    Reconstructs a NetworkX graph from the internal representation. If a
    NodeMap is provided, original node names are restored; otherwise, nodes
    are labeled with integer indices.

    Args:
        graph: netgraph_core.StrictMultiDiGraph to convert
        node_map: Optional NodeMap to restore original node names.
            If None, nodes are labeled 0, 1, 2, ...
        capacity_attr: Edge attribute name for capacity (default: "capacity")
        cost_attr: Edge attribute name for cost (default: "cost")

    Returns:
        nx.MultiDiGraph with edges and attributes from the internal graph

    Example:
        >>> graph, node_map, edge_map = from_networkx(G)
        >>> # ... run algorithms ...
        >>> G_out = to_networkx(graph, node_map)
        >>> list(G_out.nodes())
        ['A', 'B', 'C']
    """
    import networkx as nx

    G = nx.MultiDiGraph()
    num_nodes = graph.num_nodes()

    # Add nodes with original names if available
    if node_map is not None:
        for idx in range(num_nodes):
            name = node_map.to_name.get(idx, idx)
            G.add_node(name)
    else:
        G.add_nodes_from(range(num_nodes))

    # Extract edge data from graph views
    src_arr = graph.edge_src_view()
    dst_arr = graph.edge_dst_view()
    capacity_arr = graph.capacity_view()
    cost_arr = graph.cost_view()

    # Add edges
    num_edges = graph.num_edges()
    for i in range(num_edges):
        src_idx = int(src_arr[i])
        dst_idx = int(dst_arr[i])

        if node_map is not None:
            src_name = node_map.to_name.get(src_idx, src_idx)
            dst_name = node_map.to_name.get(dst_idx, dst_idx)
        else:
            src_name = src_idx
            dst_name = dst_idx

        G.add_edge(
            src_name,
            dst_name,
            **{
                capacity_attr: float(capacity_arr[i]),
                cost_attr: int(cost_arr[i]),
            },
        )

    return G
