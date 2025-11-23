"""Max-flow computation between node groups with NetGraph-Core integration.

This module provides max-flow analysis for Network models by transforming
multi-source/multi-sink problems into single-source/single-sink problems
using pseudo nodes. The implementation uses the unified build_graph() with
augmentations to add pseudo-source and pseudo-sink nodes.

The input Network is never mutated; all graph construction and computation
happens in temporary Core data structures.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import netgraph_core

from ngraph.adapters.core import AugmentationEdge, build_graph
from ngraph.model.network import Network
from ngraph.types.base import FlowPlacement
from ngraph.types.dto import FlowSummary

# Large capacity for pseudo edges (avoid float('inf') due to Core limitation)
LARGE_CAPACITY = 1e15


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
) -> Dict[Tuple[str, str], float]:
    """Compute max flow between node groups in a network.

    This function calculates the maximum flow from a set of source nodes
    to a set of sink nodes within the provided network. It supports
    "combine" mode (all sources to all sinks) and "pairwise" mode (each
    source_group to each sink_group).

    The implementation constructs an augmented graph with pseudo-source and
    pseudo-sink nodes, then delegates the computation to NetGraph-Core's
    max-flow algorithm.

    Args:
        network: Network instance containing topology and node/link data.
        source_path: Selection expression (regex or attribute) for source node groups.
        sink_path: Selection expression (regex or attribute) for sink node groups.
        mode: Aggregation strategy:
            - "combine": Treats all selected sources as a single super-source
                         and all selected sinks as a single super-sink.
            - "pairwise": Computes max flow for each (source_group, sink_group) pair separately.
        shortest_path: If True, restricts flow to shortest paths only.
        flow_placement: Strategy for distributing flow among equal-cost parallel edges.
        excluded_nodes: Optional set of node names to exclude from the graph.
        excluded_links: Optional set of link IDs to exclude from the graph.

    Returns:
        Dict[Tuple[str, str], float]: Total flow per (source_label, sink_label) pair.

    Raises:
        ValueError: If no matching sources or sinks are found, or if `mode`
                    is not one of {"combine", "pairwise"}.
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    # Map flow_placement to Core's FlowPlacement enum
    core_flow_placement = _map_flow_placement(flow_placement)

    # Create Core algorithms instance (used for all computations)
    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    def _filter_active_nodes(nodes: List) -> List[str]:
        """Filter nodes to active (not disabled or excluded) and return their names."""
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    if mode == "combine":
        combined_src_label = "|".join(sorted(src_groups.keys()))
        combined_snk_label = "|".join(sorted(snk_groups.keys()))

        # Collect all active source and sink node names
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

        # Prepare augmentation edges for pseudo nodes
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

        # Build augmented graph with pseudo nodes
        graph_handle, _, _, node_mapper = build_graph(
            network,
            augmentations=augmentations,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

        # Get pseudo node IDs
        pseudo_src_id = node_mapper.to_id(pseudo_src)
        pseudo_snk_id = node_mapper.to_id(pseudo_snk)

        # Run max-flow from pseudo-source to pseudo-sink
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

                # Prepare augmentation edges for this pair
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

                # Build augmented graph
                graph_handle, _, _, node_mapper = build_graph(
                    network,
                    augmentations=augmentations,
                    excluded_nodes=excluded_nodes,
                    excluded_links=excluded_links,
                )

                # Get pseudo node IDs
                pseudo_src_id = node_mapper.to_id(pseudo_src)
                pseudo_snk_id = node_mapper.to_id(pseudo_snk)

                # Run max-flow
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
) -> Dict[Tuple[str, str], FlowSummary]:
    """Compute max flow with detailed results.

    This function provides the same max-flow computation as `max_flow` but
    returns a `FlowSummary` object for each result, which can include
    additional details like cost distribution and min-cut information.

    Note:
        The `FlowSummary` currently provides a simplified view. Full details
        (e.g., saturated edges, explicit flow paths) would require further
        enhancements in the Core API and its integration.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "combine" or "pairwise".
        shortest_path: If True, perform single augmentation.
        flow_placement: Flow placement strategy.
        excluded_nodes: Optional set of node names to exclude.
        excluded_links: Optional set of link IDs to exclude.

    Returns:
        Dict mapping (source_label, sink_label) to FlowSummary.

    Raises:
        ValueError: If no matching sources or sinks are found, or if `mode`
                    is not one of {"combine", "pairwise"}.
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    # Map flow_placement to Core's FlowPlacement enum
    core_flow_placement = _map_flow_placement(flow_placement)

    # Create Core algorithms instance
    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    def _filter_active_nodes(nodes: List) -> List[str]:
        """Filter nodes to active and return their names."""
        return [
            n.name
            for n in nodes
            if not n.disabled
            and (excluded_nodes is None or n.name not in excluded_nodes)
        ]

    def _construct_flow_summary(flow_value: float, core_summary=None) -> FlowSummary:
        """Construct FlowSummary from flow value and optional Core summary."""
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

        # Prepare augmentations
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

        # Build augmented graph
        graph_handle, _, _, node_mapper = build_graph(
            network,
            augmentations=augmentations,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )

        pseudo_src_id = node_mapper.to_id(pseudo_src)
        pseudo_snk_id = node_mapper.to_id(pseudo_snk)

        # Run max-flow
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

                # Prepare augmentations
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

                # Build augmented graph
                graph_handle, _, _, node_mapper = build_graph(
                    network,
                    augmentations=augmentations,
                    excluded_nodes=excluded_nodes,
                    excluded_links=excluded_links,
                )

                pseudo_src_id = node_mapper.to_id(pseudo_src)
                pseudo_snk_id = node_mapper.to_id(pseudo_snk)

                # Run max-flow
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
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    excluded_nodes: Optional[Set[str]] = None,
    excluded_links: Optional[Set[str]] = None,
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Analyze sensitivity of max flow to edge failures.

    Identifies critical edges (saturated edges) and computes the flow reduction
    caused by removing each one.

    Args:
        network: Network instance.
        source_path: Selection expression for source groups.
        sink_path: Selection expression for sink groups.
        mode: "combine" or "pairwise".
        flow_placement: Flow placement strategy.
        excluded_nodes: Optional set of node names to exclude.
        excluded_links: Optional set of link IDs to exclude.

    Returns:
        Dict mapping (source_label, sink_label) to a dictionary of
        {link_id: flow_reduction}.
    """
    src_groups = network.select_node_groups_by_path(source_path)
    snk_groups = network.select_node_groups_by_path(sink_path)

    if not src_groups:
        raise ValueError(f"No source nodes found matching '{source_path}'.")
    if not snk_groups:
        raise ValueError(f"No sink nodes found matching '{sink_path}'.")

    core_flow_placement = _map_flow_placement(flow_placement)
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

        results = algs.sensitivity_analysis(
            graph_handle,
            pseudo_src_id,
            pseudo_snk_id,
            flow_placement=core_flow_placement,
        )

        sensitivity_map = {}
        ext_edge_ids = multidigraph.ext_edge_ids_view()
        for edge_id, delta in results:
            ext_id = ext_edge_ids[edge_id]
            link_id = link_mapper.to_name(ext_id)
            # Ignore sensitivity of augmentation edges (which don't have mapped names)
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

                results = algs.sensitivity_analysis(
                    graph_handle,
                    pseudo_src_id,
                    pseudo_snk_id,
                    flow_placement=core_flow_placement,
                )

                sensitivity_map = {}
                ext_edge_ids = multidigraph.ext_edge_ids_view()
                for edge_id, delta in results:
                    ext_id = ext_edge_ids[edge_id]
                    link_id = link_mapper.to_name(ext_id)
                    if link_id is not None:
                        sensitivity_map[link_id] = delta

                out[(src_label, snk_label)] = sensitivity_map
        return out

    raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")


# Helper functions


def _map_flow_placement(flow_placement: FlowPlacement) -> netgraph_core.FlowPlacement:
    """Map NetGraph FlowPlacement to Core FlowPlacement."""
    if flow_placement == FlowPlacement.PROPORTIONAL:
        return netgraph_core.FlowPlacement.PROPORTIONAL
    if flow_placement == FlowPlacement.EQUAL_BALANCED:
        return netgraph_core.FlowPlacement.EQUAL_BALANCED
    raise ValueError(f"Unsupported FlowPlacement: {flow_placement}")
