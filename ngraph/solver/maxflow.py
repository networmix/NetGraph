"""Max-flow computation between node groups with NetGraph-Core integration.

This module provides max-flow analysis for Network models by transforming
multi-source/multi-sink problems into single-source/single-sink problems
using pseudo nodes.

Graph caching enables efficient repeated analysis with different exclusion
sets by building the graph with pseudo nodes once and using O(|excluded|)
masks for exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import netgraph_core
import numpy as np

from ngraph.adapters.core import AugmentationEdge, EdgeMapper, NodeMapper, build_graph
from ngraph.model.network import Network
from ngraph.types.base import FlowPlacement
from ngraph.types.dto import FlowSummary

# Large capacity for pseudo edges (avoid float('inf') due to Core limitation)
LARGE_CAPACITY = 1e15


@dataclass
class MaxFlowGraphCache:
    """Pre-built graph with pseudo nodes for efficient repeated max-flow analysis.

    Holds all components needed for running max-flow analysis with different
    exclusion sets without rebuilding the graph. Includes pre-computed pseudo
    node ID mappings for all source/sink pairs.

    Attributes:
        graph_handle: Core Graph handle for algorithm execution.
        multidigraph: Core StrictMultiDiGraph with topology data.
        edge_mapper: Mapper for link_id <-> edge_id translation.
        node_mapper: Mapper for node_name <-> node_id translation.
        algorithms: Core Algorithms instance for running computations.
        pair_to_pseudo_ids: Mapping from (src_label, snk_label) to (pseudo_src_id, pseudo_snk_id).
        disabled_node_ids: Pre-computed set of disabled node IDs.
        disabled_link_ids: Pre-computed set of disabled link IDs.
        link_id_to_edge_indices: Mapping from link_id to edge array indices.
    """

    graph_handle: netgraph_core.Graph
    multidigraph: netgraph_core.StrictMultiDiGraph
    edge_mapper: EdgeMapper
    node_mapper: NodeMapper
    algorithms: netgraph_core.Algorithms
    pair_to_pseudo_ids: Dict[Tuple[str, str], Tuple[int, int]] = field(
        default_factory=dict
    )
    disabled_node_ids: Set[int] = field(default_factory=set)
    disabled_link_ids: Set[str] = field(default_factory=set)
    link_id_to_edge_indices: Dict[str, List[int]] = field(default_factory=dict)


def build_maxflow_cache(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "combine",
) -> MaxFlowGraphCache:
    """Build cached graph with pseudo nodes for efficient repeated max-flow analysis.

    Constructs a single graph with all pseudo source/sink nodes for all
    source/sink pairs, enabling O(|excluded|) mask building per iteration
    instead of O(V+E) graph reconstruction.

    Args:
        network: Network instance.
        source_path: Selection expression for source node groups.
        sink_path: Selection expression for sink node groups.
        mode: "combine" (single pair) or "pairwise" (N×M pairs).

    Returns:
        MaxFlowGraphCache with pre-built graph and pseudo node mappings.

    Raises:
        ValueError: If no matching sources or sinks are found.
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    # Collect all augmentation edges for ALL pairs
    augmentations: List[AugmentationEdge] = []
    pair_to_pseudo_names: Dict[Tuple[str, str], Tuple[str, str]] = {}

    def _get_active_node_names(nodes: List) -> List[str]:
        """Get names of non-disabled nodes."""
        return [n.name for n in nodes if not n.disabled]

    if mode == "combine":
        # Single combined pair
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = []
        for group_nodes in src_groups.values():
            combined_src_names.extend(_get_active_node_names(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_get_active_node_names(group_nodes))

        # Remove overlap
        combined_src_names = [
            n for n in combined_src_names if n not in combined_snk_names
        ]

        if combined_src_names and combined_snk_names:
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

    elif mode == "pairwise":
        # N × M pairs
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _get_active_node_names(src_nodes)
                active_snk_names = _get_active_node_names(snk_nodes)

                # Skip overlapping pairs
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
        raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")

    # Build graph with all pseudo nodes (no exclusions - handled via masks)
    graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(
        network,
        augmentations=augmentations if augmentations else None,
        excluded_nodes=None,
        excluded_links=None,
    )

    # Create algorithms instance
    backend = netgraph_core.Backend.cpu()
    algorithms = netgraph_core.Algorithms(backend)

    # Pre-compute pseudo node IDs from names
    pair_to_pseudo_ids: Dict[Tuple[str, str], Tuple[int, int]] = {}
    for pair_key, (pseudo_src_name, pseudo_snk_name) in pair_to_pseudo_names.items():
        pseudo_src_id = node_mapper.to_id(pseudo_src_name)
        pseudo_snk_id = node_mapper.to_id(pseudo_snk_name)
        pair_to_pseudo_ids[pair_key] = (pseudo_src_id, pseudo_snk_id)

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
        if ext_id == -1:  # Skip augmentation edges
            continue
        edge_ref = edge_mapper.decode_ext_id(ext_id)
        if edge_ref:
            link_id_to_edge_indices.setdefault(edge_ref.link_id, []).append(edge_idx)

    return MaxFlowGraphCache(
        graph_handle=graph_handle,
        multidigraph=multidigraph,
        edge_mapper=edge_mapper,
        node_mapper=node_mapper,
        algorithms=algorithms,
        pair_to_pseudo_ids=pair_to_pseudo_ids,
        disabled_node_ids=disabled_node_ids,
        disabled_link_ids=disabled_link_ids,
        link_id_to_edge_indices=link_id_to_edge_indices,
    )


def _build_node_mask(
    cache: MaxFlowGraphCache,
    excluded_nodes: Optional[Set[str]] = None,
) -> np.ndarray:
    """Build node mask using O(|excluded|) complexity."""
    num_nodes = len(cache.node_mapper.node_names)
    mask = np.ones(num_nodes, dtype=bool)

    # Exclude disabled nodes
    for node_id in cache.disabled_node_ids:
        mask[node_id] = False

    # Exclude requested nodes
    if excluded_nodes:
        for node_name in excluded_nodes:
            if node_name in cache.node_mapper.node_id_of:
                mask[cache.node_mapper.node_id_of[node_name]] = False

    return mask


def _build_edge_mask(
    cache: MaxFlowGraphCache,
    excluded_links: Optional[Set[str]] = None,
) -> np.ndarray:
    """Build edge mask using O(|excluded|) complexity."""
    num_edges = cache.multidigraph.num_edges()
    mask = np.ones(num_edges, dtype=bool)

    # Exclude disabled links
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


def max_flow(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
    _cache: Optional[MaxFlowGraphCache] = None,
) -> Dict[Tuple[str, str], float]:
    """Compute max flow between node groups in a network.

    This function calculates the maximum flow from a set of source nodes
    to a set of sink nodes within the provided network.

    When `_cache` is provided, uses O(|excluded|) mask building instead of
    O(V+E) graph reconstruction for efficient repeated analysis.

    Args:
        network: Network instance containing topology and node/link data.
        source_path: Selection expression for source node groups.
        sink_path: Selection expression for sink node groups.
        mode: "combine" (all sources to all sinks) or "pairwise" (each pair separately).
        shortest_path: If True, restricts flow to shortest paths only.
        flow_placement: Strategy for distributing flow among equal-cost edges.
        excluded_nodes: Optional set of node names to exclude.
        excluded_links: Optional set of link IDs to exclude.
        _cache: Pre-built cache for efficient repeated analysis.

    Returns:
        Dict mapping (source_label, sink_label) to total flow value.

    Raises:
        ValueError: If no matching sources or sinks are found.
    """
    core_flow_placement = _map_flow_placement(flow_placement)

    # Fast path: use cached graph with masks
    if _cache is not None:
        node_mask = None
        edge_mask = None
        if excluded_nodes or excluded_links:
            node_mask = _build_node_mask(_cache, excluded_nodes)
            edge_mask = _build_edge_mask(_cache, excluded_links)

        results: Dict[Tuple[str, str], float] = {}
        for pair_key, (
            pseudo_src_id,
            pseudo_snk_id,
        ) in _cache.pair_to_pseudo_ids.items():
            flow_value, _ = _cache.algorithms.max_flow(
                _cache.graph_handle,
                pseudo_src_id,
                pseudo_snk_id,
                flow_placement=core_flow_placement,
                shortest_path=shortest_path,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )
            results[pair_key] = flow_value

        # Handle pairs that weren't cached (overlapping src/snk)
        src_groups = network.select_node_groups_by_path(source_path)
        snk_groups = network.select_node_groups_by_path(sink_path)

        if mode == "combine":
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))
            if (combined_src_label, combined_snk_label) not in results:
                results[(combined_src_label, combined_snk_label)] = 0.0
        elif mode == "pairwise":
            for src_label in src_groups:
                for snk_label in snk_groups:
                    if (src_label, snk_label) not in results:
                        results[(src_label, snk_label)] = 0.0

        return results

    # Standard path: build graph from scratch
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    def _filter_active_nodes(nodes: List) -> List[str]:
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    if mode == "combine":
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = []
        for group_nodes in src_groups.values():
            combined_src_names.extend(_filter_active_nodes(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_filter_active_nodes(group_nodes))

        if not combined_src_names or not combined_snk_names:
            return {(combined_src_label, combined_snk_label): 0.0}
        if set(combined_src_names) & set(combined_snk_names):
            return {(combined_src_label, combined_snk_label): 0.0}

        augmentations = []
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

        graph_handle, _, _, node_mapper = build_graph(
            network,
            augmentations=augmentations,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

        pseudo_src_id = node_mapper.to_id(pseudo_src)
        pseudo_snk_id = node_mapper.to_id(pseudo_snk)

        flow_value, _ = algs.max_flow(
            graph_handle,
            pseudo_src_id,
            pseudo_snk_id,
            flow_placement=core_flow_placement,
            shortest_path=shortest_path,
        )
        return {(combined_src_label, combined_snk_label): flow_value}

    if mode == "pairwise":
        results: Dict[Tuple[str, str], float] = {}
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _filter_active_nodes(src_nodes)
                active_snk_names = _filter_active_nodes(snk_nodes)

                if not active_src_names or not active_snk_names:
                    results[(src_label, snk_label)] = 0.0
                    continue
                if set(active_src_names) & set(active_snk_names):
                    results[(src_label, snk_label)] = 0.0
                    continue

                augmentations = []
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

                graph_handle, _, _, node_mapper = build_graph(
                    network,
                    augmentations=augmentations,
                    excluded_nodes=excluded_nodes,
                    excluded_links=excluded_links,
                )

                pseudo_src_id = node_mapper.to_id(pseudo_src)
                pseudo_snk_id = node_mapper.to_id(pseudo_snk)

                flow_value, _ = algs.max_flow(
                    graph_handle,
                    pseudo_src_id,
                    pseudo_snk_id,
                    flow_placement=core_flow_placement,
                    shortest_path=shortest_path,
                )
                results[(src_label, snk_label)] = flow_value
        return results

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


def max_flow_with_details(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
    _cache: Optional[MaxFlowGraphCache] = None,
) -> Dict[Tuple[str, str], FlowSummary]:
    """Compute max flow with detailed results including cost distribution.

    When `_cache` is provided, uses O(|excluded|) mask building instead of
    O(V+E) graph reconstruction for efficient repeated analysis.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "combine" or "pairwise".
        shortest_path: If True, restricts flow to shortest paths.
        flow_placement: Flow placement strategy.
        excluded_nodes: Optional set of node names to exclude.
        excluded_links: Optional set of link IDs to exclude.
        _cache: Pre-built cache for efficient repeated analysis.

    Returns:
        Dict mapping (source_label, sink_label) to FlowSummary.
    """
    core_flow_placement = _map_flow_placement(flow_placement)

    def _construct_flow_summary(flow_value: float, core_summary=None) -> FlowSummary:
        cost_dist = {}
        if core_summary is not None and len(core_summary.costs) > 0:
            cost_dist = {
                float(c): float(f)
                for c, f in zip(core_summary.costs, core_summary.flows, strict=False)
            }
        return FlowSummary(
            total_flow=flow_value,
            cost_distribution=cost_dist,
            min_cut=(),
        )

    # Fast path: use cached graph with masks
    if _cache is not None:
        node_mask = None
        edge_mask = None
        if excluded_nodes or excluded_links:
            node_mask = _build_node_mask(_cache, excluded_nodes)
            edge_mask = _build_edge_mask(_cache, excluded_links)

        results: Dict[Tuple[str, str], FlowSummary] = {}
        for pair_key, (
            pseudo_src_id,
            pseudo_snk_id,
        ) in _cache.pair_to_pseudo_ids.items():
            flow_value, core_summary = _cache.algorithms.max_flow(
                _cache.graph_handle,
                pseudo_src_id,
                pseudo_snk_id,
                flow_placement=core_flow_placement,
                shortest_path=shortest_path,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )
            results[pair_key] = _construct_flow_summary(flow_value, core_summary)

        # Handle pairs that weren't cached
        src_groups = network.select_node_groups_by_path(source_path)
        snk_groups = network.select_node_groups_by_path(sink_path)

        if mode == "combine":
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))
            if (combined_src_label, combined_snk_label) not in results:
                results[(combined_src_label, combined_snk_label)] = (
                    _construct_flow_summary(0.0)
                )
        elif mode == "pairwise":
            for src_label in src_groups:
                for snk_label in snk_groups:
                    if (src_label, snk_label) not in results:
                        results[(src_label, snk_label)] = _construct_flow_summary(0.0)

        return results

    # Slow path: build graph from scratch
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    def _filter_active_nodes(nodes: List) -> List[str]:
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    if mode == "combine":
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = []
        for group_nodes in src_groups.values():
            combined_src_names.extend(_filter_active_nodes(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_filter_active_nodes(group_nodes))

        if not combined_src_names or not combined_snk_names:
            return {
                (combined_src_label, combined_snk_label): _construct_flow_summary(0.0)
            }
        if set(combined_src_names) & set(combined_snk_names):
            return {
                (combined_src_label, combined_snk_label): _construct_flow_summary(0.0)
            }

        augmentations = []
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

        graph_handle, _, _, node_mapper = build_graph(
            network,
            augmentations=augmentations,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

        pseudo_src_id = node_mapper.to_id(pseudo_src)
        pseudo_snk_id = node_mapper.to_id(pseudo_snk)

        flow_value, core_summary = algs.max_flow(
            graph_handle,
            pseudo_src_id,
            pseudo_snk_id,
            flow_placement=core_flow_placement,
            shortest_path=shortest_path,
        )

        return {
            (combined_src_label, combined_snk_label): _construct_flow_summary(
                flow_value, core_summary
            )
        }

    if mode == "pairwise":
        results: Dict[Tuple[str, str], FlowSummary] = {}
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _filter_active_nodes(src_nodes)
                active_snk_names = _filter_active_nodes(snk_nodes)

                if not active_src_names or not active_snk_names:
                    results[(src_label, snk_label)] = _construct_flow_summary(0.0)
                    continue
                if set(active_src_names) & set(active_snk_names):
                    results[(src_label, snk_label)] = _construct_flow_summary(0.0)
                    continue

                augmentations = []
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

                graph_handle, _, _, node_mapper = build_graph(
                    network,
                    augmentations=augmentations,
                    excluded_nodes=excluded_nodes,
                    excluded_links=excluded_links,
                )

                pseudo_src_id = node_mapper.to_id(pseudo_src)
                pseudo_snk_id = node_mapper.to_id(pseudo_snk)

                flow_value, core_summary = algs.max_flow(
                    graph_handle,
                    pseudo_src_id,
                    pseudo_snk_id,
                    flow_placement=core_flow_placement,
                    shortest_path=shortest_path,
                )

                results[(src_label, snk_label)] = _construct_flow_summary(
                    flow_value, core_summary
                )
        return results

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


def sensitivity_analysis(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
    _cache: Optional[MaxFlowGraphCache] = None,
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Analyze sensitivity of max flow to edge failures.

    Identifies critical edges and computes the flow reduction caused by
    removing each one.

    When `_cache` is provided, uses O(|excluded|) mask building instead of
    O(V+E) graph reconstruction for efficient repeated analysis.

    The `shortest_path` parameter controls routing semantics:
    - shortest_path=False (default): Full max-flow; reports all saturated edges.
    - shortest_path=True: Shortest-path-only (IP/IGP); reports only edges
      used under ECMP routing.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "combine" or "pairwise".
        shortest_path: If True, use single-tier shortest-path flow (IP/IGP).
                      If False, use full iterative max-flow (SDN/TE).
        flow_placement: Flow placement strategy.
        excluded_nodes: Optional set of node names to exclude.
        excluded_links: Optional set of link IDs to exclude.
        _cache: Pre-built cache for efficient repeated analysis.

    Returns:
        Dict mapping (source_label, sink_label) to {link_id: flow_reduction}.
    """
    core_flow_placement = _map_flow_placement(flow_placement)

    # Fast path: use cached graph with masks
    if _cache is not None:
        node_mask = None
        edge_mask = None
        if excluded_nodes or excluded_links:
            node_mask = _build_node_mask(_cache, excluded_nodes)
            edge_mask = _build_edge_mask(_cache, excluded_links)

        results: Dict[Tuple[str, str], Dict[str, float]] = {}
        ext_edge_ids = _cache.multidigraph.ext_edge_ids_view()

        for pair_key, (
            pseudo_src_id,
            pseudo_snk_id,
        ) in _cache.pair_to_pseudo_ids.items():
            sens_results = _cache.algorithms.sensitivity_analysis(
                _cache.graph_handle,
                pseudo_src_id,
                pseudo_snk_id,
                flow_placement=core_flow_placement,
                shortest_path=shortest_path,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )

            sensitivity_map: Dict[str, float] = {}
            for edge_id, delta in sens_results:
                ext_id = ext_edge_ids[edge_id]
                link_id = _cache.edge_mapper.to_name(ext_id)
                if link_id is not None:
                    sensitivity_map[link_id] = delta

            results[pair_key] = sensitivity_map

        # Handle pairs that weren't cached
        src_groups = network.select_node_groups_by_path(source_path)
        snk_groups = network.select_node_groups_by_path(sink_path)

        if mode == "combine":
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))
            if (combined_src_label, combined_snk_label) not in results:
                results[(combined_src_label, combined_snk_label)] = {}
        elif mode == "pairwise":
            for src_label in src_groups:
                for snk_label in snk_groups:
                    if (src_label, snk_label) not in results:
                        results[(src_label, snk_label)] = {}

        return results

    # Slow path: build graph from scratch
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    def _filter_active_nodes(nodes: List) -> List[str]:
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    if mode == "combine":
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = []
        for group_nodes in src_groups.values():
            combined_src_names.extend(_filter_active_nodes(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_filter_active_nodes(group_nodes))

        if not combined_src_names or not combined_snk_names:
            return {(combined_src_label, combined_snk_label): {}}
        if set(combined_src_names) & set(combined_snk_names):
            return {(combined_src_label, combined_snk_label): {}}

        augmentations = []
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

        graph_handle, multidigraph, link_mapper, node_mapper = build_graph(
            network,
            augmentations=augmentations,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

        pseudo_src_id = node_mapper.to_id(pseudo_src)
        pseudo_snk_id = node_mapper.to_id(pseudo_snk)

        sens_results = algs.sensitivity_analysis(
            graph_handle,
            pseudo_src_id,
            pseudo_snk_id,
            flow_placement=core_flow_placement,
            shortest_path=shortest_path,
        )

        sensitivity_map: Dict[str, float] = {}
        ext_edge_ids = multidigraph.ext_edge_ids_view()
        for edge_id, delta in sens_results:
            ext_id = ext_edge_ids[edge_id]
            link_id = link_mapper.to_name(ext_id)
            if link_id is not None:
                sensitivity_map[link_id] = delta

        return {(combined_src_label, combined_snk_label): sensitivity_map}

    if mode == "pairwise":
        out: Dict[Tuple[str, str], Dict[str, float]] = {}
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _filter_active_nodes(src_nodes)
                active_snk_names = _filter_active_nodes(snk_nodes)

                if not active_src_names or not active_snk_names:
                    out[(src_label, snk_label)] = {}
                    continue
                if set(active_src_names) & set(active_snk_names):
                    out[(src_label, snk_label)] = {}
                    continue

                augmentations = []
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

                graph_handle, multidigraph, link_mapper, node_mapper = build_graph(
                    network,
                    augmentations=augmentations,
                    excluded_nodes=excluded_nodes,
                    excluded_links=excluded_links,
                )

                pseudo_src_id = node_mapper.to_id(pseudo_src)
                pseudo_snk_id = node_mapper.to_id(pseudo_snk)

                sens_results = algs.sensitivity_analysis(
                    graph_handle,
                    pseudo_src_id,
                    pseudo_snk_id,
                    flow_placement=core_flow_placement,
                    shortest_path=shortest_path,
                )

                sensitivity_map: Dict[str, float] = {}
                ext_edge_ids = multidigraph.ext_edge_ids_view()
                for edge_id, delta in sens_results:
                    ext_id = ext_edge_ids[edge_id]
                    link_id = link_mapper.to_name(ext_id)
                    if link_id is not None:
                        sensitivity_map[link_id] = delta

                out[(src_label, snk_label)] = sensitivity_map
        return out

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


def _map_flow_placement(flow_placement: FlowPlacement) -> netgraph_core.FlowPlacement:
    """Map NetGraph FlowPlacement to Core FlowPlacement."""
    if flow_placement == FlowPlacement.PROPORTIONAL:
        return netgraph_core.FlowPlacement.PROPORTIONAL
    if flow_placement == FlowPlacement.EQUAL_BALANCED:
        return netgraph_core.FlowPlacement.EQUAL_BALANCED
    raise ValueError(f"Unsupported FlowPlacement: {flow_placement}")
