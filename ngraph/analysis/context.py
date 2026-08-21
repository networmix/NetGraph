"""AnalysisContext: prepared graph state for repeated network analysis.

AnalysisContext holds the Core graph infrastructure and exposes max-flow,
shortest-path, and sensitivity analysis over it.

Usage:
    # One-off analysis
    from ngraph import analyze
    flow = analyze(network).max_flow("^A$", "^B$")

    # Repeated analysis over one prepared graph (bound context)
    ctx = analyze(network, source="^A$", sink="^B$")
    baseline = ctx.max_flow()
    degraded = ctx.max_flow(excluded_links=failed_links)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Union,
)

import netgraph_core
import numpy as np

from ngraph.dsl.selectors import normalize_selector
from ngraph.model.path import Path
from ngraph.model.selectors import select_nodes
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
        cost: Edge cost (must be an integer value; Core uses int64 costs)
    """

    __slots__ = ("source", "target", "capacity", "cost")

    def __init__(self, source: str, target: str, capacity: float, cost: float):
        self.source = source
        self.target = target
        self.capacity = capacity
        self.cost = cost


def _get_active_node_names(
    nodes: List[Any],
    excluded_nodes: Optional[Set[str]] = None,
) -> List[str]:
    """Extract names of active (non-disabled) nodes, optionally excluding some."""
    if excluded_nodes:
        return [
            n.name for n in nodes if not n.disabled and n.name not in excluded_nodes
        ]
    return [n.name for n in nodes if not n.disabled]


def _resolve_selector_groups(
    network: "Network",
    source: Union[str, Dict[str, Any]],
    sink: Union[str, Dict[str, Any]],
) -> Tuple[Dict[str, List[Any]], Dict[str, List[Any]]]:
    """Normalize source/sink selectors and resolve active node groups.

    Raises:
        ValueError: If either selector matches no nodes.
    """
    src_groups = select_nodes(
        network, normalize_selector(source, "workflow"), default_active_only=True
    )
    snk_groups = select_nodes(
        network, normalize_selector(sink, "workflow"), default_active_only=True
    )
    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink}'.")
    return src_groups, snk_groups


def _combined_group_names(
    groups: Dict[str, List[Any]],
    excluded_nodes: Optional[Set[str]] = None,
) -> Tuple[str, List[str]]:
    """Return the combined "a|b" COMBINE-mode label and active member names."""
    label = "|".join(sorted(groups.keys()))
    names: List[str] = []
    for group_nodes in groups.values():
        names.extend(_get_active_node_names(group_nodes, excluded_nodes))
    return label, names


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
    """Context for pseudo nodes created during graph construction.

    Attributes:
        pairs: Mapping from (src_label, snk_label) to pseudo node IDs for
            pairs that have pseudo nodes in the graph.
        expected_pairs: All pair keys derived from the bound selectors at
            build time, including pairs skipped for empty or overlapping
            groups. Used to fill default results without re-running node
            selection.
    """

    pairs: Dict[Tuple[str, str], Tuple[int, int]]
    expected_pairs: Tuple[Tuple[str, str], ...]


@dataclass
class AnalysisContext:
    """Prepared graph state for repeated network analysis.

    Wraps the Core graph infrastructure. Two usage patterns:

    **Unbound** - source/sink given per call:

        ctx = AnalysisContext.from_network(network)
        cost = ctx.shortest_path_cost("A", "B")
        flow = ctx.max_flow("A", "B")

    Every flow call on an unbound context builds a full temporary bound
    context, which rebuilds the graph from scratch; bind the context instead
    for repeated flow analysis.

    **Bound** - source/sink fixed at construction, reused across calls:

        ctx = AnalysisContext.from_network(
            network,
            source="^dc/",
            sink="^edge/"
        )
        baseline = ctx.max_flow()  # Uses pre-built pseudo-nodes
        degraded = ctx.max_flow(excluded_links=failed)

    Selectors, here and in every method taking one, are either a regex path
    string or a dict with ``path``/``group_by``/``match``.

    Thread Safety:
        Immutable after creation. Safe for concurrent analysis calls
        with different exclusion sets.

    Attributes:
        network: Reference to source Network (read-only).
        is_bound: True if source/sink groups are pre-configured.
    """

    # Public read-only reference
    _network: "Network"

    # Core infrastructure (internal). Built eagerly for bound contexts and
    # contexts with custom augmentations; lazily on first access otherwise.
    _core: Optional[_GraphBuildResult] = field(default=None, repr=False)

    # Binding state (None if unbound)
    _source: Optional[Union[str, Dict[str, Any]]] = None
    _sink: Optional[Union[str, Dict[str, Any]]] = None
    _mode: Optional[Mode] = None
    _pseudo_context: Optional[_PseudoNodeContext] = field(default=None, repr=False)

    # User-supplied augmentations (excludes pseudo source/sink edges)
    _augmentations: Tuple[AugmentationEdge, ...] = field(default=(), repr=False)

    # Guards the lazy Core graph build
    _core_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    @property
    def network(self) -> "Network":
        """Reference to source network (read-only)."""
        return self._network

    @property
    def is_bound(self) -> bool:
        """True if source/sink groups are pre-configured."""
        return self._source is not None

    @property
    def bound_source(self) -> Optional[Union[str, Dict[str, Any]]]:
        """Source selector if bound, None otherwise."""
        return self._source

    @property
    def bound_sink(self) -> Optional[Union[str, Dict[str, Any]]]:
        """Sink selector if bound, None otherwise."""
        return self._sink

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
    # Lazy Core graph access (internal)
    # ──────────────────────────────────────────────────────────────

    def _ensure_core(self) -> _GraphBuildResult:
        """Return the Core graph build, constructing it lazily if needed.

        Bound contexts and contexts with custom augmentations build the
        graph eagerly in from_network; plain unbound contexts defer the
        build until a path-analysis method or Core accessor needs it.
        """
        core = self._core
        if core is None:
            with self._core_lock:
                core = self._core
                if core is None:
                    core = _build_graph_core(
                        self._network,
                        add_reverse=True,
                        augmentations=(
                            list(self._augmentations) if self._augmentations else None
                        ),
                    )
                    self._core = core
        return core

    @property
    def _handle(self) -> netgraph_core.Graph:
        return self._ensure_core()._handle

    @property
    def _multidigraph(self) -> netgraph_core.StrictMultiDiGraph:
        return self._ensure_core()._multidigraph

    @property
    def _node_mapper(self) -> _NodeMapper:
        return self._ensure_core()._node_mapper

    @property
    def _edge_mapper(self) -> _EdgeMapper:
        return self._ensure_core()._edge_mapper

    @property
    def _algorithms(self) -> netgraph_core.Algorithms:
        return self._ensure_core()._algorithms

    @property
    def _disabled_node_ids(self) -> FrozenSet[int]:
        return self._ensure_core()._disabled_node_ids

    @property
    def _disabled_link_ids(self) -> FrozenSet[str]:
        return self._ensure_core()._disabled_link_ids

    @property
    def _link_id_to_edge_indices(self) -> Mapping[str, Tuple[int, ...]]:
        return self._ensure_core()._link_id_to_edge_indices

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
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
        mode: Mode = Mode.COMBINE,
        augmentations: Optional[List[AugmentationEdge]] = None,
    ) -> "AnalysisContext":
        """Create analysis context from network.

        Args:
            network: Network topology to analyze.
            source: Optional source node selector (string path or selector dict).
                    If provided with sink, creates bound context with pre-built pseudo-nodes.
            sink: Optional sink node selector (string path or selector dict).
            mode: Group mode (COMBINE or PAIRWISE). Only used if bound.
            augmentations: Optional custom augmentation edges.

        Returns:
            AnalysisContext ready for analysis.

        Raises:
            ValueError: If only one of source/sink is provided.
            ValueError: If bound and no matching nodes found.
            ValueError: If any link capacity is at or above LARGE_CAPACITY
                (1e15, the internal pseudo-edge capacity), since such a link
                would be silently clamped by the pseudo attachment edges in
                combine-mode flows.
            ValueError: If any link or augmentation cost is negative or
                non-integer, or if the total of all edge costs reaches 2**62.
                Core's int64 cost arithmetic would overflow and silently
                corrupt SPF and flow results.

        Note:
            The capacity and cost checks run during the graph build, which
            happens here for bound contexts and for contexts with custom
            augmentations, and on first use otherwise.
        """
        if (source is None) != (sink is None):
            raise ValueError("source and sink must both be provided or both None")

        # Collect all augmentations
        all_augmentations: List[AugmentationEdge] = []
        if augmentations:
            all_augmentations.extend(augmentations)

        # Build pseudo node augmentations if source/sink provided
        pseudo_pairs: Optional[Dict[Tuple[str, str], Tuple[str, str]]] = None
        expected_pairs: Tuple[Tuple[str, str], ...] = ()
        if source is not None and sink is not None:
            pseudo_augmentations, pseudo_pairs, expected_pairs = (
                _build_pseudo_node_augmentations(network, source, sink, mode)
            )
            all_augmentations.extend(pseudo_augmentations)

        # Build the core graph eagerly when bound (pseudo node IDs must be
        # resolved now) or when custom augmentations are present. Plain
        # unbound contexts build lazily on first use.
        core: Optional[_GraphBuildResult] = None
        if all_augmentations or source is not None:
            core = _build_graph_core(
                network,
                add_reverse=True,
                augmentations=all_augmentations if all_augmentations else None,
            )

        # Create pseudo context if bound
        pseudo_context: Optional[_PseudoNodeContext] = None
        if source is not None and sink is not None:
            assert core is not None  # Bound contexts always build eagerly
            resolved_pairs: Dict[Tuple[str, str], Tuple[int, int]] = {}
            if pseudo_pairs:
                for pair_key, (
                    pseudo_src_name,
                    pseudo_snk_name,
                ) in pseudo_pairs.items():
                    pseudo_src_id = core._node_mapper.to_id(pseudo_src_name)
                    pseudo_snk_id = core._node_mapper.to_id(pseudo_snk_name)
                    resolved_pairs[pair_key] = (pseudo_src_id, pseudo_snk_id)

            pseudo_context = _PseudoNodeContext(
                pairs=resolved_pairs,
                expected_pairs=expected_pairs,
            )

        return cls(
            _network=network,
            _core=core,
            _source=source,
            _sink=sink,
            _mode=mode if source is not None else None,
            _pseudo_context=pseudo_context,
            _augmentations=tuple(augmentations) if augmentations else (),
        )

    # ──────────────────────────────────────────────────────────────
    # Flow analysis methods
    # ──────────────────────────────────────────────────────────────

    def _dispatch_bound(
        self,
        source: Optional[Union[str, Dict[str, Any]]],
        sink: Optional[Union[str, Dict[str, Any]]],
    ) -> bool:
        """Validate source/sink against the binding state of this context.

        Returns:
            True when the context is bound (dispatch to the *_bound path);
            False when unbound (source and sink are then non-None).

        Raises:
            ValueError: If bound and source/sink are provided, or unbound
                and source/sink are missing.
        """
        if self.is_bound:
            if source is not None or sink is not None:
                raise ValueError(
                    "Bound context: source/sink already configured. "
                    "Create new context for different groups."
                )
            return True
        if source is None or sink is None:
            raise ValueError("Unbound context: source and sink are required.")
        return False

    def max_flow(
        self,
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
        *,
        mode: Mode = Mode.COMBINE,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], float]:
        """Compute maximum flow between node groups.

        If context is bound (created with source/sink), reuses its pre-built
        pseudo-nodes. If unbound, each call rebuilds the graph (see "Unbound"
        in the class docstring).

        Args:
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
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
        if self._dispatch_bound(source, sink):
            return self._max_flow_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )
        assert source is not None and sink is not None
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
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
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

        If unbound, each call rebuilds the graph (see "Unbound" in the class
        docstring).

        Args:
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
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
        if self._dispatch_bound(source, sink):
            return self._max_flow_detailed_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
                include_min_cut=include_min_cut,
            )
        assert source is not None and sink is not None
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
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
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

        If unbound, each call rebuilds the graph (see "Unbound" in the class
        docstring).

        Args:
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
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
        if self._dispatch_bound(source, sink):
            return self._sensitivity_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )
        assert source is not None and sink is not None
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

    def sensitivity_with_flow(
        self,
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
        *,
        mode: Mode = Mode.COMBINE,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
        excluded_nodes: Optional[Set[str]] = None,
        excluded_links: Optional[Set[str]] = None,
    ) -> Dict[Tuple[str, str], Tuple[float, Dict[str, float]]]:
        """Compute max flow and edge sensitivity together per group pair.

        Produces the same values as calling max_flow and sensitivity with
        identical arguments, but builds the node/edge masks once and walks
        the group pairs once. Prefer this on repeated-analysis hot paths
        (e.g., Monte Carlo iterations) when both results are needed.

        If unbound, each call rebuilds the graph (see "Unbound" in the class
        docstring).

        Args:
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
            mode: COMBINE or PAIRWISE (ignored if bound).
            shortest_path: If True, use shortest-path-only flow (IP/IGP mode).
            require_capacity: If True (default), path selection considers
                available capacity. If False, path selection is cost-only.
            flow_placement: Flow placement strategy.
            excluded_nodes: Nodes to exclude from this analysis.
            excluded_links: Links to exclude from this analysis.

        Returns:
            Dict mapping (source_label, sink_label) to a tuple of
            (max flow value, {link_id:direction: flow_reduction}).

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
        """
        if self._dispatch_bound(source, sink):
            return self._sensitivity_with_flow_bound(
                shortest_path=shortest_path,
                require_capacity=require_capacity,
                flow_placement=flow_placement,
                excluded_nodes=excluded_nodes,
                excluded_links=excluded_links,
            )
        assert source is not None and sink is not None
        return self._sensitivity_with_flow_unbound(
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
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
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
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
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
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
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
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
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
        source: Optional[Union[str, Dict[str, Any]]] = None,
        sink: Optional[Union[str, Dict[str, Any]]] = None,
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
            source: Source node selector (required if unbound); see the class
                docstring for the accepted selector forms.
            sink: Sink node selector (required if unbound).
            mode: PAIRWISE (default) or COMBINE (ignored if bound).
            max_k: Maximum paths per pair.
            edge_select: SPF/KSP edge selection strategy. Note: it governs
                only the pruning SPF pass; Core's KSP enumeration uses a
                fixed internal selection (all parallel min-cost edges,
                capacity-blind, deterministic tie-break), so SINGLE_MIN_COST
                may yield one path per parallel edge where `shortest_paths`
                returns one.
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
        source: Optional[Union[str, Dict[str, Any]]],
        sink: Optional[Union[str, Dict[str, Any]]],
        mode: Mode,
    ) -> Tuple[Union[str, Dict[str, Any]], Union[str, Dict[str, Any]], Mode]:
        """Resolve source/sink from arguments or bound context.

        Args:
            source: Source selector from method call (or None).
            sink: Sink selector from method call (or None).
            mode: Mode from method call.

        Returns:
            Tuple of (resolved_source, resolved_sink, resolved_mode).
            Selectors can be string patterns or dict selectors.

        Raises:
            ValueError: If unbound and source/sink not provided.
            ValueError: If bound and source/sink are provided.
        """
        if self._dispatch_bound(source, sink):
            # Use bound values (can be str or dict)
            return self._source, self._sink, self._mode  # type: ignore[return-value]
        assert source is not None and sink is not None
        return source, sink, mode

    def build_node_mask(self, excluded_nodes: Optional[Set[str]] = None) -> np.ndarray:
        """Build a node inclusion mask for Core algorithms.

        Core mask semantics: True includes the node, False excludes it.
        Disabled nodes are always excluded, on top of any names passed in
        ``excluded_nodes``. Building the mask costs an O(num_nodes) fill plus
        O(|excluded| + |disabled|) updates, so it is cheap enough to redo per
        failure iteration. Useful for custom analysis functions that call
        Core primitives directly.

        Args:
            excluded_nodes: Optional set of node names to exclude. Names not
                present in the graph are ignored.

        Returns:
            Boolean numpy array of shape (num_nodes,) where True means
            included.
        """
        num_nodes = len(self._node_mapper.node_names)
        mask = np.ones(num_nodes, dtype=bool)

        for node_id in self._disabled_node_ids:
            mask[node_id] = False

        if excluded_nodes:
            for node_name in excluded_nodes:
                if node_name in self._node_mapper.node_id_of:
                    mask[self._node_mapper.node_id_of[node_name]] = False

        return mask

    def build_edge_mask(self, excluded_links: Optional[Set[str]] = None) -> np.ndarray:
        """Build an edge inclusion mask for Core algorithms.

        Core mask semantics: True includes the edge, False excludes it. Edges
        of disabled links are always excluded, on top of any IDs passed in
        ``excluded_links``. Building the mask costs an O(num_edges) fill plus
        O(|excluded| + |disabled|) updates, so it is cheap enough to redo per
        failure iteration. Useful for custom analysis functions that call
        Core primitives directly.

        Args:
            excluded_links: Optional set of link IDs to exclude. IDs not
                present in the graph are ignored.

        Returns:
            Boolean numpy array of shape (num_edges,) where True means
            included. There is one entry per Core edge - forward and reverse
            direction of each link, plus any augmentation edges - not one
            entry per link.
        """
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
        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)

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
        self._fill_missing_pairs_bound(results, lambda: 0.0)
        return results

    def _bind_temp(
        self,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
    ) -> "AnalysisContext":
        """Build a temporary bound context, preserving custom augmentations.

        Owns the re-binding semantics for all `_*_unbound` methods so state
        that must survive re-binding (e.g. augmentations) is handled once.
        """
        return AnalysisContext.from_network(
            self._network,
            source=source,
            sink=sink,
            mode=mode,
            augmentations=list(self._augmentations) if self._augmentations else None,
        )

    def _max_flow_unbound(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], float]:
        """Max flow building pseudo nodes on demand."""
        return self._bind_temp(source, sink, mode)._max_flow_bound(
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
        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)
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
                # core_summary.min_cut holds the true minimum cut; pseudo
                # edges (ext id -1) are filtered out by decode_ext_id.
                edge_refs: List[EdgeRef] = []
                for edge_id in core_summary.min_cut.edges:
                    ext_id = ext_edge_ids[int(edge_id)]
                    edge_ref = self._edge_mapper.decode_ext_id(int(ext_id))
                    if edge_ref is not None:
                        edge_refs.append(edge_ref)
                min_cut_edges = tuple(edge_refs)

            results[pair_key] = _construct_max_flow_result(
                flow_value, core_summary, min_cut_edges
            )

        # Fill missing pairs
        self._fill_missing_pairs_bound(results, lambda: _construct_max_flow_result(0.0))
        return results

    def _max_flow_detailed_unbound(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
        include_min_cut: bool,
    ) -> Dict[Tuple[str, str], MaxFlowResult]:
        """Detailed max flow building pseudo nodes on demand."""
        return self._bind_temp(source, sink, mode)._max_flow_detailed_bound(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
            include_min_cut=include_min_cut,
        )

    def _decode_sensitivity_map(
        self, sens_results: Any, ext_edge_ids: Any
    ) -> Dict[str, float]:
        """Decode core sensitivity results into a {"link_id:direction": delta} map."""
        sensitivity_map: Dict[str, float] = {}
        for edge_id, delta in sens_results:
            ext_id = ext_edge_ids[edge_id]
            edge_ref = self._edge_mapper.decode_ext_id(int(ext_id))
            if edge_ref is not None:
                sensitivity_map[f"{edge_ref.link_id}:{edge_ref.direction}"] = delta
        return sensitivity_map

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
        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)
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

            results[pair_key] = self._decode_sensitivity_map(sens_results, ext_edge_ids)

        self._fill_missing_pairs_bound(results, lambda: {})
        return results

    def _sensitivity_unbound(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Sensitivity analysis building pseudo nodes on demand."""
        return self._bind_temp(source, sink, mode)._sensitivity_bound(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    def _sensitivity_with_flow_bound(
        self,
        *,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], Tuple[float, Dict[str, float]]]:
        """Max flow plus sensitivity in one pass over pre-built pseudo nodes.

        Builds node/edge masks once and iterates the bound pairs once
        instead of duplicating that work across separate max_flow and
        sensitivity calls. Core still computes the baseline flow internally
        for the sensitivity deltas; only the Python-side duplication
        (masks and pair iteration) is removed here.
        """
        core_flow_placement = self._map_flow_placement(flow_placement)
        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)
        ext_edge_ids = self._multidigraph.ext_edge_ids_view()

        pseudo_node_pairs = self._pseudo_context.pairs if self._pseudo_context else {}
        results: Dict[Tuple[str, str], Tuple[float, Dict[str, float]]] = {}

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

            results[pair_key] = (
                flow_value,
                self._decode_sensitivity_map(sens_results, ext_edge_ids),
            )

        self._fill_missing_pairs_bound(results, lambda: (0.0, {}))
        return results

    def _sensitivity_with_flow_unbound(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
        shortest_path: bool,
        require_capacity: bool,
        flow_placement: FlowPlacement,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], Tuple[float, Dict[str, float]]]:
        """Max flow plus sensitivity building pseudo nodes on demand."""
        return self._bind_temp(source, sink, mode)._sensitivity_with_flow_bound(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

    def _fill_missing_pairs_bound(
        self, results: Dict, default_factory: Callable[[], Any]
    ) -> None:
        """Fill results for pairs not in the graph (e.g., overlapping).

        Uses pair keys precomputed at bind time; no node selection is
        re-run (the context is immutable after creation). The factory is
        called once per missing pair so mutable defaults (dicts, result
        objects) are never aliased across pairs.
        """
        if not self._pseudo_context:
            return
        for pair_key in self._pseudo_context.expected_pairs:
            if pair_key not in results:
                results[pair_key] = default_factory()

    def _shortest_path_costs_impl(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
        edge_select: EdgeSelect,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], float]:
        """Implementation of shortest_path_cost."""
        src_groups, snk_groups = _resolve_selector_groups(self._network, source, sink)

        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)
        core_edge_select = self._map_edge_select(edge_select)

        def _best_cost_for_groups(src_names: List[str], snk_names: List[str]) -> float:
            if not src_names or not snk_names:
                return float("inf")
            if set(src_names) & set(snk_names):
                return float("inf")

            best_cost = float("inf")
            for src_name in src_names:
                dists, _ = self._algorithms.spf(
                    self._handle,
                    src=self._node_mapper.to_id(src_name),
                    selection=core_edge_select,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                )
                for snk_name in snk_names:
                    cost = dists[self._node_mapper.to_id(snk_name)]
                    if cost < best_cost:
                        best_cost = cost
            return best_cost

        if mode == Mode.COMBINE:
            combined_src_label, combined_src_names = _combined_group_names(
                src_groups, excluded_nodes
            )
            combined_snk_label, combined_snk_names = _combined_group_names(
                snk_groups, excluded_nodes
            )
            return {
                (combined_src_label, combined_snk_label): _best_cost_for_groups(
                    combined_src_names, combined_snk_names
                )
            }

        if mode == Mode.PAIRWISE:
            results: Dict[Tuple[str, str], float] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    results[(src_label, snk_label)] = _best_cost_for_groups(
                        _get_active_node_names(src_nodes, excluded_nodes),
                        _get_active_node_names(snk_nodes, excluded_nodes),
                    )
            return results

        raise ValueError(f"Invalid mode '{mode}'.")

    def _shortest_paths_impl(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
        mode: Mode,
        edge_select: EdgeSelect,
        split_parallel_edges: bool,
        excluded_nodes: Optional[Set[str]],
        excluded_links: Optional[Set[str]],
    ) -> Dict[Tuple[str, str], List[Path]]:
        """Implementation of shortest_paths."""
        src_groups, snk_groups = _resolve_selector_groups(self._network, source, sink)

        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)
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
                best_paths = sorted(set(best_paths), key=_path_sort_key)
            return best_paths

        if mode == Mode.COMBINE:
            combined_src_label, combined_src_names = _combined_group_names(
                src_groups, excluded_nodes
            )
            combined_snk_label, combined_snk_names = _combined_group_names(
                snk_groups, excluded_nodes
            )

            paths_list = _best_paths_for_groups(combined_src_names, combined_snk_names)
            return {(combined_src_label, combined_snk_label): paths_list}

        if mode == Mode.PAIRWISE:
            results: Dict[Tuple[str, str], List[Path]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    active_src_names = _get_active_node_names(src_nodes, excluded_nodes)
                    active_snk_names = _get_active_node_names(snk_nodes, excluded_nodes)
                    results[(src_label, snk_label)] = _best_paths_for_groups(
                        active_src_names, active_snk_names
                    )
            return results

        raise ValueError(f"Invalid mode '{mode}'.")

    def _k_shortest_paths_impl(
        self,
        *,
        source: Union[str, Dict[str, Any]],
        sink: Union[str, Dict[str, Any]],
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
        src_groups, snk_groups = _resolve_selector_groups(self._network, source, sink)

        node_mask = self.build_node_mask(excluded_nodes)
        edge_mask = self.build_edge_mask(excluded_links)
        core_edge_select = self._map_edge_select(edge_select)

        def _ksp_for_groups(src_names: List[str], snk_names: List[str]) -> List[Path]:
            if not src_names or not snk_names:
                return []
            if set(src_names) & set(snk_names):
                return []

            # SPF pass: per-pair shortest costs and the global best cost
            pair_costs: Dict[Tuple[str, str], float] = {}
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
                    if cost == float("inf"):
                        continue
                    pair_costs[(src_name, snk_name)] = cost
                    if cost < best_cost:
                        best_cost = cost

            if not pair_costs:
                return []

            # Absolute cost cap; max_path_cost_factor is relative to the
            # best cost across ALL pairs, so per-pair KSP runs unbounded
            # (max_cost_factor=None) and paths are filtered by this cap.
            cost_cap = max_path_cost
            if max_path_cost_factor is not None:
                cost_cap = min(cost_cap, best_cost * max_path_cost_factor)

            # KSP per reachable pair within the cap, cheapest pairs first.
            # Every path for a pair costs at least that pair's shortest
            # cost, so once max_k unique paths are collected the loop stops
            # as soon as the next pair's shortest cost strictly exceeds the
            # current k-th best path cost: no remaining pair can contribute
            # a path that survives the final top-k truncation. Pairs tied
            # at the boundary are still explored so equal-cost truncation
            # stays deterministic via _path_sort_key.
            merged: Set[Path] = set()
            kth_best_cost = float("inf")
            for (src_name, snk_name), pair_cost in sorted(
                pair_costs.items(), key=lambda kv: (kv[1], kv[0])
            ):
                if pair_cost > cost_cap:
                    break  # Pairs are cost-sorted; the rest exceed the cap too
                if len(merged) >= max_k and pair_cost > kth_best_cost:
                    break
                src_id = self._node_mapper.to_id(src_name)
                snk_id = self._node_mapper.to_id(snk_name)

                count = 0
                for dists, pred_dag in self._algorithms.ksp(
                    self._handle,
                    src=src_id,
                    dst=snk_id,
                    k=max_k,
                    max_cost_factor=None,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                ):
                    cost = dists[snk_id]
                    if cost == float("inf"):
                        continue
                    if cost > cost_cap:
                        break  # KSP yields costs in non-decreasing order
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
                        merged.add(path)
                        count += 1
                        if count >= max_k:
                            break
                    if count >= max_k:
                        break

                if len(merged) >= max_k:
                    kth_best_cost = sorted(p.cost for p in merged)[max_k - 1]

            return sorted(merged, key=_path_sort_key)[:max_k]

        if mode == Mode.COMBINE:
            combined_src_label, combined_src_names = _combined_group_names(
                src_groups, excluded_nodes
            )
            combined_snk_label, combined_snk_names = _combined_group_names(
                snk_groups, excluded_nodes
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
                    active_src_names = _get_active_node_names(src_nodes, excluded_nodes)
                    active_snk_names = _get_active_node_names(snk_nodes, excluded_nodes)
                    results[(src_label, snk_label)] = _ksp_for_groups(
                        active_src_names, active_snk_names
                    )
            return results

        raise ValueError(f"Invalid mode '{mode}'.")


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helper functions
# ──────────────────────────────────────────────────────────────────────────────


def _path_sort_key(path: Path) -> Tuple[Any, ...]:
    """Deterministic total-order sort key for Path objects.

    Path.__lt__ compares cost only, so sorting equal-cost paths with the
    default ordering preserves set-iteration order, which varies with
    string-hash randomization (PYTHONHASHSEED). This key orders by cost,
    then node sequence, then the structural edge sequence (link ids and
    directions). Any two distinct paths differ in the key, so sorted
    output and equal-cost truncation (e.g., k_shortest_paths max_k) are
    independent of hash order. Paths that differ only in which parallel
    link they traverse still order by link id, which embeds a build-time
    UUID; node-sequence-level selection is stable across runs.
    """
    return (
        path.cost,
        path.nodes_seq,
        tuple(
            tuple((edge.link_id, edge.direction) for edge in edges) for _, edges in path
        ),
    )


def _build_pseudo_node_augmentations(
    network: "Network",
    source: Union[str, Dict[str, Any]],
    sink: Union[str, Dict[str, Any]],
    mode: Mode,
) -> Tuple[
    List[AugmentationEdge],
    Dict[Tuple[str, str], Tuple[str, str]],
    Tuple[Tuple[str, str], ...],
]:
    """Build augmentation edges for pseudo source/sink nodes.

    Returns:
        Tuple of (augmentation edges, pair -> pseudo node names for pairs
        materialized in the graph, all expected pair keys including pairs
        skipped for empty or overlapping groups).
    """
    src_groups, snk_groups = _resolve_selector_groups(network, source, sink)

    augmentations: List[AugmentationEdge] = []
    pair_to_pseudo_names: Dict[Tuple[str, str], Tuple[str, str]] = {}
    expected_pairs: Tuple[Tuple[str, str], ...]

    if mode == Mode.COMBINE:
        combined_src_label, combined_src_names = _combined_group_names(src_groups)
        combined_snk_label, combined_snk_names = _combined_group_names(snk_groups)
        expected_pairs = ((combined_src_label, combined_snk_label),)

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
        expected_pairs = tuple(
            (src_label, snk_label)
            for src_label in src_groups
            for snk_label in snk_groups
        )

        src_names_of = {
            label: [n.name for n in nodes] for label, nodes in src_groups.items()
        }
        snk_names_of = {
            label: [n.name for n in nodes] for label, nodes in snk_groups.items()
        }

        # Hoisted out of the pair loop: one set per group, not one per pair.
        src_name_sets = {label: set(names) for label, names in src_names_of.items()}
        snk_name_sets = {label: set(names) for label, names in snk_names_of.items()}

        # Pass 1: determine valid pairs and which groups participate in
        # at least one valid pair (no pseudo nodes for orphan groups).
        participating_src: Set[str] = set()
        participating_snk: Set[str] = set()
        for src_label, src_names in src_names_of.items():
            for snk_label, snk_names in snk_names_of.items():
                if not src_names or not snk_names:
                    continue
                if src_name_sets[src_label] & snk_name_sets[snk_label]:
                    continue

                pair_to_pseudo_names[(src_label, snk_label)] = (
                    f"__PSEUDO_SRC_{src_label}__",
                    f"__PSEUDO_SNK_{snk_label}__",
                )
                participating_src.add(src_label)
                participating_snk.add(snk_label)

        # Pass 2: emit attachment edges once per participating group
        # member (not once per opposing group).
        for src_label, src_names in src_names_of.items():
            if src_label not in participating_src:
                continue
            pseudo_src = f"__PSEUDO_SRC_{src_label}__"
            for src_name in src_names:
                augmentations.append(
                    AugmentationEdge(pseudo_src, src_name, LARGE_CAPACITY, 0)
                )
        for snk_label, snk_names in snk_names_of.items():
            if snk_label not in participating_snk:
                continue
            pseudo_snk = f"__PSEUDO_SNK_{snk_label}__"
            for snk_name in snk_names:
                augmentations.append(
                    AugmentationEdge(snk_name, pseudo_snk, LARGE_CAPACITY, 0)
                )

    else:
        raise ValueError(f"Invalid mode '{mode}'.")

    return augmentations, pair_to_pseudo_names, expected_pairs


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

    link_ids = sorted(network.links.keys())
    edge_mapper = _EdgeMapper(link_ids)

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

    src_arr = np.array(src_list, dtype=np.int32)
    dst_arr = np.array(dst_list, dtype=np.int32)
    capacity_arr = np.array(capacity_list, dtype=np.float64)

    # Pseudo attachment edges carry LARGE_CAPACITY; a real capacity at or
    # above it would be silently clamped by those edges in combine-mode
    # flows, so reject it loudly instead.
    oversized = [
        link_id
        for link_id in link_ids
        if float(network.links[link_id].capacity) >= LARGE_CAPACITY
    ]
    if oversized:
        raise ValueError(
            f"Link capacities must be below {LARGE_CAPACITY:g} (the internal "
            f"pseudo-edge capacity); offending links: {', '.join(oversized[:5])}"
        )

    # Core requires int64 costs; validate integrality instead of silently
    # truncating (which would corrupt SPF/flow results).
    cost_f = np.asarray(cost_list, dtype=np.float64)
    # Core SPF uses int64 costs with INT64_MAX as the unreachable sentinel and
    # computes d_u + edge_cost without overflow checks, so ACCUMULATED path
    # costs must stay below 2**62 (a reverse-edge bounce can double a cost of
    # 2**62 past INT64_MAX and wrap negative). Bounding the total of all edge
    # costs bounds every simple path.
    if np.any(cost_f < 0) or float(cost_f.sum()) >= 2**62:
        raise ValueError(
            "Link costs must be non-negative and their total must stay below "
            "2**62: larger accumulated path costs overflow the core engine's "
            "int64 cost arithmetic and silently corrupt results"
        )
    if not np.array_equal(cost_f, np.trunc(cost_f)):
        bad_indices = np.nonzero(cost_f != np.trunc(cost_f))[0]
        edges_per_link = 2 if add_reverse else 1
        num_link_edges = len(link_ids) * edges_per_link
        offenders: List[str] = []
        for idx in bad_indices:
            if idx < num_link_edges:
                link_id = link_ids[int(idx) // edges_per_link]
                desc = f"link {link_id!r} (cost {network.links[link_id].cost})"
            else:
                aug = (augmentations or [])[int(idx) - num_link_edges]
                desc = f"augmentation {aug.source!r}->{aug.target!r} (cost {aug.cost})"
            if desc not in offenders:
                offenders.append(desc)
        raise ValueError(
            "Non-integer link costs are not supported by the analysis engine "
            f"(costs are int64): {', '.join(offenders)}"
        )
    cost_arr = cost_f.astype(np.int64)

    ext_edge_ids_arr = np.array(ext_edge_id_list, dtype=np.int64)

    multidigraph = netgraph_core.StrictMultiDiGraph.from_arrays(
        num_nodes=len(all_node_names),
        src=src_arr,
        dst=dst_arr,
        capacity=capacity_arr,
        cost=cost_arr,
        ext_edge_ids=ext_edge_ids_arr,
    )

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
            for c, f in zip(core_summary.costs, core_summary.flows, strict=True)
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


def analyze(
    network: "Network",
    *,
    source: Optional[Union[str, Dict[str, Any]]] = None,
    sink: Optional[Union[str, Dict[str, Any]]] = None,
    mode: Mode = Mode.COMBINE,
    augmentations: Optional[List[AugmentationEdge]] = None,
) -> AnalysisContext:
    """Create an analysis context for the network.

    Primary entry point for network analysis in NetGraph.

    Args:
        network: Network topology to analyze.
        source: Optional source node selector (string path or selector dict).
                If provided with sink, creates a bound context whose pseudo
                nodes are pre-built once and reused by every flow call.
        sink: Optional sink node selector (string path or selector dict).
        mode: Group mode (COMBINE or PAIRWISE). Only used if bound.
        augmentations: Optional custom augmentation edges.

    Returns:
        AnalysisContext ready for analysis calls.

    Raises:
        ValueError: If only one of source/sink is provided, or if a bound
            selector matches no nodes.
        ValueError: If any link capacity is at or above LARGE_CAPACITY (1e15,
            the internal pseudo-edge capacity), since such a link would be
            silently clamped by the pseudo attachment edges in combine-mode
            flows.
        ValueError: If any link or augmentation cost is negative or
            non-integer, or if the total of all edge costs reaches 2**62.
            Core's int64 cost arithmetic would overflow and silently corrupt
            SPF and flow results.

    Note:
        The capacity and cost checks run during the graph build, which happens
        here for bound contexts and for contexts with custom augmentations,
        and on first use otherwise.

    Examples:
        One-off analysis (unbound context):

            flow = analyze(network).max_flow("^A$", "^B$")
            paths = analyze(network).shortest_paths("^A$", "^B$")

        Repeated analysis over one prepared graph (bound context):

            ctx = analyze(network, source="^dc/", sink="^edge/")
            baseline = ctx.max_flow()
            degraded = ctx.max_flow(excluded_links=failed_links)

        Multiple exclusion scenarios:

            ctx = analyze(network, source="^A$", sink="^B$")
            for scenario in failure_scenarios:
                result = ctx.max_flow(excluded_links=scenario)
    """
    return AnalysisContext.from_network(
        network,
        source=source,
        sink=sink,
        mode=mode,
        augmentations=augmentations,
    )
