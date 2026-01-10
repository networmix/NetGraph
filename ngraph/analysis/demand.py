"""Demand expansion: converts TrafficDemand specs into concrete placement demands.

Supports both pairwise and combine modes through augmentation-based pseudo nodes.
Uses unified selectors for node selection.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List

from ngraph.analysis.context import LARGE_CAPACITY, AugmentationEdge
from ngraph.dsl.selectors import normalize_selector, select_nodes
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.model.network import Network, Node


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
        demand_id: Parent TrafficDemand ID for tracking.
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


def _flatten_groups(groups: Dict[str, List[Node]]) -> List[Node]:
    """Flatten grouped nodes into a single list."""
    result: List[Node] = []
    for nodes in groups.values():
        result.extend(nodes)
    return result


def _flatten_group_names(groups: Dict[str, List[Node]]) -> List[str]:
    """Flatten grouped nodes into a list of names."""
    return [node.name for node in _flatten_groups(groups)]


def _expand_combine(
    td: TrafficDemand,
    src_groups: Dict[str, List[Node]],
    dst_groups: Dict[str, List[Node]],
    policy_preset: FlowPolicyPreset,
) -> tuple[list[ExpandedDemand], list[AugmentationEdge]]:
    """Expand combine mode: aggregate sources/sinks through pseudo nodes."""
    pseudo_src = f"_src_{td.id}"
    pseudo_snk = f"_snk_{td.id}"

    src_names = _flatten_group_names(src_groups)
    dst_names = _flatten_group_names(dst_groups)

    if not src_names or not dst_names:
        return [], []

    augmentations = []

    # Pseudo-source -> real sources (unidirectional OUT)
    for src_name in src_names:
        augmentations.append(AugmentationEdge(pseudo_src, src_name, LARGE_CAPACITY, 0))

    # Real targets -> pseudo-target (unidirectional IN)
    for dst_name in dst_names:
        augmentations.append(AugmentationEdge(dst_name, pseudo_snk, LARGE_CAPACITY, 0))

    # Single aggregated demand
    expanded = ExpandedDemand(
        src_name=pseudo_src,
        dst_name=pseudo_snk,
        volume=td.volume,
        priority=td.priority,
        policy_preset=policy_preset,
        demand_id=td.id,
    )

    return [expanded], augmentations


def _expand_pairwise(
    td: TrafficDemand,
    src_groups: Dict[str, List[Node]],
    dst_groups: Dict[str, List[Node]],
    policy_preset: FlowPolicyPreset,
) -> tuple[list[ExpandedDemand], list[AugmentationEdge]]:
    """Expand pairwise mode: create demand for each (src, dst) pair."""
    src_nodes = _flatten_groups(src_groups)
    dst_nodes = _flatten_groups(dst_groups)

    # Filter self-pairs
    pairs = [
        (src, dst) for src in src_nodes for dst in dst_nodes if src.name != dst.name
    ]

    if not pairs:
        return [], []

    # Distribute volume evenly
    volume_per_pair = td.volume / len(pairs)

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


def _expand_by_group_mode(
    td: TrafficDemand,
    src_groups: Dict[str, List[Node]],
    dst_groups: Dict[str, List[Node]],
    policy_preset: FlowPolicyPreset,
) -> tuple[list[ExpandedDemand], list[AugmentationEdge]]:
    """Expand demands based on group_mode.

    group_mode semantics:
    - flatten: All nodes combined (default, current behavior)
    - per_group: One demand per (src_group, dst_group) pair
    - group_pairwise: Pairwise expansion within each group pair
    """
    if td.group_mode == "flatten":
        # Standard behavior: flatten all groups, then apply mode
        if td.mode == "combine":
            return _expand_combine(td, src_groups, dst_groups, policy_preset)
        elif td.mode == "pairwise":
            return _expand_pairwise(td, src_groups, dst_groups, policy_preset)
        else:
            raise ValueError(f"Unknown demand mode: {td.mode}")

    elif td.group_mode == "per_group":
        # One demand per (src_group, dst_group) pair
        all_demands: List[ExpandedDemand] = []
        all_augmentations: List[AugmentationEdge] = []

        for src_label, src_nodes in src_groups.items():
            for dst_label, dst_nodes in dst_groups.items():
                if src_label == dst_label:
                    continue  # Skip same-group pairs

                group_td = replace(td, id=f"{td.id}|{src_label}|{dst_label}")
                single_src = {src_label: src_nodes}
                single_dst = {dst_label: dst_nodes}

                if td.mode == "combine":
                    demands, augs = _expand_combine(
                        group_td, single_src, single_dst, policy_preset
                    )
                else:
                    demands, augs = _expand_pairwise(
                        group_td, single_src, single_dst, policy_preset
                    )

                all_demands.extend(demands)
                all_augmentations.extend(augs)

        return all_demands, all_augmentations

    elif td.group_mode == "group_pairwise":
        # Pairwise between groups: each src group to each dst group
        all_demands: List[ExpandedDemand] = []
        all_augmentations: List[AugmentationEdge] = []

        group_pairs = [
            (src_label, dst_label)
            for src_label in src_groups
            for dst_label in dst_groups
            if src_label != dst_label
        ]

        if not group_pairs:
            return [], []

        # Divide volume among group pairs
        volume_per_group_pair = td.volume / len(group_pairs)

        for src_label, dst_label in group_pairs:
            group_td = replace(
                td,
                id=f"{td.id}|{src_label}|{dst_label}",
                volume=volume_per_group_pair,
            )
            single_src = {src_label: src_groups[src_label]}
            single_dst = {dst_label: dst_groups[dst_label]}

            if td.mode == "combine":
                demands, augs = _expand_combine(
                    group_td, single_src, single_dst, policy_preset
                )
            else:
                demands, augs = _expand_pairwise(
                    group_td, single_src, single_dst, policy_preset
                )

            all_demands.extend(demands)
            all_augmentations.extend(augs)

        return all_demands, all_augmentations

    else:
        raise ValueError(f"Unknown group_mode: {td.group_mode}")


def expand_demands(
    network: Network,
    traffic_demands: List[TrafficDemand],
    default_policy_preset: FlowPolicyPreset = FlowPolicyPreset.SHORTEST_PATHS_ECMP,
) -> DemandExpansion:
    """Expand TrafficDemand specifications into concrete demands with augmentations.

    Pure function that:
    1. Normalizes and evaluates selectors to get node groups
    2. Distributes volume based on mode (combine/pairwise) and group_mode
    3. Generates augmentation edges for combine mode (pseudo nodes)
    4. Returns demands (node names) + augmentations

    Node names are used (not IDs) so expansion happens BEFORE graph building.
    IDs are resolved after graph is built with augmentations.

    Note: Variable expansion (expand: block) is handled during YAML parsing in
    build_demand_set(), so TrafficDemand objects here are already expanded.

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
        # Step 1: Normalize selectors
        src_sel = normalize_selector(td.source, "demand")
        tgt_sel = normalize_selector(td.target, "demand")

        # Step 2: Select nodes (active_only=True for demands by context default)
        src_groups = select_nodes(network, src_sel, default_active_only=True)
        dst_groups = select_nodes(network, tgt_sel, default_active_only=True)

        if not src_groups or not dst_groups:
            continue

        policy_preset = td.flow_policy or default_policy_preset

        # Step 3: Expand by group_mode
        demands, augmentations = _expand_by_group_mode(
            td, src_groups, dst_groups, policy_preset
        )

        all_demands.extend(demands)
        all_augmentations.extend(augmentations)

    if not all_demands:
        raise ValueError(
            "No demands could be expanded. Possible causes:\n"
            "  - Source/target selectors don't match any nodes\n"
            "  - All matching nodes are disabled\n"
            "  - Source and target are identical (self-loops not allowed)"
        )

    # Sort by priority (lower = higher priority)
    sorted_demands = sorted(all_demands, key=lambda d: d.priority)

    return DemandExpansion(demands=sorted_demands, augmentations=all_augmentations)
