"""Flow policy preset configurations for NetGraph.

Provides convenient factory functions to create common FlowPolicy configurations
using NetGraph-Core's FlowPolicy and FlowPolicyConfig.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from ngraph.logging import get_logger

try:
    import netgraph_core
except ImportError as e:
    raise ImportError(
        "netgraph_core module not found. Ensure NetGraph-Core is installed."
    ) from e

logger = get_logger(__name__)


class FlowPolicyPreset(IntEnum):
    """Enumerates common flow policy presets for traffic routing.

    These presets map to specific combinations of path algorithms, flow placement
    strategies, and edge selection modes provided by NetGraph-Core.
    """

    SHORTEST_PATHS_ECMP = 1
    """Hop-by-hop equal-cost multi-path routing (ECMP).

    Single flow with equal-cost path splitting, similar to IP forwarding with ECMP.
    """

    SHORTEST_PATHS_WCMP = 2
    """Hop-by-hop weighted cost multi-path routing (WCMP).

    Single flow with proportional splitting over equal-cost paths.
    """

    TE_WCMP_UNLIM = 3
    """Traffic engineering with unlimited WCMP flows.

    Capacity-aware path selection with proportional flow placement.
    """

    TE_ECMP_UP_TO_256_LSP = 4
    """Traffic engineering with up to 256 label-switched paths (LSPs) using ECMP.

    Capacity-aware path selection with equal-balanced placement and reoptimization.

    Each LSP is a distinct tunnel using a single path (MPLS LSP semantics). Multiple LSPs
    can share the same path. With N LSPs and M paths where N > M, LSPs are distributed
    across paths (~N/M LSPs per path). ECMP constraint ensures all LSPs carry equal volume.

    Configuration: multipath=False ensures tunnel-based ECMP (not hash-based ECMP).
    """

    TE_ECMP_16_LSP = 5
    """Traffic engineering with exactly 16 LSPs using ECMP.

    Fixed 16 flows with capacity-aware selection, equal-balanced placement, and reoptimization.

    Each LSP is a distinct tunnel using a single path (MPLS LSP semantics). With 16 LSPs
    and M paths: if M ≥ 16, one LSP per path; if M < 16, some paths carry multiple LSPs.
    ECMP constraint ensures all LSPs carry equal volume.

    Example: 15 parallel paths (capacity 1.0 each) with 16 LSPs:
      - 15 paths carry 1 LSP, 1 path carries 2 LSPs
      - ECMP constraint limits all LSPs to 0.5 units (bottleneck path: 1.0 / 2 = 0.5)
      - Total: 16 × 0.5 = 8.0 units

    Configuration: multipath=False ensures tunnel-based ECMP (not hash-based ECMP).
    """


def create_flow_policy(
    algorithms: netgraph_core.Algorithms,
    graph: netgraph_core.Graph,
    preset: FlowPolicyPreset,
    node_mask=None,
    edge_mask=None,
) -> netgraph_core.FlowPolicy:
    """Create a FlowPolicy instance from a preset configuration.

    Args:
        algorithms: NetGraph-Core Algorithms instance.
        graph: NetGraph-Core Graph handle.
        preset: FlowPolicyPreset enum value specifying the desired policy.
        node_mask: Optional numpy bool array for node exclusions (True = include).
        edge_mask: Optional numpy bool array for edge exclusions (True = include).

    Returns:
        netgraph_core.FlowPolicy: Configured policy instance.

    Raises:
        ValueError: If an unknown FlowPolicyPreset value is provided.

    Example:
        >>> backend = netgraph_core.Backend.cpu()
        >>> algs = netgraph_core.Algorithms(backend)
        >>> graph = algs.build_graph(strict_multidigraph)
        >>> policy = create_flow_policy(algs, graph, FlowPolicyPreset.SHORTEST_PATHS_ECMP)
    """
    if preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP:
        # Hop-by-hop equal-cost balanced routing (similar to IP forwarding with ECMP)
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=False,
            tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
        )
        config.min_flow_count = 1
        config.max_flow_count = 1
        return netgraph_core.FlowPolicy(
            algorithms, graph, config, node_mask=node_mask, edge_mask=edge_mask
        )

    elif preset == FlowPolicyPreset.SHORTEST_PATHS_WCMP:
        # Hop-by-hop weighted ECMP (WCMP) over equal-cost paths (proportional split)
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=False,
            tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
        )
        config.min_flow_count = 1
        config.max_flow_count = 1
        return netgraph_core.FlowPolicy(
            algorithms, graph, config, node_mask=node_mask, edge_mask=edge_mask
        )

    elif preset == FlowPolicyPreset.TE_WCMP_UNLIM:
        # Traffic engineering with WCMP (proportional split) and capacity-aware selection
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.min_flow_count = 1
        # max_flow_count defaults to None (unlimited)
        return netgraph_core.FlowPolicy(
            algorithms, graph, config, node_mask=node_mask, edge_mask=edge_mask
        )

    elif preset == FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP:
        # TE with up to 256 LSPs using ECMP flow placement
        # multipath=False ensures each LSP is a single path (MPLS tunnel semantics)
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False  # Each LSP uses a single path (tunnel-based ECMP)
        config.min_flow_count = 1
        config.max_flow_count = 256
        config.reoptimize_flows_on_each_placement = True
        return netgraph_core.FlowPolicy(
            algorithms, graph, config, node_mask=node_mask, edge_mask=edge_mask
        )

    elif preset == FlowPolicyPreset.TE_ECMP_16_LSP:
        # TE with exactly 16 LSPs using ECMP flow placement
        # multipath=False ensures each LSP is a single path (MPLS tunnel semantics)
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False  # Each LSP uses a single path (tunnel-based ECMP)
        config.min_flow_count = 16
        config.max_flow_count = 16
        config.reoptimize_flows_on_each_placement = True
        return netgraph_core.FlowPolicy(
            algorithms, graph, config, node_mask=node_mask, edge_mask=edge_mask
        )

    else:
        raise ValueError(f"Unknown flow policy preset: {preset}")


def serialize_policy_preset(cfg: Any) -> Optional[str]:
    """Serialize a FlowPolicyPreset to its string name for JSON storage.

    Handles FlowPolicyPreset enum values, integer enum values, and string fallbacks.
    Returns None for None input.

    Args:
        cfg: FlowPolicyPreset enum, integer, or other value to serialize.

    Returns:
        String name of the preset (e.g., "SHORTEST_PATHS_ECMP"), or None if input is None.
    """
    if cfg is None:
        return None
    if isinstance(cfg, FlowPolicyPreset):
        return cfg.name
    # Try to coerce integer to enum
    try:
        return FlowPolicyPreset(int(cfg)).name
    except (ValueError, TypeError) as exc:
        logger.debug("Unrecognized flow_policy_preset value: %r (%s)", cfg, exc)
        return str(cfg)
