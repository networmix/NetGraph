"""Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager. Each analysis function
takes a Network, exclusion sets, and analysis-specific parameters, returning
results of type FlowIterationResult.

Parameters should ideally be hashable so FailureManager can deduplicate
identical failure patterns before dispatch; non-hashable objects are keyed
by memory address.

Graph caching builds the graph once and applies each exclusion set as an
O(|excluded|) mask instead of rebuilding.

SPF caching computes shortest paths once per unique source node rather than
once per demand. For networks with many demands sharing the same sources, this
can reduce SPF computations by an order of magnitude.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, Set

import netgraph_core

from ngraph.analysis.context import AnalysisContext, analyze
from ngraph.analysis.demand import DemandExpansion, expand_demands
from ngraph.analysis.placement import place_demands
from ngraph.model.demand.builder import coerce_flow_policy
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.types.base import FlowPlacement, Mode


def _reconstruct_traffic_demands(
    demands_config: list[dict[str, Any]],
) -> list[TrafficDemand]:
    """Reconstruct TrafficDemand objects from serialized config.

    Configs without an "id" receive a deterministic id derived from
    source, target, and list position. This keeps pseudo node names
    (which embed the demand id) stable across repeated reconstructions,
    so a context pre-built from the same config list stays consistent.

    Field defaults match TrafficDemand's own defaults (mode="combine",
    group_mode="flatten"), so a config produced by `TrafficDemand.to_dict`
    round-trips faithfully.

    Args:
        demands_config: List of demand configurations with fields:
            source, target, volume, mode, group_mode, flow_policy,
            priority, attrs.

    Returns:
        List of TrafficDemand objects with stable IDs.
    """
    results = []
    for i, config in enumerate(demands_config):
        results.append(
            TrafficDemand(
                id=config.get("id")
                or f"{config['source']}|{config.get('target', '')}|{i}",
                source=config["source"],
                target=config.get("target", ""),
                volume=config.get("volume", 0.0),
                mode=config.get("mode", "combine"),
                group_mode=config.get("group_mode", "flatten"),
                flow_policy=coerce_flow_policy(config.get("flow_policy")),
                priority=config.get("priority", 0),
                attrs=config.get("attrs") or {},
            )
        )
    return results


if TYPE_CHECKING:
    from ngraph.model.network import Network


def _with_prepare_inputs(
    prepare: "Callable[[Network, dict[str, Any]], dict[str, Any]]",
):
    """Attach a FailureManager pre-build hook to an analysis function.

    ``FailureManager.run_monte_carlo_analysis`` calls
    ``func.prepare_inputs(network, analysis_kwargs)`` once per run (unless
    the caller already supplied ``context``) and merges the returned extra
    kwargs into every iteration's call. Third-party analysis functions can
    opt in the same way by setting a ``prepare_inputs`` attribute.
    """

    def _attach(func):
        func.prepare_inputs = prepare  # type: ignore[attr-defined]
        return func

    return _attach


def _prepare_demand_placement_inputs(
    network: "Network", analysis_kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Pre-build context, expansion, and resolved node IDs once per MC run."""
    context, expansion, resolved_ids = build_demand_placement_inputs(
        network, analysis_kwargs["demands_config"]
    )
    return {
        "context": context,
        "expansion": expansion,
        "resolved_ids": resolved_ids,
    }


def _prepare_maxflow_inputs(
    network: "Network", analysis_kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Pre-build the bound max-flow context once per MC run."""
    return {
        "context": build_maxflow_context(
            network,
            analysis_kwargs["source"],
            analysis_kwargs["target"],
            mode=analysis_kwargs.get("mode", "combine"),
        )
    }


@_with_prepare_inputs(_prepare_maxflow_inputs)
def max_flow_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    source: str | dict[str, Any],
    target: str | dict[str, Any],
    mode: str = "combine",
    shortest_path: bool = False,
    require_capacity: bool = True,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    include_flow_details: bool = False,
    include_min_cut: bool = False,
    context: Optional[AnalysisContext] = None,
) -> FlowIterationResult:
    """Analyze maximum flow capacity between node groups.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: If True, use single-tier shortest-path flow (IP/IGP
            mode) instead of full iterative max-flow.
        require_capacity: If True (default), path selection considers available
            capacity. If False, path selection is cost-only (true IP/IGP semantics).
        flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP).
        include_flow_details: Whether to collect cost distribution and similar details.
        include_min_cut: Whether to include min-cut edge list in entry data.
        context: Pre-built AnalysisContext reused across calls. Must be
            unbound or bound to these same source/target/mode arguments.

    Returns:
        FlowIterationResult describing this iteration.
    """
    # Convert string mode to Mode enum (raises on invalid values)
    mode_enum = Mode.from_string(mode)

    # Use provided context or create a new one. A bound context carries its
    # own source/sink/mode; silently ignoring mismatched arguments would
    # return results for the wrong pair, so reject the mismatch loudly.
    if context is not None:
        ctx = context
        if ctx.is_bound and (
            ctx.bound_source != source
            or ctx.bound_sink != target
            or ctx.bound_mode != mode_enum
        ):
            raise ValueError(
                "Provided context is bound to "
                f"source={ctx.bound_source!r}, sink={ctx.bound_sink!r}, "
                f"mode={ctx.bound_mode}, which differs from the analysis "
                "arguments; rebuild the context or pass matching arguments."
            )
    else:
        ctx = analyze(network, source=source, sink=target, mode=mode_enum)

    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    if include_flow_details or include_min_cut:
        flows = ctx.max_flow_detailed(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
            include_min_cut=include_min_cut,
        )
        for (src, dst), summary in flows.items():
            value = float(summary.total_flow)
            cost_dist = summary.cost_distribution or {}
            min_cut_edges = summary.min_cut or ()
            entry = FlowEntry(
                source=str(src),
                destination=str(dst),
                priority=0,
                demand=value,
                placed=value,
                dropped=0.0,
                cost_distribution=(
                    {float(k): float(v) for k, v in cost_dist.items()}
                    if include_flow_details
                    else {}
                ),
                data=(
                    {
                        "edges": [f"{e.link_id}:{e.direction}" for e in min_cut_edges],
                        "edges_kind": "min_cut",
                    }
                    if include_min_cut and min_cut_edges
                    else {}
                ),
            )
            flow_entries.append(entry)
            total_demand += value
            total_placed += value
    else:
        flows = ctx.max_flow(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )
        for (src, dst), val in flows.items():
            value = float(val)
            entry = FlowEntry(
                source=str(src),
                destination=str(dst),
                priority=0,
                demand=value,
                placed=value,
                dropped=0.0,
            )
            flow_entries.append(entry)
            total_demand += value
            total_placed += value

    overall_ratio = (total_placed / total_demand) if total_demand > 0 else 1.0
    dropped_flows = sum(1 for e in flow_entries if e.dropped > 0.0)
    summary = FlowSummary(
        total_demand=total_demand,
        total_placed=total_placed,
        overall_ratio=overall_ratio,
        dropped_flows=dropped_flows,
        num_flows=len(flow_entries),
    )
    return FlowIterationResult(flows=flow_entries, summary=summary)


@_with_prepare_inputs(_prepare_demand_placement_inputs)
def demand_placement_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    demands_config: list[dict[str, Any]],
    include_flow_details: bool = False,
    include_used_edges: bool = False,
    context: Optional[AnalysisContext] = None,
    expansion: Optional[DemandExpansion] = None,
    resolved_ids: Optional[Sequence[tuple[int, int]]] = None,
) -> FlowIterationResult:
    """Analyze traffic demand placement success rates using Core directly.

    Steps:
    1. Build Core infrastructure (graph, algorithms, flow_graph), or reuse the
       pre-built ``context``
    2. Expand demands into concrete (src, dst, volume) tuples (or use a
       pre-computed expansion)
    3. Place each demand using SPF caching for cacheable policies.
       SHORTEST_PATHS_* presets admit flow onto the cost-only shortest paths
       of the base topology and drop overflow (IGP semantics); TE_* presets
       reroute remaining volume onto residual-capacity paths.
    4. Fall back to FlowPolicy for presets outside CACHEABLE_PRESETS
    5. Aggregate results into FlowIterationResult

    SPF Caching Optimization:
        For cacheable policies (ECMP, WCMP, TE_WCMP_UNLIM), SPF results are
        cached by source node. This reduces SPF computations from O(demands)
        to O(unique_sources), typically a 5-10x reduction for workloads with
        many demands sharing the same sources.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        demands_config: List of demand configurations (serializable dicts).
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data.
        context: Pre-built AnalysisContext, reused across calls. Must be built
            from this same demands_config - pseudo node names embed demand
            ids, so a context built from a different config raises ValueError
            during endpoint resolution. See build_demand_placement_inputs.
        expansion: Pre-computed DemandExpansion matching demands_config. When
            provided, per-call demand reconstruction and expansion are skipped.
            Must be built together with ``context`` (pseudo node names embed
            demand ids) - see build_demand_placement_inputs.
        resolved_ids: Pre-resolved (src_id, dst_id) pairs aligned with
            expansion.demands. Only valid together with ``context``.

    Returns:
        FlowIterationResult describing this iteration.
    """
    if expansion is None:
        traffic_demands = _reconstruct_traffic_demands(demands_config)

        # Phase 1: Expand demands (pure logic, returns names + augmentations)
        expansion = expand_demands(
            network,
            traffic_demands,
            default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        )

    # Phase 2: Use cached context infrastructure or build fresh
    if context is not None:
        ctx = context
    else:
        # Build fresh context with augmentations
        ctx = AnalysisContext.from_network(
            network, augmentations=expansion.augmentations
        )

    node_mask = ctx.build_node_mask(excluded_nodes)
    edge_mask = ctx.build_edge_mask(excluded_links)
    flow_graph = netgraph_core.FlowGraph(ctx.multidigraph)

    # Phase 3: Place demands using unified placement module
    result = place_demands(
        expansion.demands,
        [d.volume for d in expansion.demands],
        flow_graph,
        ctx,
        node_mask,
        edge_mask,
        resolved_ids=resolved_ids,
        collect_entries=True,
        include_cost_distribution=include_flow_details,
        include_used_edges=include_used_edges,
    )

    # Phase 4: Convert to FlowEntry format
    flow_entries = [
        FlowEntry(
            source=e.src_name,
            destination=e.dst_name,
            priority=e.priority,
            demand=e.volume,
            placed=e.placed,
            dropped=e.volume - e.placed,
            cost_distribution=e.cost_distribution,
            data=(
                {"edges": sorted(e.used_edges), "edges_kind": "used"}
                if e.used_edges
                else {}
            ),
        )
        for e in result.entries or []
    ]

    dropped_flows = sum(1 for e in flow_entries if e.dropped > 0.0)
    summary = FlowSummary(
        total_demand=result.summary.total_demand,
        total_placed=result.summary.total_placed,
        overall_ratio=result.summary.ratio,
        dropped_flows=dropped_flows,
        num_flows=len(flow_entries),
    )

    return FlowIterationResult(flows=flow_entries, summary=summary, data={})


@_with_prepare_inputs(_prepare_maxflow_inputs)
def sensitivity_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    source: str | dict[str, Any],
    target: str | dict[str, Any],
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    context: Optional[AnalysisContext] = None,
) -> FlowIterationResult:
    """Analyze component sensitivity to failures.

    Identifies critical edges (saturated edges) and computes the flow reduction
    caused by removing each one. Returns a FlowIterationResult where each
    FlowEntry represents a source/target pair with:
    - demand/placed = max flow value (the capacity being analyzed)
    - dropped = 0.0 (baseline analysis, no failures applied)
    - data["sensitivity"] = {link_id:direction: flow_reduction} for critical edges

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: If True, use single-tier shortest-path flow (IP/IGP mode).
            Reports only edges used under ECMP routing. If False (default), use
            full iterative max-flow (SDN/TE mode) and report all saturated edges.
        flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP).
        context: Pre-built AnalysisContext reused across calls. Must be
            unbound or bound to these same source/target/mode arguments.

    Returns:
        FlowIterationResult with sensitivity data in each FlowEntry.data.
    """
    # Convert string mode to Mode enum (raises on invalid values)
    mode_enum = Mode.from_string(mode)

    # Use provided context or create a new one. A bound context carries its
    # own source/sink/mode; silently ignoring mismatched arguments would
    # return results for the wrong pair, so reject the mismatch loudly.
    if context is not None:
        ctx = context
        if ctx.is_bound and (
            ctx.bound_source != source
            or ctx.bound_sink != target
            or ctx.bound_mode != mode_enum
        ):
            raise ValueError(
                "Provided context is bound to "
                f"source={ctx.bound_source!r}, sink={ctx.bound_sink!r}, "
                f"mode={ctx.bound_mode}, which differs from the analysis "
                "arguments; rebuild the context or pass matching arguments."
            )
    else:
        ctx = analyze(network, source=source, sink=target, mode=mode_enum)

    # Get max flow and sensitivity (critical edges) for each pair in a
    # single pass: masks are built once and the pairs are walked once.
    combined = ctx.sensitivity_with_flow(
        shortest_path=shortest_path,
        flow_placement=flow_placement,
        excluded_nodes=excluded_nodes,
        excluded_links=excluded_links,
    )

    # Build FlowEntry for each pair
    flow_entries: list[FlowEntry] = []
    total_flow = 0.0

    for (src, dst), (flow_value, sensitivity_map) in combined.items():
        entry = FlowEntry(
            source=str(src),
            destination=str(dst),
            priority=0,
            demand=flow_value,
            placed=flow_value,
            dropped=0.0,
            data={"sensitivity": sensitivity_map},
        )
        flow_entries.append(entry)
        total_flow += flow_value

    # Build summary
    summary = FlowSummary(
        total_demand=total_flow,
        total_placed=total_flow,
        overall_ratio=1.0,
        dropped_flows=0,
        num_flows=len(flow_entries),
    )

    return FlowIterationResult(flows=flow_entries, summary=summary)


def build_demand_placement_inputs(
    network: "Network",
    demands_config: list[dict[str, Any]],
) -> tuple[AnalysisContext, DemandExpansion, list[tuple[int, int]]]:
    """Build context, expansion, and resolved node IDs for demand placement.

    Reconstructs and expands demands once so repeated calls to
    demand_placement_analysis (e.g., Monte Carlo iterations) can skip the
    per-iteration expansion and node-ID resolution work. Building the
    expansion and context together guarantees that pseudo node names
    (derived from demand ids) match the context's graph.

    Args:
        network: Network instance.
        demands_config: List of demand configurations (same format as
            demand_placement_analysis).

    Returns:
        Tuple of (context, expansion, resolved_ids) where resolved_ids holds
        (src_id, dst_id) pairs aligned with expansion.demands.
    """
    traffic_demands = _reconstruct_traffic_demands(demands_config)

    # Expand demands once to get augmentations and concrete demands
    expansion = expand_demands(
        network,
        traffic_demands,
        default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
    )

    # Build context with augmentations
    context = analyze(network, augmentations=expansion.augmentations)

    # Pre-resolve node IDs once
    resolved_ids = [
        (context.node_mapper.to_id(d.src_name), context.node_mapper.to_id(d.dst_name))
        for d in expansion.demands
    ]
    return context, expansion, resolved_ids


def build_maxflow_context(
    network: "Network",
    source: str | dict[str, Any],
    target: str | dict[str, Any],
    mode: str = "combine",
) -> AnalysisContext:
    """Build an AnalysisContext for repeated max-flow analysis.

    Pre-computes the graph with pseudo source/target nodes for all source/target
    pairs, enabling O(|excluded|) mask building per iteration.

    Args:
        network: Network instance.
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        mode: Flow analysis mode ("combine" or "pairwise").

    Returns:
        AnalysisContext ready for use with max_flow_analysis or sensitivity_analysis.
    """
    mode_enum = Mode.from_string(mode)
    return analyze(network, source=source, sink=target, mode=mode_enum)
