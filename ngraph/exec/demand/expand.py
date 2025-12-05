"""Demand expansion: converts TrafficDemand specs into concrete placement demands.

Supports both pairwise and combine modes through augmentation-based pseudo nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ngraph.analysis.context import LARGE_CAPACITY, AugmentationEdge
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.model.network import Network
from ngraph.utils.nodes import (
    collect_active_node_names_from_groups,
    collect_active_nodes_from_groups,
)


@dataclass
class ExpandedDemand:
    """Concrete demand ready for placement.

    Uses node names (not IDs) so expansion happens before graph building.
    Node IDs are resolved after the graph is built with pseudo nodes.

    Attributes:
        src_name: Source node name (real or pseudo).
        dst_name: Destination node name (real or pseudo).
        volume: Traffic volume to place.
        priority: Priority class (lower is higher priority).
        policy_preset: FlowPolicy configuration preset.
        demand_id: Parent TrafficDemand ID (for tracking).
    """

    src_name: str
    dst_name: str
    volume: float
    priority: int
    policy_preset: FlowPolicyPreset
    demand_id: str


@dataclass
class DemandExpansion:
    """Demand expansion result.

    Attributes:
        demands: Concrete demands ready for placement (sorted by priority).
        augmentations: Augmentation edges for pseudo nodes (empty for pairwise).
    """

    demands: List[ExpandedDemand]
    augmentations: List[AugmentationEdge]


def _expand_combine(
    td: TrafficDemand,
    src_groups,
    dst_groups,
    policy_preset: FlowPolicyPreset,
) -> tuple[list[ExpandedDemand], list[AugmentationEdge]]:
    """Expand combine mode: aggregate sources/sinks through pseudo nodes."""
    pseudo_src = f"_src_{td.id}"
    pseudo_snk = f"_snk_{td.id}"

    src_names = collect_active_node_names_from_groups(src_groups)
    dst_names = collect_active_node_names_from_groups(dst_groups)

    if not src_names or not dst_names:
        return [], []

    augmentations = []

    # Pseudo-source → real sources (unidirectional OUT)
    for src_name in src_names:
        augmentations.append(AugmentationEdge(pseudo_src, src_name, LARGE_CAPACITY, 0))

    # Real sinks → pseudo-sink (unidirectional IN)
    for dst_name in dst_names:
        augmentations.append(AugmentationEdge(dst_name, pseudo_snk, LARGE_CAPACITY, 0))

    # Single aggregated demand
    demand = ExpandedDemand(
        src_name=pseudo_src,
        dst_name=pseudo_snk,
        volume=td.demand,
        priority=td.priority,
        policy_preset=policy_preset,
        demand_id=td.id,
    )

    return [demand], augmentations


def _expand_pairwise(
    td: TrafficDemand,
    src_groups,
    dst_groups,
    policy_preset: FlowPolicyPreset,
) -> tuple[list[ExpandedDemand], list[AugmentationEdge]]:
    """Expand pairwise mode: create demand for each (src, dst) pair."""
    src_nodes = collect_active_nodes_from_groups(src_groups)
    dst_nodes = collect_active_nodes_from_groups(dst_groups)

    # Filter self-pairs
    pairs = [
        (src, dst) for src in src_nodes for dst in dst_nodes if src.name != dst.name
    ]

    if not pairs:
        return [], []

    # Distribute volume evenly
    volume_per_pair = td.demand / len(pairs)

    demands = [
        ExpandedDemand(
            src_name=src.name,
            dst_name=dst.name,
            volume=volume_per_pair,
            priority=td.priority,
            policy_preset=policy_preset,
            demand_id=td.id,
        )
        for src, dst in pairs
    ]

    return demands, []  # No augmentations for pairwise


def expand_demands(
    network: Network,
    traffic_demands: List[TrafficDemand],
    default_policy_preset: FlowPolicyPreset = FlowPolicyPreset.SHORTEST_PATHS_ECMP,
) -> DemandExpansion:
    """Expand TrafficDemand specifications into concrete demands with augmentations.

    Pure function that:
    1. Selects node groups using Network's selection API
    2. Distributes volume based on mode (combine/pairwise)
    3. Generates augmentation edges for combine mode (pseudo nodes)
    4. Returns demands (node names) + augmentations

    Node names are used (not IDs) so expansion happens BEFORE graph building.
    IDs are resolved after graph is built with augmentations.

    Args:
        network: Network for node selection.
        traffic_demands: High-level demand specifications.
        default_policy_preset: Default policy if demand doesn't specify one.

    Returns:
        DemandExpansion with demands and augmentations.

    Raises:
        ValueError: If no demands could be expanded or unsupported mode.
    """
    all_demands: List[ExpandedDemand] = []
    all_augmentations: List[AugmentationEdge] = []

    for td in traffic_demands:
        # Select node groups
        src_groups = network.select_node_groups_by_path(td.source_path)
        dst_groups = network.select_node_groups_by_path(td.sink_path)

        if not src_groups or not dst_groups:
            continue

        policy_preset = td.flow_policy_config or default_policy_preset

        # Expand based on mode
        if td.mode == "combine":
            demands, augmentations = _expand_combine(
                td, src_groups, dst_groups, policy_preset
            )
        elif td.mode == "pairwise":
            demands, augmentations = _expand_pairwise(
                td, src_groups, dst_groups, policy_preset
            )
        else:
            raise ValueError(f"Unknown demand mode: {td.mode}")

        all_demands.extend(demands)
        all_augmentations.extend(augmentations)

    if not all_demands:
        raise ValueError(
            "No demands could be expanded. Possible causes:\n"
            "  - Source/sink paths don't match any nodes\n"
            "  - All matching nodes are disabled\n"
            "  - Source and sink are identical (self-loops not allowed)"
        )

    # Sort by priority (lower = higher priority)
    sorted_demands = sorted(all_demands, key=lambda d: d.priority)

    return DemandExpansion(demands=sorted_demands, augmentations=all_augmentations)
