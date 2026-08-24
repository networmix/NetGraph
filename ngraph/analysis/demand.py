"""Demand expansion: converts TrafficDemand specs into concrete placement demands.

Combine mode aggregates each side behind augmentation-based pseudo nodes;
pairwise mode emits one demand per (source, target) pair. Endpoints are
resolved through the shared selector layer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

from ngraph.analysis.context import LARGE_CAPACITY, AugmentationEdge
from ngraph.dsl.selectors import normalize_selector
from ngraph.model.demand.spec import StaticPath, TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.model.network import Network, Node
from ngraph.model.selectors import select_nodes


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
        static_paths: Routes this demand is pinned to, empty when it is
            routed by the policy.
    """

    src_name: str
    dst_name: str
    volume: float
    priority: int
    policy_preset: FlowPolicyPreset
    static_paths: Tuple[StaticPath, ...] = ()


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
    """Expand combine mode: aggregate sources/sinks through pseudo nodes.

    Nodes selected on both sides are excluded from the target set. Without
    this guard a shared node would be attached to both pseudo endpoints,
    forming a zero-cost pseudo_src -> node -> pseudo_snk bypass over two
    LARGE_CAPACITY augmentation edges that absorbs the entire demand
    without touching the real network. This mirrors the overlap invariant
    enforced in context._build_pseudo_node_augmentations. If the exclusion
    empties the target set, nothing is expanded.
    """
    pseudo_src = f"_src_{td.id}"
    pseudo_snk = f"_snk_{td.id}"

    src_names = _flatten_group_names(src_groups)
    src_name_set = set(src_names)
    dst_names = [
        name for name in _flatten_group_names(dst_groups) if name not in src_name_set
    ]

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
            static_paths=td.static_paths,
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
    - flatten: All groups merged into one node set, then mode applied.
    - per_group: Each group expands independently. With mode=combine, one
      demand per source group with all target groups combined (nodes in
      the source group itself are excluded from the targets; a source
      group whose targets become empty after exclusion is skipped); with
      mode=pairwise, pairwise within each group label present on both
      sides. td.volume is split evenly across groups; a skipped group's
      share is not redistributed, so total expanded volume can be less
      than td.volume when exclusion empties a group's targets or a label
      has no non-self pairs.
    - group_pairwise: One expansion per (src_group, dst_group) label pair
      with distinct labels (same-label pairs are skipped), with td.volume
      split evenly across those pairs; a pair that empties after
      source/target overlap exclusion likewise drops its share.
    """
    # td.mode and td.group_mode are validated by TrafficDemand.__post_init__,
    # so mode is "combine" or "pairwise" in every branch below.
    if td.group_mode == "flatten":
        # Standard behavior: flatten all groups, then apply mode
        if td.mode == "combine":
            return _expand_combine(td, src_groups, dst_groups, policy_preset)
        return _expand_pairwise(td, src_groups, dst_groups, policy_preset)

    elif td.group_mode == "per_group":
        all_demands: List[ExpandedDemand] = []
        all_augmentations: List[AugmentationEdge] = []

        if td.mode == "combine":
            # One demand per source group, all target groups combined
            if not src_groups:
                return [], []
            volume_per_group = td.volume / len(src_groups)
            for src_label, src_nodes in src_groups.items():
                group_td = replace(
                    td, id=f"{td.id}|{src_label}", volume=volume_per_group
                )
                demands, augs = _expand_combine(
                    group_td, {src_label: src_nodes}, dst_groups, policy_preset
                )
                all_demands.extend(demands)
                all_augmentations.extend(augs)
        else:
            # Pairwise within each group label present on both sides
            shared_labels = [label for label in src_groups if label in dst_groups]
            if not shared_labels:
                return [], []
            volume_per_group = td.volume / len(shared_labels)
            for label in shared_labels:
                group_td = replace(td, id=f"{td.id}|{label}", volume=volume_per_group)
                demands, augs = _expand_pairwise(
                    group_td,
                    {label: src_groups[label]},
                    {label: dst_groups[label]},
                    policy_preset,
                )
                all_demands.extend(demands)
                all_augmentations.extend(augs)

        return all_demands, all_augmentations

    else:  # group_pairwise
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

        for pair_index, (src_label, dst_label) in enumerate(group_pairs):
            # Labels are '|'-joined regex captures and may themselves contain
            # '|', so a purely label-composed id is ambiguous across pairs.
            # The enumeration index makes the id injective; labels are kept
            # for readability.
            group_td = replace(
                td,
                id=f"{td.id}|{src_label}|{dst_label}#gp{pair_index}",
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
        ValueError: If no demands could be expanded, if two demands share an
            id (pseudo node names embed the id, so duplicates would merge
            distinct demands' attachment edges into one endpoint), or if a
            demand with `static_paths` does not resolve to exactly one
            source/target pair.
    """
    seen_ids: set[str] = set()
    for td in traffic_demands:
        if td.id in seen_ids:
            raise ValueError(
                f"Duplicate TrafficDemand id '{td.id}'. Demand ids must be "
                "unique within one expansion."
            )
        seen_ids.add(td.id)

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
            if td.static_paths:
                raise ValueError(
                    f"Demand '{td.id}' sets static_paths but its selectors match "
                    "no active source or target node"
                )
            continue

        policy_preset = td.flow_policy or default_policy_preset

        # Step 3: Expand by group_mode
        demands, augmentations = _expand_by_group_mode(
            td, src_groups, dst_groups, policy_preset
        )

        if td.static_paths:
            # Routes are pinned between two concrete nodes, so the demand has
            # to name exactly one pair. Combine mode routes through pseudo
            # endpoints, which no operator-supplied route can start from.
            if td.mode == "combine":
                raise ValueError(
                    f"Demand '{td.id}' sets static_paths, which pins traffic to "
                    "routes between two nodes; use mode 'pairwise' instead of "
                    "'combine'"
                )
            if len(demands) != 1:
                raise ValueError(
                    f"Demand '{td.id}' sets static_paths but its selectors "
                    f"expand to {len(demands)} source/target pairs; static "
                    "paths require selectors matching exactly one source and "
                    "one target"
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

    # Pseudo endpoints must be unique across the whole expansion: composed
    # ids concatenate demand ids and group labels, both of which may contain
    # '|', so distinct demands can render to the same pseudo name (e.g.
    # id "X" + label "Y|Z" vs id "X|Y" + label "Z"). A shared pseudo node
    # would silently merge the demands' attachment edges, recreating the
    # zero-cost bypass.
    seen_endpoints: set[str] = set()
    for d in all_demands:
        for name in (d.src_name, d.dst_name):
            if not name.startswith(("_src_", "_snk_")):
                continue
            if name in seen_endpoints:
                raise ValueError(
                    f"Ambiguous demand expansion: pseudo endpoint '{name}' is "
                    "claimed by two different demand expansions. Demand ids "
                    "and group labels containing '|' can compose to the same "
                    "id; use distinct demand ids."
                )
            seen_endpoints.add(name)

    # Sort by priority (lower = higher priority)
    sorted_demands = sorted(all_demands, key=lambda d: d.priority)

    return DemandExpansion(demands=sorted_demands, augmentations=all_augmentations)
