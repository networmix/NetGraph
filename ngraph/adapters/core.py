"""Adapter layer for NetGraph-Core integration.

Provides graph building, node/edge ID mapping, and result translation between
NetGraph's scenario-level types and NetGraph-Core's internal representations.

Key components:
- build_graph(): One-shot graph construction with exclusions
- build_graph_cache(): Cached graph for repeated analysis with masks
- build_node_mask() / build_edge_mask(): O(|excluded|) mask construction
- get_disabled_exclusions(): Helper to collect disabled topology for exclusions

Graph caching enables efficient repeated analysis with different exclusion sets
by building the graph once and using lightweight masks for exclusions. Disabled
nodes and links are automatically included in masks built from a GraphCache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Set

import netgraph_core
import numpy as np

from ngraph.types.dto import EdgeRef

if TYPE_CHECKING:
    from ngraph.model.network import Network


def get_disabled_exclusions(
    network: "Network",
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
) -> tuple[Optional[Set[str]], Optional[Set[str]]]:
    """Merge user exclusions with disabled nodes/links from the network.

    Use this when calling build_graph() to ensure disabled topology is excluded.

    Args:
        network: Network instance.
        excluded_nodes: User-provided node exclusions (or None).
        excluded_links: User-provided link exclusions (or None).

    Returns:
        Tuple of (full_excluded_nodes, full_excluded_links) including disabled.
        Returns None for either if empty (for efficient build_graph calls).
    """
    disabled_nodes = {name for name, node in network.nodes.items() if node.disabled}
    disabled_links = {lid for lid, link in network.links.items() if link.disabled}

    full_excluded_nodes: Optional[Set[str]] = None
    if disabled_nodes or excluded_nodes:
        full_excluded_nodes = (excluded_nodes or set()) | disabled_nodes

    full_excluded_links: Optional[Set[str]] = None
    if disabled_links or excluded_links:
        full_excluded_links = (excluded_links or set()) | disabled_links

    return full_excluded_nodes, full_excluded_links


class AugmentationEdge(NamedTuple):
    """Edge specification for graph augmentation.

    Augmentation edges are added to the graph as-is (unidirectional).
    Nodes referenced in augmentations that don't exist in the network
    are automatically treated as pseudo/virtual nodes.

    Attributes:
        source: Source node name (real or pseudo)
        target: Target node name (real or pseudo)
        capacity: Edge capacity
        cost: Edge cost (converted to int64 for Core)
    """

    source: str
    target: str
    capacity: float
    cost: float


class NodeMapper:
    """Bidirectional mapping between NetGraph node names (str) and Core NodeId (int)."""

    def __init__(self, node_names: list[str]):
        """Initialize mapper from ordered list of node names.

        Args:
            node_names: Ordered list of node names; index is Core NodeId.
        """
        self.node_names = node_names
        self.node_id_of = {name: idx for idx, name in enumerate(node_names)}

    def to_id(self, name: str) -> int:
        """Map node name to Core NodeId."""
        return self.node_id_of[name]

    def to_name(self, node_id: int) -> str:
        """Map Core NodeId to node name."""
        return self.node_names[node_id]


class EdgeMapper:
    """Bidirectional mapping between external edge IDs and EdgeRef (link_id + direction).

    External edge ID encoding: (linkIndex << 1) | dirBit
    - linkIndex: stable sorted index of link_id in Network.links
    - dirBit: 0 for forward ('fwd'), 1 for reverse ('rev')
    """

    def __init__(self, link_ids: list[str]):
        """Initialize mapper from ordered list of link IDs.

        Args:
            link_ids: Sorted list of link IDs (stable ordering for linkIndex assignment).
        """
        self.link_ids = link_ids
        self.link_index_of = {lid: idx for idx, lid in enumerate(link_ids)}

    def encode_ext_id(self, link_id: str, direction: str) -> int:
        """Encode (link_id, direction) to external edge ID.

        Args:
            link_id: Scenario link identifier.
            direction: 'fwd' or 'rev'.

        Returns:
            External edge ID as int64.
        """
        link_idx = self.link_index_of[link_id]
        dir_bit = 1 if direction == "rev" else 0
        return (link_idx << 1) | dir_bit

    def decode_ext_id(self, ext_id: int) -> Optional[EdgeRef]:
        """Decode external edge ID to EdgeRef.

        Args:
            ext_id: External edge ID from Core.

        Returns:
            EdgeRef with link_id and direction, or None if augmentation edge.
        """
        if ext_id == -1:
            return None
        link_idx = ext_id >> 1
        dir_bit = ext_id & 1
        link_id = self.link_ids[link_idx]
        direction = "rev" if dir_bit else "fwd"
        return EdgeRef(link_id=link_id, direction=direction)  # type: ignore

    def to_ref(
        self, core_edge_id: int, multidigraph: netgraph_core.StrictMultiDiGraph
    ) -> Optional[EdgeRef]:
        """Map Core EdgeId to EdgeRef using the Core graph's ext_edge_ids.

        Args:
            core_edge_id: Core's internal EdgeId (index into edge arrays).
            multidigraph: Core StrictMultiDiGraph instance.

        Returns:
            EdgeRef corresponding to the Core edge, or None if augmentation edge.
        """
        ext_edge_ids = multidigraph.ext_edge_ids_view()
        ext_id = ext_edge_ids[core_edge_id]
        return self.decode_ext_id(int(ext_id))

    def to_name(self, ext_id: int) -> Optional[str]:
        """Map external edge ID to link ID (name).

        Args:
            ext_id: External edge ID from Core.

        Returns:
            Link ID string, or None if it's a sentinel/augmentation edge.
        """
        if ext_id == -1:
            return None
        edge_ref = self.decode_ext_id(ext_id)
        if edge_ref is None:
            return None
        return edge_ref.link_id


@dataclass
class GraphCache:
    """Pre-built graph components for efficient repeated analysis.

    Holds all components needed for running analysis with different exclusion
    sets without rebuilding the graph. Use build_graph_cache() to create.

    Attributes:
        graph_handle: Core Graph handle for algorithm execution.
        multidigraph: Core StrictMultiDiGraph with topology data.
        edge_mapper: Mapper for link_id <-> edge_id translation.
        node_mapper: Mapper for node_name <-> node_id translation.
        algorithms: Core Algorithms instance for running computations.
        disabled_node_ids: Pre-computed set of disabled node IDs.
        disabled_link_ids: Pre-computed set of disabled link IDs.
        link_id_to_edge_indices: Mapping from link_id to edge array indices.
    """

    graph_handle: netgraph_core.Graph
    multidigraph: netgraph_core.StrictMultiDiGraph
    edge_mapper: EdgeMapper
    node_mapper: NodeMapper
    algorithms: netgraph_core.Algorithms
    disabled_node_ids: Set[int] = field(default_factory=set)
    disabled_link_ids: Set[str] = field(default_factory=set)
    link_id_to_edge_indices: Dict[str, List[int]] = field(default_factory=dict)


def build_graph_cache(
    network: "Network",
    *,
    add_reverse: bool = True,
    augmentations: Optional[List[AugmentationEdge]] = None,
) -> GraphCache:
    """Build cached graph components for efficient repeated analysis.

    Constructs the graph once and pre-computes mappings needed for fast
    mask building. Use with build_node_mask() and build_edge_mask() for
    O(|excluded|) exclusion handling instead of O(V+E).

    Args:
        network: NetGraph Network instance.
        add_reverse: If True, add reverse edges for network links.
        augmentations: Optional list of edges to add (for pseudo nodes, etc.).

    Returns:
        GraphCache with all pre-built components.

    Example:
        >>> cache = build_graph_cache(network)
        >>> for excluded_nodes, excluded_links in failure_patterns:
        ...     node_mask = build_node_mask(cache, excluded_nodes)
        ...     edge_mask = build_edge_mask(cache, excluded_links)
        ...     result = cache.algorithms.max_flow(
        ...         cache.graph_handle, src, dst,
        ...         node_mask=node_mask, edge_mask=edge_mask
        ...     )
    """
    # Build graph without exclusions (exclusions handled via masks)
    graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(
        network,
        add_reverse=add_reverse,
        augmentations=augmentations,
        excluded_nodes=None,
        excluded_links=None,
    )

    # Create algorithms instance
    backend = netgraph_core.Backend.cpu()
    algorithms = netgraph_core.Algorithms(backend)

    # Pre-compute disabled node IDs
    disabled_node_ids: Set[int] = set()
    for node_name, node in network.nodes.items():
        if node.disabled and node_name in node_mapper.node_id_of:
            disabled_node_ids.add(node_mapper.node_id_of[node_name])

    # Pre-compute disabled link IDs
    disabled_link_ids: Set[str] = {
        link_id for link_id, link in network.links.items() if link.disabled
    }

    # Pre-compute link_id -> edge indices mapping for O(|excluded|) mask building
    ext_edge_ids = multidigraph.ext_edge_ids_view()
    link_id_to_edge_indices: Dict[str, List[int]] = {}
    for edge_idx in range(len(ext_edge_ids)):
        ext_id = int(ext_edge_ids[edge_idx])
        if ext_id == -1:  # Skip augmentation edges
            continue
        edge_ref = edge_mapper.decode_ext_id(ext_id)
        if edge_ref:
            link_id_to_edge_indices.setdefault(edge_ref.link_id, []).append(edge_idx)

    return GraphCache(
        graph_handle=graph_handle,
        multidigraph=multidigraph,
        edge_mapper=edge_mapper,
        node_mapper=node_mapper,
        algorithms=algorithms,
        disabled_node_ids=disabled_node_ids,
        disabled_link_ids=disabled_link_ids,
        link_id_to_edge_indices=link_id_to_edge_indices,
    )


def build_graph(
    network: "Network",
    *,
    add_reverse: bool = True,
    augmentations: Optional[List[AugmentationEdge]] = None,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
) -> tuple[
    netgraph_core.Graph, netgraph_core.StrictMultiDiGraph, EdgeMapper, NodeMapper
]:
    """Build Core graph with optional augmentations and exclusions.

    This is the unified graph builder for all analysis functions. It supports:
    - Standard network topology
    - Pseudo/virtual nodes (via augmentations)
    - Filtered topology (via exclusions)

    For repeated analysis with different exclusions, use build_graph_cache()
    with build_node_mask()/build_edge_mask() for better performance.

    Args:
        network: NetGraph Network instance.
        add_reverse: If True, add reverse edges for network links.
        augmentations: Optional list of edges to add (for pseudo nodes, etc.).
        excluded_nodes: Optional set of node names to exclude.
        excluded_links: Optional set of link IDs to exclude.

    Returns:
        Tuple of (graph_handle, multidigraph, edge_mapper, node_mapper).

    Pseudo Nodes:
        Any node name in augmentations that doesn't exist in network.nodes
        is automatically treated as a pseudo node and assigned a node ID.

    Augmentation Edges:
        - Added unidirectionally as specified
        - Assigned ext_edge_id of -1 (sentinel for non-network edges)
        - Not included in edge_mapper translation

    Node ID Assignment:
        Real nodes (sorted): IDs 0..(num_real-1)
        Pseudo nodes (sorted): IDs num_real..(num_real+num_pseudo-1)
    """
    # Validate exclusions
    if excluded_nodes:
        invalid = excluded_nodes - set(network.nodes.keys())
        if invalid:
            raise ValueError(f"Excluded nodes not in network: {invalid}")

    if excluded_links:
        invalid = excluded_links - set(network.links.keys())
        if invalid:
            raise ValueError(f"Excluded links not in network: {invalid}")

    # Step 1: Identify real nodes (after exclusions)
    real_node_names = set(network.nodes.keys())
    if excluded_nodes:
        real_node_names -= excluded_nodes

    # Step 2: Infer pseudo nodes from augmentation edges
    pseudo_node_names: Set[str] = set()
    if augmentations:
        for aug_edge in augmentations:
            if aug_edge.source not in real_node_names:
                pseudo_node_names.add(aug_edge.source)
            if aug_edge.target not in real_node_names:
                pseudo_node_names.add(aug_edge.target)

    # Step 3: Assign node IDs (real first, then pseudo)
    all_node_names = sorted(real_node_names) + sorted(pseudo_node_names)
    node_mapper = NodeMapper(all_node_names)

    # Step 4: Build edge mapper (only for real network links)
    link_ids = sorted(network.links.keys())
    edge_mapper = EdgeMapper(link_ids)

    # Step 5: Build edge arrays
    src_list: List[int] = []
    dst_list: List[int] = []
    capacity_list: List[float] = []
    cost_list: List[float] = []
    ext_edge_id_list: List[int] = []

    # Add real network edges (bidirectional)
    for link_id in link_ids:
        if excluded_links and link_id in excluded_links:
            continue

        link = network.links[link_id]

        # Skip if either endpoint is excluded
        if (
            link.source not in node_mapper.node_id_of
            or link.target not in node_mapper.node_id_of
        ):
            continue

        src_id = node_mapper.to_id(link.source)
        dst_id = node_mapper.to_id(link.target)

        # Forward edge
        src_list.append(src_id)
        dst_list.append(dst_id)
        capacity_list.append(link.capacity)
        cost_list.append(link.cost)
        ext_edge_id_list.append(edge_mapper.encode_ext_id(link_id, "fwd"))

        # Reverse edge
        if add_reverse:
            src_list.append(dst_id)
            dst_list.append(src_id)
            capacity_list.append(link.capacity)
            cost_list.append(link.cost)
            ext_edge_id_list.append(edge_mapper.encode_ext_id(link_id, "rev"))

    # Add augmentation edges (unidirectional, as specified)
    if augmentations:
        for aug_edge in augmentations:
            src_id = node_mapper.to_id(aug_edge.source)
            dst_id = node_mapper.to_id(aug_edge.target)
            src_list.append(src_id)
            dst_list.append(dst_id)
            capacity_list.append(aug_edge.capacity)
            cost_list.append(aug_edge.cost)
            ext_edge_id_list.append(-1)  # Sentinel: not a network edge

    # Convert to numpy arrays
    src_arr = np.array(src_list, dtype=np.int32)
    dst_arr = np.array(dst_list, dtype=np.int32)
    capacity_arr = np.array(capacity_list, dtype=np.float64)
    cost_arr = np.array(cost_list, dtype=np.int64)
    ext_edge_ids_arr = np.array(ext_edge_id_list, dtype=np.int64)

    # Build StrictMultiDiGraph
    multidigraph = netgraph_core.StrictMultiDiGraph.from_arrays(
        num_nodes=len(all_node_names),
        src=src_arr,
        dst=dst_arr,
        capacity=capacity_arr,
        cost=cost_arr,
        ext_edge_ids=ext_edge_ids_arr,
    )

    # Build Core graph handle
    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)
    graph_handle = algs.build_graph(multidigraph)

    return graph_handle, multidigraph, edge_mapper, node_mapper


def build_node_mask(
    cache: GraphCache,
    excluded_nodes: Optional[Set[str]] = None,
) -> np.ndarray:
    """Build a node mask array for Core algorithms.

    Uses O(|excluded| + |disabled|) time complexity by only setting
    excluded/disabled nodes to False, rather than iterating all nodes.

    Core semantics: True = include, False = exclude.

    Args:
        cache: GraphCache with pre-computed disabled node IDs.
        excluded_nodes: Optional set of node names to exclude.

    Returns:
        Boolean numpy array of shape (num_nodes,) where True means included.
    """
    num_nodes = len(cache.node_mapper.node_names)
    mask = np.ones(num_nodes, dtype=bool)

    # Exclude disabled nodes (pre-computed)
    for node_id in cache.disabled_node_ids:
        mask[node_id] = False

    # Exclude requested nodes
    if excluded_nodes:
        for node_name in excluded_nodes:
            if node_name in cache.node_mapper.node_id_of:
                mask[cache.node_mapper.node_id_of[node_name]] = False

    return mask


def build_edge_mask(
    cache: GraphCache,
    excluded_links: Optional[Set[str]] = None,
) -> np.ndarray:
    """Build an edge mask array for Core algorithms.

    Uses O(|excluded| + |disabled|) time complexity by using the pre-computed
    link_id -> edge_indices mapping, rather than iterating all edges.

    Core semantics: True = include, False = exclude.

    Args:
        cache: GraphCache with pre-computed edge index mapping.
        excluded_links: Optional set of link IDs to exclude.

    Returns:
        Boolean numpy array of shape (num_edges,) where True means included.
    """
    num_edges = cache.multidigraph.num_edges()
    mask = np.ones(num_edges, dtype=bool)

    # Exclude disabled links (pre-computed)
    for link_id in cache.disabled_link_ids:
        if link_id in cache.link_id_to_edge_indices:
            for edge_idx in cache.link_id_to_edge_indices[link_id]:
                mask[edge_idx] = False

    # Exclude requested links
    if excluded_links:
        for link_id in excluded_links:
            if link_id in cache.link_id_to_edge_indices:
                for edge_idx in cache.link_id_to_edge_indices[link_id]:
                    mask[edge_idx] = False

    return mask
