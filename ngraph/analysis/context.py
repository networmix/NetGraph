"""AnalysisContext: Prepared state for efficient network analysis.

This module provides the primary API for network analysis in NetGraph.
AnalysisContext encapsulates Core graph infrastructure and provides
methods for max-flow, shortest paths, and sensitivity analysis.

Usage:
    # One-off analysis
    from ngraph import analyze
    flow = analyze(network).max_flow("^A$", "^B$")

    # Efficient repeated analysis (bound context)
    ctx = analyze(network, source="^A$", sink="^B$")
    baseline = ctx.max_flow()
    degraded = ctx.max_flow(excluded_links=failed_links)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

import netgraph_core
import numpy as np

from ngraph.model.path import Path
from ngraph.types.base import EdgeSelect, FlowPlacement, Mode
from ngraph.types.dto import EdgeRef, MaxFlowResult

if TYPE_CHECKING:
    from ngraph.model.network import Network


# Large capacity for pseudo edges (avoid float('inf') due to Core limitation)
LARGE_CAPACITY = 1e15


class AugmentationEdge:
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

    __slots__ = ("source", "target", "capacity", "cost")

    def __init__(self, source: str, target: str, capacity: float, cost: float):
        self.source = source
        self.target = target
        self.capacity = capacity
        self.cost = cost


class _NodeMapper:
    """Bidirectional mapping between node names (str) and Core NodeId (int)."""

    def __init__(self, node_names: list[str]):
        self.node_names = node_names
        self.node_id_of = {name: idx for idx, name in enumerate(node_names)}

    def to_id(self, name: str) -> int:
        return self.node_id_of[name]

    def to_name(self, node_id: int) -> str:
        return self.node_names[node_id]


class _EdgeMapper:
    """Bidirectional mapping between external edge IDs and EdgeRef."""

    def __init__(self, link_ids: list[str]):
        self.link_ids = link_ids
        self.link_index_of = {lid: idx for idx, lid in enumerate(link_ids)}

    def encode_ext_id(self, link_id: str, direction: str) -> int:
        link_idx = self.link_index_of[link_id]
        dir_bit = 1 if direction == "rev" else 0
        return (link_idx << 1) | dir_bit

    def decode_ext_id(self, ext_id: int) -> Optional[EdgeRef]:
        if ext_id == -1:
            return None
        link_idx = ext_id >> 1
        dir_bit = ext_id & 1
        link_id = self.link_ids[link_idx]
        direction = "rev" if dir_bit else "fwd"
        return EdgeRef(link_id=link_id, direction=direction)

    def to_ref(
        self, core_edge_id: int, multidigraph: netgraph_core.StrictMultiDiGraph
    ) -> Optional[EdgeRef]:
        ext_edge_ids = multidigraph.ext_edge_ids_view()
        ext_id = ext_edge_ids[core_edge_id]
        return self.decode_ext_id(int(ext_id))

    def to_name(self, ext_id: int) -> Optional[str]:
        if ext_id == -1:
            return None
        edge_ref = self.decode_ext_id(ext_id)
        return edge_ref.link_id if edge_ref else None


@dataclass
class _PseudoNodeContext:
    """Context for pseudo nodes created during graph construction."""

    source_path: str
    sink_path: str
    mode: Mode
    pairs: Dict[Tuple[str, str], Tuple[int, int]]


@dataclass
class AnalysisContext:
    """Prepared state for efficient network analysis.

    Encapsulates Core graph infrastructure. Supports two usage patterns:

    **Unbound** - flexible, specify source/sink per-call:

        ctx = AnalysisContext.from_network(network)
        cost = ctx.shortest_path_cost("A", "B")
        flow = ctx.max_flow("A", "B")  # Builds pseudo-nodes each call

    **Bound** - optimized for repeated analysis with same groups:

        ctx = AnalysisContext.from_network(
            network,
            source="^dc/",
            sink="^edge/"
        )
        baseline = ctx.max_flow()  # Uses pre-built pseudo-nodes
        degraded = ctx.max_flow(excluded_links=failed)

    Thread Safety:
        Immutable after creation. Safe for concurrent analysis calls
        with different exclusion sets.

    Attributes:
        network: Reference to source Network (read-only).
        is_bound: True if source/sink groups are pre-configured.
    """

    # Public read-only reference
    _network: "Network"

    # Core infrastructure (internal)
    _handle: netgraph_core.Graph = field(repr=False)
    _multidigraph: netgraph_core.StrictMultiDiGraph = field(repr=False)
    _node_mapper: _NodeMapper = field(repr=False)
    _edge_mapper: _EdgeMapper = field(repr=False)
    _algorithms: netgraph_core.Algorithms = field(repr=False)
    _disabled_node_ids: FrozenSet[int] = field(repr=False)
    _disabled_link_ids: FrozenSet[str] = field(repr=False)
    _link_id_to_edge_indices: Mapping[str, Tuple[int, ...]] = field(repr=False)

    # Binding state (None if unbound)
    _source_path: Optional[str] = None
    _sink_path: Optional[str] = None
    _mode: Optional[Mode] = None
    _pseudo_context: Optional[_PseudoNodeContext] = field(default=None, repr=False)

    @property
    def network(self) -> "Network":
        """Reference to source network (read-only)."""
        return self._network

    @property
    def is_bound(self) -> bool:
        """True if source/sink groups are pre-configured."""
        return self._source_path is not None

    @property
    def bound_source(self) -> Optional[str]:
        """Source pattern if bound, None otherwise."""
        return self._source_path

    @property
    def bound_sink(self) -> Optional[str]:
        """Sink pattern if bound, None otherwise."""
        return self._sink_path

    @property
    def bound_mode(self) -> Optional[Mode]:
        """Mode if bound, None otherwise."""
        return self._mode

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph (including pseudo nodes if bound)."""
        return len(self._node_mapper.node_names)

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph (includes forward + reverse)."""
        return self._multidigraph.num_edges()

    # ──────────────────────────────────────────────────────────────
    # Internal properties (not part of public API)
    #
    # These expose Core implementation details for use by internal
    # workflow steps and advanced tests. External code should use
    # the public methods (max_flow, shortest_paths, etc.) instead.
    # ──────────────────────────────────────────────────────────────

    @property
    def handle(self) -> netgraph_core.Graph:
        """Core Graph handle. Internal use only."""
        return self._handle

    @property
    def multidigraph(self) -> netgraph_core.StrictMultiDiGraph:
        """Core StrictMultiDiGraph. Internal use only."""
        return self._multidigraph

    @property
    def node_mapper(self) -> "_NodeMapper":
        """Node name <-> ID mapper. Internal use only."""
        return self._node_mapper

    @property
    def edge_mapper(self) -> "_EdgeMapper":
        """Edge/Link ID mapper. Internal use only."""
        return self._edge_mapper

    @property
    def algorithms(self) -> netgraph_core.Algorithms:
        """Core Algorithms instance. Internal use only."""
        return self._algorithms

    @property
    def disabled_node_ids(self) -> FrozenSet[int]:
        """Pre-computed disabled node IDs. Internal use only."""
        return self._disabled_node_ids

    @property
    def disabled_link_ids(self) -> FrozenSet[str]:
        """Pre-computed disabled link IDs. Internal use only."""
        return self._disabled_link_ids

    @property
    def link_id_to_edge_indices(self) -> Mapping[str, Tuple[int, ...]]:
        """Link ID to Core edge indices mapping. Internal use only."""
        return self._link_id_to_edge_indices

    # ──────────────────────────────────────────────────────────────
    # Factory methods
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def from_network(
        cls,
        network: "Network",
        *,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        mode: Mode = Mode.COMBINE,
        augmentations: Optional[List[AugmentationEdge]] = None,
    ) -> "AnalysisContext":
        """Create analysis context from network.

        Args:
            network: Network topology to analyze.
            source: Optional source group pattern. If provided with sink,
                    creates bound context with pre-built pseudo-nodes.
            sink: Optional sink group pattern.
            mode: Group mode (COMBINE or PAIRWISE). Only used if bound.
            augmentations: Optional custom augmentation edges.

        Returns:
            AnalysisContext ready for analysis.

        Raises:
            ValueError: If only one of source/sink is provided.
            ValueError: If bound and no matching nodes found.
        """
        if (source is None) != (sink is None):
            raise ValueError("source and sink must both be provided or both None")

        # Collect all augmentations
        all_augmentations: List[AugmentationEdge] = []
        if augmentations:
            all_augmentations.extend(augmentations)

        # Build pseudo node augmentations if source/sink provided
        pseudo_pairs: Optional[Dict[Tuple[str, str], Tuple[str, str]]] = None
        if source is not None and sink is not None:
            pseudo_augmentations, pseudo_pairs = _build_pseudo_node_augmentations(
                network, source, sink, mode
            )
            all_augmentations.extend(pseudo_augmentations)

        # Build the core graph
        ctx = _build_graph_core(
            network,
            add_reverse=True,
            augmentations=all_augmentations if all_augmentations else None,
        )

        # Create pseudo context if bound
        pseudo_context: Optional[_PseudoNodeContext] = None
        if source is not None and sink is not None:
            resolved_pairs: Dict[Tuple[str, str], Tuple[int, int]] = {}
            if pseudo_pairs:
                for pair_key, (
                    pseudo_src_name,
                    pseudo_snk_name,
                ) in pseudo_pairs.items():
                    pseudo_src_id = ctx._node_mapper.to_id(pseudo_src_name)
                    pseudo_snk_id = ctx._node_mapper.to_id(pseudo_snk_name)
                    resolved_pairs[pair_key] = (pseudo_src_id, pseudo_snk_id)

            pseudo_context = _PseudoNodeContext(
                source_path=source,
                sink_path=sink,
                mode=mode,
                pairs=resolved_pairs,
            )

        return cls(
            _network=network,
            _handle=ctx._handle,
            _multidigraph=ctx._multidigraph,
            _node_mapper=ctx._node_mapper,
            _edge_mapper=ctx._edge_mapper,
            _algorithms=ctx._algorithms,
            _disabled_node_ids=ctx._disabled_node_ids,
            _disabled_link_ids=ctx._disabled_link_ids,
            _link_id_to_edge_indices=ctx._link_id_to_edge_indices,
            _source_path=source,
            _sink_path=sink,
            _mode=mode if source is not None else None,
            _pseudo_context=pseudo_context,
        )

    # ──────────────────────────────────────────────────────────────
    # Flow analysis methods
    # ──────────────────────────────────────────────────────────────

    def max_flow(
        self,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        *,
        mode: Mode = Mode.COMBINE,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], float]:
        """Compute maximum flow between node groups.

        If context is bound (created with source/sink), uses pre-built
        pseudo-nodes for efficiency. Otherwise builds them per-call.

        Args:
            source: Source group pattern (required if unbound).
            sink: Sink group pattern (required if unbound).
            mode: COMBINE or PAIRWISE (ignored if bound).
            shortest_path: If True, use only shortest paths (IP/IGP mode).
            require_capacity: If True (default), path selection considers
                available capacity. If False, path selection is cost-only
                (true IP/IGP semantics where saturated paths still receive
                traffic). For true IP simulation, use shortest_path=True
                with require_capacity=False.
            flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP).
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.

        Returns:
            Dict mapping (source_label, sink_label) to flow value.

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
        """
        if self.is_bound:
            if source is not None or sink is not None:
                raise ValueError(
                    "Bound context: source/sink already configured. "
                    "Create new context for different groups."
                )
            return self._max_flow_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )
        else:
            if source is None or sink is None:
                raise ValueError("Unbound context: source and sink are required.")
            return self._max_flow_unbound(
                source=source,
                sink=sink,
                mode=mode,
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )

    def max_flow_detailed(
        self,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        *,
        mode: Mode = Mode.COMBINE,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
        include_min_cut: bool = False,
    ) -> Dict[Tuple[str, str], MaxFlowResult]:
        """Compute max flow with detailed results including cost distribution.

        Args:
            source: Source group pattern (required if unbound).
            sink: Sink group pattern (required if unbound).
            mode: COMBINE or PAIRWISE (ignored if bound).
            shortest_path: If True, restricts flow to shortest paths.
            require_capacity: If True (default), path selection considers
                available capacity. If False, path selection is cost-only.
            flow_placement: Flow placement strategy.
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.
            include_min_cut: If True, compute and include min-cut edges.

        Returns:
            Dict mapping (source_label, sink_label) to MaxFlowResult.
        """
        if self.is_bound:
            if source is not None or sink is not None:
                raise ValueError("Bound context: source/sink already configured.")
            return self._max_flow_detailed_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
                include_min_cut=include_min_cut,
            )
        else:
            if source is None or sink is None:
                raise ValueError("Unbound context: source and sink are required.")
            return self._max_flow_detailed_unbound(
                source=source,
                sink=sink,
                mode=mode,
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
                include_min_cut=include_min_cut,
            )

    def sensitivity(
        self,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        *,
        mode: Mode = Mode.COMBINE,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Analyze sensitivity of max flow to edge failures.

        Identifies critical edges and computes the flow reduction caused by
        removing each one.

        Args:
            source: Source group pattern (required if unbound).
            sink: Sink group pattern (required if unbound).
            mode: COMBINE or PAIRWISE (ignored if bound).
            shortest_path: If True, use shortest-path-only flow (IP/IGP mode).
            require_capacity: If True (default), path selection considers
                available capacity. If False, path selection is cost-only.
            flow_placement: Flow placement strategy.
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.

        Returns:
            Dict mapping (source_label, sink_label) to {link_id:direction: flow_reduction}.
        """
        if self.is_bound:
            if source is not None or sink is not None:
                raise ValueError("Bound context: source/sink already configured.")
            return self._sensitivity_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )
        else:
            if source is None or sink is None:
                raise ValueError("Unbound context: source and sink are required.")
            return self._sensitivity_unbound(
                source=source,
                sink=sink,
                mode=mode,
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )

    # ──────────────────────────────────────────────────────────────
    # Path analysis methods
    # ──────────────────────────────────────────────────────────────

    def shortest_path_cost(
        self,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        *,
        mode: Mode = Mode.COMBINE,
        edge_select: EdgeSelect = EdgeSelect.ALL_MIN_COST,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], float]:
        """Compute shortest path costs between node groups.

        If context is bound (created with source/sink), uses pre-configured
        groups. Otherwise source and sink arguments are required.

        Args:
            source: Source group pattern (required if unbound).
            sink: Sink group pattern (required if unbound).
            mode: COMBINE or PAIRWISE (ignored if bound).
            edge_select: SPF edge selection strategy.
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.

        Returns:
            Mapping from (source_label, sink_label) to minimal cost; inf if no path.

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
            ValueError: If no source nodes match source pattern.
            ValueError: If no sink nodes match sink pattern.
        """
        resolved_source, resolved_sink, resolved_mode = self._resolve_source_sink(
            source, sink, mode
        )
        return self._shortest_path_costs_impl(
            source=resolved_source,
            sink=resolved_sink,
            mode=resolved_mode,
            edge_select=edge_select,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    def shortest_paths(
        self,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        *,
        mode: Mode = Mode.COMBINE,
        edge_select: EdgeSelect = EdgeSelect.ALL_MIN_COST,
        split_parallel_edges: bool = False,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], List[Path]]:
        """Compute concrete shortest paths between node groups.

        If context is bound (created with source/sink), uses pre-configured
        groups. Otherwise source and sink arguments are required.

        Args:
            source: Source group pattern (required if unbound).
            sink: Sink group pattern (required if unbound).
            mode: COMBINE or PAIRWISE (ignored if bound).
            edge_select: SPF edge selection strategy.
            split_parallel_edges: Expand parallel edges into distinct paths.
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.

        Returns:
            Mapping from (source_label, sink_label) to list of Path.

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
        """
        resolved_source, resolved_sink, resolved_mode = self._resolve_source_sink(
            source, sink, mode
        )
        return self._shortest_paths_impl(
            source=resolved_source,
            sink=resolved_sink,
            mode=resolved_mode,
            edge_select=edge_select,
            split_parallel_edges=split_parallel_edges,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    def k_shortest_paths(
        self,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        *,
        mode: Mode = Mode.PAIRWISE,
        max_k: int = 3,
        edge_select: EdgeSelect = EdgeSelect.ALL_MIN_COST,
        max_path_cost: float = float("inf"),
        max_path_cost_factor: Optional[float] = None,
        split_parallel_edges: bool = False,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], List[Path]]:
        """Compute up to K shortest paths per group pair.

        If context is bound (created with source/sink), uses pre-configured
        groups. Otherwise source and sink arguments are required.

        Args:
            source: Source group pattern (required if unbound).
            sink: Sink group pattern (required if unbound).
            mode: PAIRWISE (default) or COMBINE (ignored if bound).
            max_k: Maximum paths per pair.
            edge_select: SPF/KSP edge selection strategy.
            max_path_cost: Absolute cost threshold.
            max_path_cost_factor: Relative threshold versus best path.
            split_parallel_edges: Expand parallel edges into distinct paths.
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.

        Returns:
            Mapping from (source_label, sink_label) to list of Path (<= max_k).

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
        """
        resolved_source, resolved_sink, resolved_mode = self._resolve_source_sink(
            source, sink, mode
        )
        return self._k_shortest_paths_impl(
            source=resolved_source,
            sink=resolved_sink,
            mode=resolved_mode,
            max_k=max_k,
            edge_select=edge_select,
            max_path_cost=max_path_cost,
            max_path_cost_factor=max_path_cost_factor,
            split_parallel_edges=split_parallel_edges,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    # ──────────────────────────────────────────────────────────────
    # Internal implementation methods
    # ──────────────────────────────────────────────────────────────

    def _resolve_source_sink(
        self,
        source: Optional[str],
        sink: Optional[str],
        mode: Mode,
    ) -> Tuple[str, str, Mode]:
        """Resolve source/sink from arguments or bound context.

        Args:
            source: Source pattern from method call (or None).
            sink: Sink pattern from method call (or None).
            mode: Mode from method call.

        Returns:
            Tuple of (resolved_source, resolved_sink, resolved_mode).

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
        """
        if self.is_bound:
            if source is not None or sink is not None:
                raise ValueError(
                    "Bound context: source/sink already configured. "
                    "Create new context for different groups."
                )
            # Use bound values
            return self._source_path, self._sink_path, self._mode  # type: ignore[return-value]
        else:
            if source is None or sink is None:
                raise ValueError("Unbound context: source and sink are required.")
            return source, sink, mode

    def _build_node_mask(self, excluded_nodes: Optional[Set[str]] = None) -> np.ndarray:
        """Build node mask array for Core algorithms."""
        num_nodes = len(self._node_mapper.node_names)
        mask = np.ones(num_nodes, dtype=bool)

        for node_id in self._disabled_node_ids:
            mask[node_id] = False

        if excluded_nodes:
            for node_name in excluded_nodes:
                if node_name in self._node_mapper.node_id_of:
                    mask[self._node_mapper.node_id_of[node_name]] = False

        return mask

    def _build_edge_mask(self, excluded_links: Optional[Set[str]] = None) -> np.ndarray:
        """Build edge mask array for Core algorithms."""
        num_edges = self._multidigraph.num_edges()
        mask = np.ones(num_edges, dtype=bool)

        for link_id in self._disabled_link_ids:
            if link_id in self._link_id_to_edge_indices:
                for edge_idx in self._link_id_to_edge_indices[link_id]:
                    mask[edge_idx] = False

        if excluded_links:
            for link_id in excluded_links:
                if link_id in self._link_id_to_edge_indices:
                    for edge_idx in self._link_id_to_edge_indices[link_id]:
                        mask[edge_idx] = False

        return mask

    def _map_flow_placement(
        self, flow_placement: FlowPlacement
    ) -> netgraph_core.FlowPlacement:
        """Map NetGraph FlowPlacement to Core FlowPlacement."""
        if flow_placement == FlowPlacement.PROPORTIONAL:
            return netgraph_core.FlowPlacement.PROPORTIONAL
        if flow_placement == FlowPlacement.EQUAL_BALANCED:
            return netgraph_core.FlowPlacement.EQUAL_BALANCED
        raise ValueError(f"Unsupported FlowPlacement: {flow_placement}")

    def _map_edge_select(self, edge_select: EdgeSelect) -> netgraph_core.EdgeSelection:
        """Map NetGraph EdgeSelect to Core EdgeSelection."""
        if edge_select == EdgeSelect.ALL_MIN_COST:
            return netgraph_core.EdgeSelection(
                multi_edge=True,
                require_capacity=False,
                tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
            )
        if edge_select == EdgeSelect.SINGLE_MIN_COST:
            return netgraph_core.EdgeSelection(
                multi_edge=False,
                require_capacity=False,
                tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
            )
        raise ValueError(f"Unsupported EdgeSelect: {edge_select}")

    def _max_flow_bound(
        self,
        *,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], float]:
        """Max flow using pre-built pseudo nodes."""
        core_flow_placement = self._map_flow_placement(flow_placement)
        node_mask = self._build_node_mask(excluded_nodes)
        edge_mask = self._build_edge_mask(excluded_links)

        pseudo_node_pairs = self._pseudo_context.pairs if self._pseudo_context else {}
        results: Dict[Tuple[str, str], float] = {}

        for pair_key, (pseudo_src_id, pseudo_snk_id) in pseudo_node_pairs.items():
            flow_value, _ = self._algorithms.max_flow(
                self._handle,
                pseudo_src_id,
                pseudo_snk_id,
                flow_placement=core_flow_placement,
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )
            results[pair_key] = flow_value

        # Fill missing pairs (overlapping src/snk)
        self._fill_missing_pairs_bound(results, 0.0)
        return results

    def _max_flow_unbound(
        self,
        *,
        source: str,
        sink: str,
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], float]:
        """Max flow building pseudo nodes on demand."""
        # Build a temporary bound context
        temp_ctx = AnalysisContext.from_network(
            self._network, source=source, sink=sink, mode=mode
        )
        return temp_ctx._max_flow_bound(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    def _max_flow_detailed_bound(
        self,
        *,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
        include_min_cut: bool,
    ) -> Dict[Tuple[str, str], MaxFlowResult]:
        """Detailed max flow using pre-built pseudo nodes."""
        core_flow_placement = self._map_flow_placement(flow_placement)
        node_mask = self._build_node_mask(excluded_nodes)
        edge_mask = self._build_edge_mask(excluded_links)
        ext_edge_ids = self._multidigraph.ext_edge_ids_view()

        pseudo_node_pairs = self._pseudo_context.pairs if self._pseudo_context else {}
        results: Dict[Tuple[str, str], MaxFlowResult] = {}

        for pair_key, (pseudo_src_id, pseudo_snk_id) in pseudo_node_pairs.items():
            flow_value, core_summary = self._algorithms.max_flow(
                self._handle,
                pseudo_src_id,
                pseudo_snk_id,
                flow_placement=core_flow_placement,
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )

            min_cut_edges: Optional[Tuple[EdgeRef, ...]] = None
            if include_min_cut:
                sens_results = self._algorithms.sensitivity_analysis(
                    self._handle,
                    pseudo_src_id,
                    pseudo_snk_id,
                    flow_placement=core_flow_placement,
                    shortest_path=shortest_path,
                    require_capacity=require_capacity,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                )
                edge_refs: List[EdgeRef] = []
                for edge_id, _delta in sens_results:
                    ext_id = ext_edge_ids[edge_id]
                    edge_ref = self._edge_mapper.decode_ext_id(int(ext_id))
                    if edge_ref is not None:
                        edge_refs.append(edge_ref)
                min_cut_edges = tuple(edge_refs)

            results[pair_key] = _construct_max_flow_result(
                flow_value, core_summary, min_cut_edges
            )

        # Fill missing pairs
        self._fill_missing_pairs_bound(results, _construct_max_flow_result(0.0))
        return results

    def _max_flow_detailed_unbound(
        self,
        *,
        source: str,
        sink: str,
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
        include_min_cut: bool,
    ) -> Dict[Tuple[str, str], MaxFlowResult]:
        """Detailed max flow building pseudo nodes on demand."""
        temp_ctx = AnalysisContext.from_network(
            self._network, source=source, sink=sink, mode=mode
        )
        return temp_ctx._max_flow_detailed_bound(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
            include_min_cut=include_min_cut,
        )

    def _sensitivity_bound(
        self,
        *,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Sensitivity analysis using pre-built pseudo nodes."""
        core_flow_placement = self._map_flow_placement(flow_placement)
        node_mask = self._build_node_mask(excluded_nodes)
        edge_mask = self._build_edge_mask(excluded_links)
        ext_edge_ids = self._multidigraph.ext_edge_ids_view()

        pseudo_node_pairs = self._pseudo_context.pairs if self._pseudo_context else {}
        results: Dict[Tuple[str, str], Dict[str, float]] = {}

        for pair_key, (pseudo_src_id, pseudo_snk_id) in pseudo_node_pairs.items():
            sens_results = self._algorithms.sensitivity_analysis(
                self._handle,
                pseudo_src_id,
                pseudo_snk_id,
                flow_placement=core_flow_placement,
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )

            sensitivity_map: Dict[str, float] = {}
            for edge_id, delta in sens_results:
                ext_id = ext_edge_ids[edge_id]
                edge_ref = self._edge_mapper.decode_ext_id(int(ext_id))
                if edge_ref is not None:
                    key = f"{edge_ref.link_id}:{edge_ref.direction}"
                    sensitivity_map[key] = delta

            results[pair_key] = sensitivity_map

        self._fill_missing_pairs_bound(results, {})
        return results

    def _sensitivity_unbound(
        self,
        *,
        source: str,
        sink: str,
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Sensitivity analysis building pseudo nodes on demand."""
        temp_ctx = AnalysisContext.from_network(
            self._network, source=source, sink=sink, mode=mode
        )
        return temp_ctx._sensitivity_bound(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    def _fill_missing_pairs_bound(self, results: Dict, default_value) -> None:
        """Fill results for pairs not in the graph (e.g., overlapping)."""
        if not self._pseudo_context:
            return

        src_groups = self._network.select_node_groups_by_path(self._source_path or "")
        snk_groups = self._network.select_node_groups_by_path(self._sink_path or "")

        if self._mode == Mode.COMBINE:
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))
            if (combined_src_label, combined_snk_label) not in results:
                results[(combined_src_label, combined_snk_label)] = default_value
        elif self._mode == Mode.PAIRWISE:
            for src_label in src_groups:
                for snk_label in snk_groups:
                    if (src_label, snk_label) not in results:
                        results[(src_label, snk_label)] = default_value

    def _shortest_path_costs_impl(
        self,
        *,
        source: str,
        sink: str,
        mode: Mode,
        edge_select: EdgeSelect,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], float]:
        """Implementation of shortest_path_cost."""
        from ngraph.utils.nodes import get_active_node_names

        src_groups = self._network.select_node_groups_by_path(source)
        snk_groups = self._network.select_node_groups_by_path(sink)

        if not src_groups:
            raise ValueError(f"No source nodes found matching '{source}'.")
        if not snk_groups:
            raise ValueError(f"No sink nodes found matching '{sink}'.")

        node_mask = self._build_node_mask(excluded_nodes)
        edge_mask = self._build_edge_mask(excluded_links)
        core_edge_select = self._map_edge_select(edge_select)

        if mode == Mode.COMBINE:
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))

            combined_src_names = []
            for group_nodes in src_groups.values():
                combined_src_names.extend(
                    get_active_node_names(group_nodes, excluded_nodes)
                )
            combined_snk_names = []
            for group_nodes in snk_groups.values():
                combined_snk_names.extend(
                    get_active_node_names(group_nodes, excluded_nodes)
                )

            if not combined_src_names or not combined_snk_names:
                return {(combined_src_label, combined_snk_label): float("inf")}
            if set(combined_src_names) & set(combined_snk_names):
                return {(combined_src_label, combined_snk_label): float("inf")}

            best_cost = float("inf")
            for src_name in combined_src_names:
                src_id = self._node_mapper.to_id(src_name)
                dists, _ = self._algorithms.spf(
                    self._handle,
                    src=src_id,
                    selection=core_edge_select,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                )
                for snk_name in combined_snk_names:
                    snk_id = self._node_mapper.to_id(snk_name)
                    cost = dists[snk_id]
                    if cost < best_cost:
                        best_cost = cost
            return {(combined_src_label, combined_snk_label): best_cost}

        if mode == Mode.PAIRWISE:
            results: Dict[Tuple[str, str], float] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    active_src_names = get_active_node_names(src_nodes, excluded_nodes)
                    active_snk_names = get_active_node_names(snk_nodes, excluded_nodes)
                    if not active_src_names or not active_snk_names:
                        results[(src_label, snk_label)] = float("inf")
                        continue
                    if set(active_src_names) & set(active_snk_names):
                        results[(src_label, snk_label)] = float("inf")
                        continue

                    best_cost = float("inf")
                    for src_name in active_src_names:
                        src_id = self._node_mapper.to_id(src_name)
                        dists, _ = self._algorithms.spf(
                            self._handle,
                            src=src_id,
                            selection=core_edge_select,
                            node_mask=node_mask,
                            edge_mask=edge_mask,
                        )
                        for snk_name in active_snk_names:
                            snk_id = self._node_mapper.to_id(snk_name)
                            cost = dists[snk_id]
                            if cost < best_cost:
                                best_cost = cost
                    results[(src_label, snk_label)] = best_cost
            return results

        raise ValueError(f"Invalid mode '{mode}'.")

    def _shortest_paths_impl(
        self,
        *,
        source: str,
        sink: str,
        mode: Mode,
        edge_select: EdgeSelect,
        split_parallel_edges: bool,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], List[Path]]:
        """Implementation of shortest_paths."""
        from ngraph.utils.nodes import get_active_node_names

        src_groups = self._network.select_node_groups_by_path(source)
        snk_groups = self._network.select_node_groups_by_path(sink)

        if not src_groups:
            raise ValueError(f"No source nodes found matching '{source}'.")
        if not snk_groups:
            raise ValueError(f"No sink nodes found matching '{sink}'.")

        node_mask = self._build_node_mask(excluded_nodes)
        edge_mask = self._build_edge_mask(excluded_links)
        core_edge_select = self._map_edge_select(edge_select)

        def _best_paths_for_groups(
            src_names: List[str], snk_names: List[str]
        ) -> List[Path]:
            if not src_names or not snk_names:
                return []
            if set(src_names) & set(snk_names):
                return []

            best_cost = float("inf")
            best_paths: List[Path] = []

            for src_name in src_names:
                src_id = self._node_mapper.to_id(src_name)
                dists, pred_dag = self._algorithms.spf(
                    self._handle,
                    src=src_id,
                    selection=core_edge_select,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                )
                for snk_name in snk_names:
                    snk_id = self._node_mapper.to_id(snk_name)
                    cost = dists[snk_id]
                    if cost == float("inf"):
                        continue
                    if cost < best_cost:
                        best_cost = cost
                        best_paths = _extract_paths_from_pred_dag(
                            pred_dag,
                            src_name,
                            snk_name,
                            cost,
                            self._node_mapper,
                            self._edge_mapper,
                            self._multidigraph,
                            split_parallel_edges,
                        )
                    elif cost == best_cost:
                        best_paths.extend(
                            _extract_paths_from_pred_dag(
                                pred_dag,
                                src_name,
                                snk_name,
                                cost,
                                self._node_mapper,
                                self._edge_mapper,
                                self._multidigraph,
                                split_parallel_edges,
                            )
                        )

            if best_paths:
                best_paths = sorted(set(best_paths))
            return best_paths

        if mode == Mode.COMBINE:
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))

            combined_src_names = []
            for group_nodes in src_groups.values():
                combined_src_names.extend(
                    get_active_node_names(group_nodes, excluded_nodes)
                )
            combined_snk_names = []
            for group_nodes in snk_groups.values():
                combined_snk_names.extend(
                    get_active_node_names(group_nodes, excluded_nodes)
                )

            paths_list = _best_paths_for_groups(combined_src_names, combined_snk_names)
            return {(combined_src_label, combined_snk_label): paths_list}

        if mode == Mode.PAIRWISE:
            results: Dict[Tuple[str, str], List[Path]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    active_src_names = get_active_node_names(src_nodes, excluded_nodes)
                    active_snk_names = get_active_node_names(snk_nodes, excluded_nodes)
                    results[(src_label, snk_label)] = _best_paths_for_groups(
                        active_src_names, active_snk_names
                    )
            return results

        raise ValueError(f"Invalid mode '{mode}'.")

    def _k_shortest_paths_impl(
        self,
        *,
        source: str,
        sink: str,
        mode: Mode,
        max_k: int,
        edge_select: EdgeSelect,
        max_path_cost: float,
        max_path_cost_factor: Optional[float],
        split_parallel_edges: bool,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], List[Path]]:
        """Implementation of k_shortest_paths."""
        from ngraph.utils.nodes import get_active_node_names

        src_groups = self._network.select_node_groups_by_path(source)
        snk_groups = self._network.select_node_groups_by_path(sink)

        if not src_groups:
            raise ValueError(f"No source nodes found matching '{source}'.")
        if not snk_groups:
            raise ValueError(f"No sink nodes found matching '{sink}'.")

        node_mask = self._build_node_mask(excluded_nodes)
        edge_mask = self._build_edge_mask(excluded_links)
        core_edge_select = self._map_edge_select(edge_select)

        def _ksp_for_groups(src_names: List[str], snk_names: List[str]) -> List[Path]:
            if not src_names or not snk_names:
                return []
            if set(src_names) & set(snk_names):
                return []

            # Find best pair
            best_pair: Optional[Tuple[str, str]] = None
            best_cost = float("inf")
            for src_name in src_names:
                src_id = self._node_mapper.to_id(src_name)
                dists, _ = self._algorithms.spf(
                    self._handle,
                    src=src_id,
                    selection=core_edge_select,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                )
                for snk_name in snk_names:
                    snk_id = self._node_mapper.to_id(snk_name)
                    cost = dists[snk_id]
                    if cost < best_cost:
                        best_cost = cost
                        best_pair = (src_name, snk_name)

            if best_pair is None:
                return []

            src_name, snk_name = best_pair
            src_id = self._node_mapper.to_id(src_name)
            snk_id = self._node_mapper.to_id(snk_name)

            results: List[Path] = []
            count = 0

            for dists, pred_dag in self._algorithms.ksp(
                self._handle,
                src=src_id,
                dst=snk_id,
                k=max_k,
                max_cost_factor=max_path_cost_factor,
                node_mask=node_mask,
                edge_mask=edge_mask,
            ):
                cost = dists[snk_id]
                if cost == float("inf") or cost > max_path_cost:
                    continue
                for path in _extract_paths_from_pred_dag(
                    pred_dag,
                    src_name,
                    snk_name,
                    cost,
                    self._node_mapper,
                    self._edge_mapper,
                    self._multidigraph,
                    split_parallel_edges,
                ):
                    results.append(path)
                    count += 1
                    if count >= max_k:
                        break
                if count >= max_k:
                    break

            if results:
                results = sorted(set(results))[:max_k]
            return results

        if mode == Mode.COMBINE:
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))

            combined_src_names = []
            for group_nodes in src_groups.values():
                combined_src_names.extend(
                    get_active_node_names(group_nodes, excluded_nodes)
                )
            combined_snk_names = []
            for group_nodes in snk_groups.values():
                combined_snk_names.extend(
                    get_active_node_names(group_nodes, excluded_nodes)
                )

            return {
                (combined_src_label, combined_snk_label): _ksp_for_groups(
                    combined_src_names, combined_snk_names
                )
            }

        if mode == Mode.PAIRWISE:
            results: Dict[Tuple[str, str], List[Path]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    active_src_names = get_active_node_names(src_nodes, excluded_nodes)
                    active_snk_names = get_active_node_names(snk_nodes, excluded_nodes)
                    results[(src_label, snk_label)] = _ksp_for_groups(
                        active_src_names, active_snk_names
                    )
            return results

        raise ValueError(f"Invalid mode '{mode}'.")


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helper functions
# ──────────────────────────────────────────────────────────────────────────────


def _build_pseudo_node_augmentations(
    network: "Network",
    source_path: str,
    sink_path: str,
    mode: Mode,
) -> Tuple[List[AugmentationEdge], Dict[Tuple[str, str], Tuple[str, str]]]:
    """Build augmentation edges for pseudo source/sink nodes."""
    from ngraph.utils.nodes import (
        collect_active_node_names_from_groups,
        get_active_node_names,
    )

    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    augmentations: List[AugmentationEdge] = []
    pair_to_pseudo_names: Dict[Tuple[str, str], Tuple[str, str]] = {}

    if mode == Mode.COMBINE:
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = collect_active_node_names_from_groups(src_groups)
        combined_snk_names = collect_active_node_names_from_groups(snk_groups)

        has_overlap = bool(set(combined_src_names) & set(combined_snk_names))

        if combined_src_names and combined_snk_names and not has_overlap:
            pseudo_src = "__PSEUDO_SRC__"
            pseudo_snk = "__PSEUDO_SNK__"

            for src_name in combined_src_names:
                augmentations.append(
                    AugmentationEdge(pseudo_src, src_name, LARGE_CAPACITY, 0)
                )
            for snk_name in combined_snk_names:
                augmentations.append(
                    AugmentationEdge(snk_name, pseudo_snk, LARGE_CAPACITY, 0)
                )

            pair_to_pseudo_names[(combined_src_label, combined_snk_label)] = (
                pseudo_src,
                pseudo_snk,
            )

    elif mode == Mode.PAIRWISE:
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = get_active_node_names(src_nodes)
                active_snk_names = get_active_node_names(snk_nodes)

                if set(active_src_names) & set(active_snk_names):
                    continue
                if not active_src_names or not active_snk_names:
                    continue

                pseudo_src = f"__PSEUDO_SRC_{src_label}__"
                pseudo_snk = f"__PSEUDO_SNK_{snk_label}__"

                for src_name in active_src_names:
                    augmentations.append(
                        AugmentationEdge(pseudo_src, src_name, LARGE_CAPACITY, 0)
                    )
                for snk_name in active_snk_names:
                    augmentations.append(
                        AugmentationEdge(snk_name, pseudo_snk, LARGE_CAPACITY, 0)
                    )

                pair_to_pseudo_names[(src_label, snk_label)] = (pseudo_src, pseudo_snk)

    else:
        raise ValueError(f"Invalid mode '{mode}'.")

    return augmentations, pair_to_pseudo_names


@dataclass
class _GraphBuildResult:
    """Intermediate result from _build_graph_core."""

    _handle: netgraph_core.Graph
    _multidigraph: netgraph_core.StrictMultiDiGraph
    _node_mapper: _NodeMapper
    _edge_mapper: _EdgeMapper
    _algorithms: netgraph_core.Algorithms
    _disabled_node_ids: FrozenSet[int]
    _disabled_link_ids: FrozenSet[str]
    _link_id_to_edge_indices: Mapping[str, Tuple[int, ...]]


def _build_graph_core(
    network: "Network",
    *,
    add_reverse: bool = True,
    augmentations: Optional[List[AugmentationEdge]] = None,
) -> _GraphBuildResult:
    """Build Core graph infrastructure from Network."""
    # Identify real nodes
    real_node_names = set(network.nodes.keys())

    # Infer pseudo nodes from augmentations
    pseudo_node_names: Set[str] = set()
    if augmentations:
        for aug_edge in augmentations:
            if aug_edge.source not in real_node_names:
                pseudo_node_names.add(aug_edge.source)
            if aug_edge.target not in real_node_names:
                pseudo_node_names.add(aug_edge.target)

    # Assign node IDs (real first, then pseudo)
    all_node_names = sorted(real_node_names) + sorted(pseudo_node_names)
    node_mapper = _NodeMapper(all_node_names)

    # Build edge mapper
    link_ids = sorted(network.links.keys())
    edge_mapper = _EdgeMapper(link_ids)

    # Build edge arrays
    src_list: List[int] = []
    dst_list: List[int] = []
    capacity_list: List[float] = []
    cost_list: List[float] = []
    ext_edge_id_list: List[int] = []

    for link_id in link_ids:
        link = network.links[link_id]
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

    # Add augmentation edges
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
    algorithms = netgraph_core.Algorithms(backend)
    handle = algorithms.build_graph(multidigraph)

    # Pre-compute disabled node IDs
    disabled_node_ids: Set[int] = set()
    for node_name, node in network.nodes.items():
        if node.disabled and node_name in node_mapper.node_id_of:
            disabled_node_ids.add(node_mapper.node_id_of[node_name])

    # Pre-compute disabled link IDs
    disabled_link_ids: Set[str] = {
        link_id for link_id, link in network.links.items() if link.disabled
    }

    # Pre-compute link_id -> edge indices mapping
    ext_edge_ids = multidigraph.ext_edge_ids_view()
    link_id_to_edge_indices: Dict[str, List[int]] = {}
    for edge_idx in range(len(ext_edge_ids)):
        ext_id = int(ext_edge_ids[edge_idx])
        if ext_id == -1:
            continue
        edge_ref = edge_mapper.decode_ext_id(ext_id)
        if edge_ref:
            link_id_to_edge_indices.setdefault(edge_ref.link_id, []).append(edge_idx)

    # Convert to immutable structures
    frozen_link_id_to_edge_indices = {
        k: tuple(v) for k, v in link_id_to_edge_indices.items()
    }

    return _GraphBuildResult(
        _handle=handle,
        _multidigraph=multidigraph,
        _node_mapper=node_mapper,
        _edge_mapper=edge_mapper,
        _algorithms=algorithms,
        _disabled_node_ids=frozenset(disabled_node_ids),
        _disabled_link_ids=frozenset(disabled_link_ids),
        _link_id_to_edge_indices=frozen_link_id_to_edge_indices,
    )


def _construct_max_flow_result(
    flow_value: float,
    core_summary=None,
    min_cut: Optional[Tuple[EdgeRef, ...]] = None,
) -> MaxFlowResult:
    """Construct MaxFlowResult from Core results."""
    cost_dist: Dict[float, float] = {}
    if core_summary is not None and len(core_summary.costs) > 0:
        cost_dist = {
            float(c): float(f)
            for c, f in zip(core_summary.costs, core_summary.flows, strict=False)
        }
    return MaxFlowResult(
        total_flow=flow_value,
        cost_distribution=cost_dist,
        min_cut=min_cut,
    )


def _extract_paths_from_pred_dag(
    pred_dag: netgraph_core.PredDAG,
    src_name: str,
    snk_name: str,
    cost: float,
    node_mapper: _NodeMapper,
    edge_mapper: _EdgeMapper,
    multidigraph: netgraph_core.StrictMultiDiGraph,
    split_parallel_edges: bool,
) -> List[Path]:
    """Extract Path objects from a PredDAG."""
    src_id = node_mapper.to_id(src_name)
    snk_id = node_mapper.to_id(snk_name)

    raw_paths = pred_dag.resolve_to_paths(
        src_id, snk_id, split_parallel_edges=split_parallel_edges
    )

    paths = []
    ext_edge_ids = multidigraph.ext_edge_ids_view()

    for raw_path in raw_paths:
        path_elements: List[Tuple[str, Tuple[EdgeRef, ...]]] = []

        for node_id, edge_ids in raw_path:
            node_name = node_mapper.to_name(node_id)

            edge_refs = []
            for edge_id in edge_ids:
                ext_id = ext_edge_ids[edge_id]
                edge_ref = edge_mapper.decode_ext_id(int(ext_id))
                if edge_ref is not None:
                    edge_refs.append(edge_ref)

            path_elements.append((node_name, tuple(edge_refs)))

        paths.append(Path(tuple(path_elements), cost))

    return paths


# ──────────────────────────────────────────────────────────────────────────────
# Module-level utilities for advanced/workflow use
# ──────────────────────────────────────────────────────────────────────────────


def build_node_mask(
    ctx: AnalysisContext,
    excluded_nodes: Optional[Set[str]] = None,
) -> np.ndarray:
    """Build a node mask array for Core algorithms.

    Uses O(|excluded| + |disabled|) time complexity.
    Core semantics: True = include, False = exclude.

    Args:
        ctx: AnalysisContext with pre-computed disabled node IDs.
        excluded_nodes: Optional set of node names to exclude.

    Returns:
        Boolean numpy array of shape (num_nodes,) where True means included.
    """
    return ctx._build_node_mask(excluded_nodes)


def build_edge_mask(
    ctx: AnalysisContext,
    excluded_links: Optional[Set[str]] = None,
) -> np.ndarray:
    """Build an edge mask array for Core algorithms.

    Uses O(|excluded| + |disabled|) time complexity.
    Core semantics: True = include, False = exclude.

    Args:
        ctx: AnalysisContext with pre-computed edge index mapping.
        excluded_links: Optional set of link IDs to exclude.

    Returns:
        Boolean numpy array of shape (num_edges,) where True means included.
    """
    return ctx._build_edge_mask(excluded_links)
