"""Expansion helpers for traffic demand specifications.

Public functions here convert user-facing `TrafficDemand` specifications into
concrete `Demand` objects that can be placed on a `StrictMultiDiGraph`.

This module provides the pure expansion logic that was previously embedded in
`TrafficManager`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Union

from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.demand import Demand
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig, get_flow_policy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.model.network import Network, Node

try:
    # Avoid importing at runtime if not needed while keeping type hints precise
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:  # pragma: no cover - typing only
        from ngraph.model.view import NetworkView
except Exception:  # pragma: no cover - defensive for environments without extras
    TYPE_CHECKING = False


def expand_demands(
    network: Union[Network, "NetworkView"],
    graph: StrictMultiDiGraph | None,
    traffic_demands: List[TrafficDemand],
    default_flow_policy_config: FlowPolicyConfig,
) -> Tuple[List[Demand], Dict[str, List[Demand]]]:
    """Expand traffic demands into concrete `Demand` objects.

    The result is a flat list of `Demand` plus a mapping from
    ``TrafficDemand.id`` to the list of expanded demands for that entry.

    Args:
        network: Network or NetworkView used for node group selection.
        graph: Flow graph to operate on. If ``None``, expansion that requires
            graph mutation (pseudo nodes/edges) is skipped.
        traffic_demands: List of high-level traffic demand specifications.
        default_flow_policy_config: Default policy to apply when a demand does
            not specify an explicit `flow_policy`.

    Returns:
        A tuple ``(expanded, td_map)`` where:
        - ``expanded`` is the flattened, sorted list of all expanded demands
          (sorted by ascending ``demand_class``).
        - ``td_map`` maps ``TrafficDemand.id`` to its expanded demands.
    """
    td_to_demands: Dict[str, List[Demand]] = {}
    expanded: List[Demand] = []

    for td in traffic_demands:
        # Gather node groups for source and sink
        src_groups = network.select_node_groups_by_path(td.source_path)
        snk_groups = network.select_node_groups_by_path(td.sink_path)

        if not src_groups or not snk_groups:
            td_to_demands[td.id] = []
            continue

        demands_of_td: List[Demand] = []
        if td.mode == "combine":
            _expand_combine(
                demands_of_td,
                td,
                src_groups,
                snk_groups,
                graph,
                default_flow_policy_config,
            )
        elif td.mode == "pairwise":
            _expand_pairwise(
                demands_of_td,
                td,
                src_groups,
                snk_groups,
                default_flow_policy_config,
            )
        else:
            raise ValueError(f"Unknown mode: {td.mode}")

        expanded.extend(demands_of_td)
        td_to_demands[td.id] = demands_of_td

    # Sort final demands by ascending demand_class (i.e., priority)
    expanded.sort(key=lambda d: d.demand_class)
    return expanded, td_to_demands


def _expand_combine(
    expanded: List[Demand],
    td: TrafficDemand,
    src_groups: Dict[str, List[Node]],
    snk_groups: Dict[str, List[Node]],
    graph: StrictMultiDiGraph | None,
    default_flow_policy_config: FlowPolicyConfig,
) -> None:
    """Expand a single demand using the ``combine`` mode.

    Adds pseudo-source and pseudo-sink nodes, connects them to real nodes
    with infinite-capacity, zero-cost edges, and creates one aggregate
    `Demand` from pseudo-source to pseudo-sink with the full volume.
    """
    # Flatten and sort source and sink node lists for deterministic order
    src_nodes = sorted(
        (node for group_nodes in src_groups.values() for node in group_nodes),
        key=lambda n: n.name,
    )
    dst_nodes = sorted(
        (node for group_nodes in snk_groups.values() for node in group_nodes),
        key=lambda n: n.name,
    )

    if not src_nodes or not dst_nodes or graph is None:
        return

    # Create pseudo-source / pseudo-sink names
    pseudo_source_name = f"combine_src::{td.id}"
    pseudo_sink_name = f"combine_snk::{td.id}"

    # Add pseudo nodes to the graph only if missing (idempotent)
    if pseudo_source_name not in graph:
        graph.add_node(pseudo_source_name)
    if pseudo_sink_name not in graph:
        graph.add_node(pseudo_sink_name)

    # Link pseudo-source to real sources, and real sinks to pseudo-sink (idempotent)
    for s_node in src_nodes:
        if not graph.edges_between(pseudo_source_name, s_node.name):
            graph.add_edge(
                pseudo_source_name, s_node.name, capacity=float("inf"), cost=0
            )
    for t_node in dst_nodes:
        if not graph.edges_between(t_node.name, pseudo_sink_name):
            graph.add_edge(t_node.name, pseudo_sink_name, capacity=float("inf"), cost=0)

    # Initialize flow-related attributes without resetting existing usage
    init_flow_graph(graph, reset_flow_graph=False)

    # Create a single Demand with the full volume
    if td.flow_policy:
        flow_policy = td.flow_policy.deep_copy()
    else:
        fp_config = td.flow_policy_config or default_flow_policy_config
        flow_policy = get_flow_policy(fp_config)

    expanded.append(
        Demand(
            src_node=pseudo_source_name,
            dst_node=pseudo_sink_name,
            volume=td.demand,
            demand_class=td.priority,
            flow_policy=flow_policy,
        )
    )


def _expand_pairwise(
    expanded: List[Demand],
    td: TrafficDemand,
    src_groups: Dict[str, List[Node]],
    snk_groups: Dict[str, List[Node]],
    default_flow_policy_config: FlowPolicyConfig,
) -> None:
    """Expand a single demand using the ``pairwise`` mode.

    Creates one `Demand` for each valid source-destination pair (excluding
    self-pairs) and splits total volume evenly across pairs.
    """
    # Flatten and sort source and sink node lists for deterministic order
    src_nodes = sorted(
        (node for group_nodes in src_groups.values() for node in group_nodes),
        key=lambda n: n.name,
    )
    dst_nodes = sorted(
        (node for group_nodes in snk_groups.values() for node in group_nodes),
        key=lambda n: n.name,
    )

    # Generate all valid (src, dst) pairs in deterministic lexicographic order
    valid_pairs = []
    for s_node in src_nodes:
        for t_node in dst_nodes:
            if s_node.name != t_node.name:
                valid_pairs.append((s_node, t_node))
    pair_count = len(valid_pairs)
    if pair_count == 0:
        return

    demand_per_pair = td.demand / float(pair_count)

    for s_node, t_node in valid_pairs:
        if td.flow_policy:
            flow_policy = td.flow_policy.deep_copy()
        else:
            fp_config = td.flow_policy_config or default_flow_policy_config
            flow_policy = get_flow_policy(fp_config)

        expanded.append(
            Demand(
                src_node=s_node.name,
                dst_node=t_node.name,
                volume=demand_per_pair,
                demand_class=td.priority,
                flow_policy=flow_policy,
            )
        )
