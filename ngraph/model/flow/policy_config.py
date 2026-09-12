"""Flow policy preset configurations for NetGraph.

Named routing presets, the single mapping from a preset to a NetGraph-Core
``FlowPolicyConfig``, and the factory that materializes a preset as a Core
``FlowPolicy``. Both placement engines (the SPF-cached fast path in
``ngraph.analysis.placement`` and Core's FlowPolicy) read their edge selection
and placement mode from ``preset_config`` so the two cannot drift.
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

    The ``SHORTEST_PATHS_*`` presets model hop-by-hop IP/IGP forwarding: routes
    follow link costs alone and each demand is placed in one pass on the
    cost-only shortest-path DAG. The ``TE_*`` presets model a controller that
    selects paths with knowledge of residual capacity.
    """

    SHORTEST_PATHS_ECMP = 1
    """Hop-by-hop equal-cost multi-path routing (ECMP), lossless admission.

    Traffic is hashed equally over every equal-cost next hop and admitted at
    the largest volume that causes no loss on any of them. A next hop
    saturated by an earlier demand blocks admission of any later demand
    hashed onto it, because the forwarding table does not react to load.
    ``placed`` is the volume the network carries without drops.
    """

    SHORTEST_PATHS_WCMP = 2
    """Hop-by-hop weighted cost multi-path routing (WCMP).

    Single flow with proportional splitting over equal-cost paths. Weights
    follow residual capacity, which equals link capacity on an unloaded
    network and adapts to load placed by earlier demands.
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

    SHORTEST_PATHS_ECMP_LOSSY = 6
    """Hop-by-hop ECMP, best-effort forwarding with loss.

    Traffic is hashed equally over every equal-cost next hop; each link
    carries what fits and drops the rest, and a deficit propagates
    downstream. ``placed`` is the volume delivered to the destination and
    ``dropped`` is what was lost on the way. With flow details enabled the
    result records the dropped volume per link.
    """


#: Presets that model hop-by-hop IP/IGP forwarding: cost-only routes, one
#: placement pass per demand, no rerouting. In combine mode these presets
#: originate an even share of the demand at every source that can reach a
#: target.
HOP_BY_HOP_PRESETS: frozenset[FlowPolicyPreset] = frozenset(
    {
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
        FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
    }
)


def preset_config(preset: FlowPolicyPreset) -> netgraph_core.FlowPolicyConfig:
    """Build the Core ``FlowPolicyConfig`` a preset stands for.

    This is the single source of the preset semantics. The SPF-cached
    placement engine reads ``selection`` and ``flow_placement`` from it, and
    ``create_flow_policy`` materializes it as a Core ``FlowPolicy``.

    Hop-by-hop presets set ``require_capacity=False`` (routes follow costs
    only) and ``shortest_path=True`` (one placement on the cost-only DAG), so
    a FlowPolicy built from them places exactly what the cached engine
    places.

    Args:
        preset: Preset to describe.

    Returns:
        A fresh ``FlowPolicyConfig``; callers may adjust it further.

    Raises:
        ValueError: If an unknown FlowPolicyPreset value is provided.
    """
    config = netgraph_core.FlowPolicyConfig()
    config.path_alg = netgraph_core.PathAlg.SPF

    if preset in HOP_BY_HOP_PRESETS:
        # Hop-by-hop IP/IGP forwarding: cost-only routing, single pass, one
        # flow whose split rule is the only thing that differs per preset.
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=False,
            tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
        )
        config.require_capacity = False
        config.shortest_path = True
        config.min_flow_count = 1
        config.max_flow_count = 1
        if preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP:
            config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED_FIXED
        elif preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY:
            config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED_LOSSY
        else:
            config.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        return config

    if preset == FlowPolicyPreset.TE_WCMP_UNLIM:
        # Traffic engineering with WCMP (proportional split) and capacity-aware selection
        config.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.min_flow_count = 1
        # max_flow_count defaults to None (unlimited)
        return config

    if preset in (
        FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP,
        FlowPolicyPreset.TE_ECMP_16_LSP,
    ):
        # TE with ECMP flow placement over single-path tunnels.
        # multipath=False ensures each LSP is a single path (MPLS tunnel semantics)
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False
        config.reoptimize_flows_on_each_placement = True
        if preset == FlowPolicyPreset.TE_ECMP_16_LSP:
            config.min_flow_count = 16
            config.max_flow_count = 16
        else:
            config.min_flow_count = 1
            config.max_flow_count = 256
        return config

    raise ValueError(f"Unknown flow policy preset: {preset}")


def create_flow_policy(
    algorithms: netgraph_core.Algorithms,
    graph: netgraph_core.Graph,
    preset: FlowPolicyPreset,
    node_mask=None,
    edge_mask=None,
    static_path_count: Optional[int] = None,
) -> netgraph_core.FlowPolicy:
    """Create a FlowPolicy instance from a preset configuration.

    Args:
        algorithms: NetGraph-Core Algorithms instance.
        graph: NetGraph-Core Graph handle.
        preset: Preset whose path algorithm, placement, edge selection, and
            flow-count bounds to apply (see ``preset_config``).
        node_mask: Optional numpy bool array for node exclusions (True = include).
        edge_mask: Optional numpy bool array for edge exclusions (True = include).
        static_path_count: Number of routes the caller will pin with
            `FlowPolicy.set_static_paths`. Sets the flow count to match, since
            a pinned policy creates one flow per route and never grows.

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
    config = preset_config(preset)
    if static_path_count is not None:
        # A pinned policy creates exactly one flow per route, so the flow
        # bounds must match; Core rejects a mismatch. Cost ceilings,
        # reoptimization and the single-augmentation IP mode are inert or
        # rejected once paths are pinned.
        config.min_flow_count = 1
        config.max_flow_count = static_path_count
        config.reoptimize_flows_on_each_placement = False
        config.shortest_path = False
    return netgraph_core.FlowPolicy(
        algorithms, graph, config, node_mask=node_mask, edge_mask=edge_mask
    )


def serialize_policy_preset(cfg: Any) -> Optional[str]:
    """Serialize a FlowPolicyPreset to its string name for JSON storage.

    Args:
        cfg: FlowPolicyPreset enum, an integer coercible to one, or any other
            value.

    Returns:
        Preset name (e.g. "SHORTEST_PATHS_ECMP"); None when ``cfg`` is None.
        Values that do not map to a preset are logged at debug level and
        returned as ``str(cfg)``.
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
