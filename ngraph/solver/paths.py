"""Shortest-path solver wrappers bound to the model layer.

Expose convenience functions for computing shortest paths between node groups
selected from a ``Network`` context. Selection semantics mirror the max-flow
wrappers with ``mode`` in {"combine", "pairwise"}.

Functions return minimal costs or concrete ``Path`` objects built from SPF
predecessor maps. Parallel equal-cost edges can be expanded into distinct
paths.

All functions fail fast on invalid selection inputs and do not mutate the
input context.

Note:
    For path queries, overlapping source/sink membership is treated as
    unreachable.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

import netgraph_core

from ngraph.adapters.core import build_edge_mask, build_graph, build_node_mask
from ngraph.model.network import Network
from ngraph.model.path import Path
from ngraph.types.base import EdgeSelect
from ngraph.types.dto import EdgeRef


def shortest_path_costs(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "combine",
    edge_select: EdgeSelect = EdgeSelect.ALL_MIN_COST,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
) -> Dict[Tuple[str, str], float]:
    """Return minimal path cost(s) between selected node groups.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "combine" or "pairwise".
        edge_select: SPF edge selection strategy.
        excluded_nodes: Optional set of node names to exclude temporarily.
        excluded_links: Optional set of link IDs to exclude temporarily.

    Returns:
        Mapping from (source_label, sink_label) to minimal cost; ``inf`` if no
        path.

    Raises:
        ValueError: If no source nodes match ``source_path``.
        ValueError: If no sink nodes match ``sink_path``.
        ValueError: If ``mode`` is not "combine" or "pairwise".
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    # Build Core graph and masks
    graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(network)
    node_mask = build_node_mask(network, node_mapper, excluded_nodes)
    edge_mask = build_edge_mask(network, multidigraph, edge_mapper, excluded_links)

    # Create Core backend and algorithms
    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    # Map edge_select to Core's EdgeSelection
    core_edge_select = _map_edge_select(edge_select)

    def _active_node_names(nodes: Iterable) -> List[str]:
        """Filter to active (non-disabled) node names."""
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
            combined_src_names.extend(_active_node_names(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_active_node_names(group_nodes))

        if not combined_src_names or not combined_snk_names:
            return {(combined_src_label, combined_snk_label): float("inf")}
        if set(combined_src_names) & set(combined_snk_names):
            return {(combined_src_label, combined_snk_label): float("inf")}

        # Run SPF from each source, find min cost to any sink
        best_cost = float("inf")
        for src_name in combined_src_names:
            src_id = node_mapper.to_id(src_name)
            dists, pred_dag = algs.spf(
                graph_handle,
                src=src_id,
                selection=core_edge_select,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )
            for snk_name in combined_snk_names:
                snk_id = node_mapper.to_id(snk_name)
                cost = dists[snk_id]
                if cost < best_cost:
                    best_cost = cost
        return {(combined_src_label, combined_snk_label): best_cost}

    if mode == "pairwise":
        results: Dict[Tuple[str, str], float] = {}
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _active_node_names(src_nodes)
                active_snk_names = _active_node_names(snk_nodes)
                if not active_src_names or not active_snk_names:
                    results[(src_label, snk_label)] = float("inf")
                    continue
                if set(active_src_names) & set(active_snk_names):
                    results[(src_label, snk_label)] = float("inf")
                    continue

                best_cost = float("inf")
                for src_name in active_src_names:
                    src_id = node_mapper.to_id(src_name)
                    dists, pred_dag = algs.spf(
                        graph_handle,
                        src=src_id,
                        selection=core_edge_select,
                        node_mask=node_mask,
                        edge_mask=edge_mask,
                    )
                    for snk_name in active_snk_names:
                        snk_id = node_mapper.to_id(snk_name)
                        cost = dists[snk_id]
                        if cost < best_cost:
                            best_cost = cost
                results[(src_label, snk_label)] = best_cost
        return results

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


def shortest_paths(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "combine",
    edge_select: EdgeSelect = EdgeSelect.ALL_MIN_COST,
    split_parallel_edges: bool = False,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
) -> Dict[Tuple[str, str], List[Path]]:
    """Return concrete shortest path(s) between selected node groups.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "combine" or "pairwise".
        edge_select: SPF edge selection strategy.
        split_parallel_edges: Expand parallel edges into distinct paths when True.
        excluded_nodes: Optional set of node names to exclude temporarily.
        excluded_links: Optional set of link IDs to exclude temporarily.

    Returns:
        Mapping from (source_label, sink_label) to list of Path. Empty if
        unreachable.

    Raises:
        ValueError: If no source nodes match ``source_path``.
        ValueError: If no sink nodes match ``sink_path``.
        ValueError: If ``mode`` is not "combine" or "pairwise".
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    # Build Core graph and masks
    graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(network)
    node_mask = build_node_mask(network, node_mapper, excluded_nodes)
    edge_mask = build_edge_mask(network, multidigraph, edge_mapper, excluded_links)

    # Create Core backend and algorithms
    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    # Map edge_select to Core's EdgeSelection
    core_edge_select = _map_edge_select(edge_select)

    def _active_node_names(nodes: Iterable) -> List[str]:
        """Filter to active (non-disabled) node names."""
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    def _best_paths_for_groups(
        src_names: List[str], snk_names: List[str]
    ) -> List[Path]:
        """Find best-cost paths from any source to any sink."""
        if not src_names or not snk_names:
            return []
        if set(src_names) & set(snk_names):
            return []

        best_cost = float("inf")
        best_paths: List[Path] = []

        for src_name in src_names:
            src_id = node_mapper.to_id(src_name)
            dists, pred_dag = algs.spf(
                graph_handle,
                src=src_id,
                selection=core_edge_select,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )
            for snk_name in snk_names:
                snk_id = node_mapper.to_id(snk_name)
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
                        node_mapper,
                        edge_mapper,
                        multidigraph,
                        split_parallel_edges,
                    )
                elif cost == best_cost:
                    best_paths.extend(
                        _extract_paths_from_pred_dag(
                            pred_dag,
                            src_name,
                            snk_name,
                            cost,
                            node_mapper,
                            edge_mapper,
                            multidigraph,
                            split_parallel_edges,
                        )
                    )

        if best_paths:
            best_paths = sorted(set(best_paths))
        return best_paths

    if mode == "combine":
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = []
        for group_nodes in src_groups.values():
            combined_src_names.extend(_active_node_names(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_active_node_names(group_nodes))

        paths_list = _best_paths_for_groups(combined_src_names, combined_snk_names)
        return {(combined_src_label, combined_snk_label): paths_list}

    if mode == "pairwise":
        results: Dict[Tuple[str, str], List[Path]] = {}
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _active_node_names(src_nodes)
                active_snk_names = _active_node_names(snk_nodes)
                results[(src_label, snk_label)] = _best_paths_for_groups(
                    active_src_names, active_snk_names
                )
        return results

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


def k_shortest_paths(
    network: Network,
    source_path: str,
    sink_path: str,
    *,
    mode: str = "pairwise",
    max_k: int = 3,
    edge_select: EdgeSelect = EdgeSelect.ALL_MIN_COST,
    max_path_cost: float = float("inf"),
    max_path_cost_factor: Optional[float] = None,
    split_parallel_edges: bool = False,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
) -> Dict[Tuple[str, str], List[Path]]:
    """Return up to K shortest paths per group pair.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "pairwise" (default) or "combine".
        max_k: Max paths per pair.
        edge_select: SPF/KSP edge selection strategy.
        max_path_cost: Absolute cost threshold.
        max_path_cost_factor: Relative threshold versus best path.
        split_parallel_edges: Expand parallel edges into distinct paths when True.
        excluded_nodes: Optional set of node names to exclude temporarily.
        excluded_links: Optional set of link IDs to exclude temporarily.

    Returns:
        Mapping from (source_label, sink_label) to list of Path (<= max_k).

    Raises:
        ValueError: If no source nodes match ``source_path``.
        ValueError: If no sink nodes match ``sink_path``.
        ValueError: If ``mode`` is not "combine" or "pairwise".
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    # Build Core graph and masks
    graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(network)
    node_mask = build_node_mask(network, node_mapper, excluded_nodes)
    edge_mask = build_edge_mask(network, multidigraph, edge_mapper, excluded_links)

    # Create Core backend and algorithms
    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    # Map edge_select to Core's EdgeSelection
    core_edge_select = _map_edge_select(edge_select)

    def _active_node_names(nodes: Iterable) -> List[str]:
        """Filter to active (non-disabled) node names."""
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    def _ksp_for_groups(src_names: List[str], snk_names: List[str]) -> List[Path]:
        """Find K shortest paths from any source to any sink."""
        if not src_names or not snk_names:
            return []
        if set(src_names) & set(snk_names):
            return []

        # Find best pair to seed thresholds
        best_pair: Optional[Tuple[str, str]] = None
        best_cost = float("inf")
        for src_name in src_names:
            src_id = node_mapper.to_id(src_name)
            dists, pred_dag = algs.spf(
                graph_handle,
                src=src_id,
                selection=core_edge_select,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )
            for snk_name in snk_names:
                snk_id = node_mapper.to_id(snk_name)
                cost = dists[snk_id]
                if cost < best_cost:
                    best_cost = cost
                    best_pair = (src_name, snk_name)

        if best_pair is None:
            return []

        # Run KSP on the best pair
        src_name, snk_name = best_pair
        src_id = node_mapper.to_id(src_name)
        snk_id = node_mapper.to_id(snk_name)

        results: List[Path] = []
        count = 0

        for dists, pred_dag in algs.ksp(
            graph_handle,
            src=src_id,
            dst=snk_id,
            k=max_k,
            max_cost_factor=max_path_cost_factor
            if max_path_cost_factor is not None
            else None,
            node_mask=node_mask,
            edge_mask=edge_mask,
        ):
            cost = dists[snk_id]
            if cost == float("inf"):
                continue
            for path in _extract_paths_from_pred_dag(
                pred_dag,
                src_name,
                snk_name,
                cost,
                node_mapper,
                edge_mapper,
                multidigraph,
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

    if mode == "combine":
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        combined_src_names = []
        for group_nodes in src_groups.values():
            combined_src_names.extend(_active_node_names(group_nodes))
        combined_snk_names = []
        for group_nodes in snk_groups.values():
            combined_snk_names.extend(_active_node_names(group_nodes))

        return {
            (combined_src_label, combined_snk_label): _ksp_for_groups(
                combined_src_names, combined_snk_names
            )
        }

    if mode == "pairwise":
        results: Dict[Tuple[str, str], List[Path]] = {}
        for src_label, src_nodes in src_groups.items():
            for snk_label, snk_nodes in snk_groups.items():
                active_src_names = _active_node_names(src_nodes)
                active_snk_names = _active_node_names(snk_nodes)
                results[(src_label, snk_label)] = _ksp_for_groups(
                    active_src_names, active_snk_names
                )
        return results

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


# Helper functions


def _map_edge_select(edge_select: EdgeSelect) -> netgraph_core.EdgeSelection:
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


def _extract_paths_from_pred_dag(
    pred_dag: netgraph_core.PredDAG,
    src_name: str,
    snk_name: str,
    cost: float,
    node_mapper,
    edge_mapper,
    multidigraph,
    split_parallel_edges: bool,
) -> List[Path]:
    """Extract Path objects from a PredDAG.

    Args:
        pred_dag: Core PredDAG instance.
        src_name: Source node name.
        snk_name: Sink node name.
        cost: Path cost.
        node_mapper: NodeMapper for ID <-> name translation.
        edge_mapper: EdgeMapper for ext_edge_id <-> EdgeRef translation.
        multidigraph: Core StrictMultiDiGraph instance.
        split_parallel_edges: If True, expand parallel edges into distinct paths.

    Returns:
        List of Path objects.
    """
    src_id = node_mapper.to_id(src_name)
    snk_id = node_mapper.to_id(snk_name)

    # Get fully resolved paths from PredDAG
    # Returns list of paths, where each path is a list of (node_id, edge_ids_tuple)
    raw_paths = pred_dag.resolve_to_paths(
        src_id, snk_id, split_parallel_edges=split_parallel_edges
    )

    paths = []
    ext_edge_ids = multidigraph.ext_edge_ids_view()

    for raw_path in raw_paths:
        path_elements: List[Tuple[str, Tuple[EdgeRef, ...]]] = []

        for node_id, edge_ids in raw_path:
            node_name = node_mapper.to_name(node_id)

            # Resolve EdgeRefs
            edge_refs = []
            for edge_id in edge_ids:
                ext_id = ext_edge_ids[edge_id]
                edge_ref = edge_mapper.decode_ext_id(int(ext_id))
                if edge_ref is not None:
                    edge_refs.append(edge_ref)

            path_elements.append((node_name, tuple(edge_refs)))

        paths.append(Path(tuple(path_elements), cost))

    return paths
