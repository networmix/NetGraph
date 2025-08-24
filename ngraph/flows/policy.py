"""FlowPolicy and FlowPolicyConfig classes for traffic routing algorithms."""

from __future__ import annotations

import copy
from collections import deque
from enum import IntEnum
from typing import Any, Callable, Dict, Hashable, List, Optional, Set, Tuple

from ngraph.algorithms import base, edge_select, spf
from ngraph.algorithms.placement import FlowPlacement
from ngraph.flows.flow import Flow, FlowIndex
from ngraph.graph.strict_multidigraph import (
    AttrDict,
    EdgeID,
    NodeID,
    StrictMultiDiGraph,
)
from ngraph.logging import get_logger
from ngraph.paths.bundle import PathBundle


class FlowPolicyConfig(IntEnum):
    """Enumerates supported flow policy configurations."""

    SHORTEST_PATHS_ECMP = 1
    SHORTEST_PATHS_WCMP = 2
    TE_WCMP_UNLIM = 3
    TE_ECMP_UP_TO_256_LSP = 4
    TE_ECMP_16_LSP = 5


class FlowPolicy:
    """Create, place, rebalance, and remove flows on a network graph.

    Converts a demand into one or more `Flow` objects subject to capacity
    constraints and configuration: path selection, edge selection, and flow
    placement method.
    """

    def __init__(
        self,
        path_alg: base.PathAlg,
        flow_placement: FlowPlacement,
        edge_select: base.EdgeSelect,
        multipath: bool,
        min_flow_count: int = 1,
        max_flow_count: Optional[int] = None,
        max_path_cost: Optional[base.Cost] = None,
        max_path_cost_factor: Optional[float] = None,
        static_paths: Optional[List[PathBundle]] = None,
        edge_select_func: Optional[
            Callable[
                [
                    StrictMultiDiGraph,
                    NodeID,
                    NodeID,
                    Dict[EdgeID, AttrDict],
                    Optional[Set[EdgeID]],
                    Optional[Set[NodeID]],
                ],
                Tuple[base.Cost, List[EdgeID]],
            ]
        ] = None,
        edge_select_value: Optional[Any] = None,
        reoptimize_flows_on_each_placement: bool = False,
        max_no_progress_iterations: int = 100,
        max_total_iterations: int = 10000,
        # Diminishing-returns cutoff configuration
        diminishing_returns_enabled: bool = True,
        diminishing_returns_window: int = 8,
        diminishing_returns_epsilon_frac: float = 1e-3,
    ) -> None:
        """Initialize a policy instance.

        Args:
            path_alg: Path algorithm (e.g., SPF).
            flow_placement: Flow placement method (e.g., EQUAL_BALANCED, PROPORTIONAL).
            edge_select: Edge selection mode (e.g., ALL_MIN_COST).
            multipath: Whether to allow multiple parallel paths at the SPF stage.
            min_flow_count: Minimum number of flows to create for a demand.
            max_flow_count: Maximum number of flows allowable for a demand.
            max_path_cost: Absolute cost limit for allowable paths.
            max_path_cost_factor: Relative cost factor limit (multiplying the best path cost).
            static_paths: Predefined paths to force flows onto, if provided.
            edge_select_func: Custom function for edge selection.
            edge_select_value: Additional parameter for certain edge selection strategies.
            reoptimize_flows_on_each_placement: Re-run path optimization after every placement.
            max_no_progress_iterations: Max consecutive iterations with no progress before loop detection.
            max_total_iterations: Absolute max iterations regardless of progress.

        Raises:
            ValueError: If static_paths length does not match max_flow_count,
                        or if EQUAL_BALANCED placement is used without a
                        specified max_flow_count.
        """
        # Module logger
        self._logger = get_logger(__name__)
        self.path_alg: base.PathAlg = path_alg
        self.flow_placement: FlowPlacement = flow_placement
        self.edge_select: base.EdgeSelect = edge_select
        self.multipath: bool = multipath
        self.min_flow_count: int = min_flow_count
        self.max_flow_count: Optional[int] = max_flow_count
        self.max_path_cost: Optional[base.Cost] = max_path_cost
        self.max_path_cost_factor: Optional[float] = max_path_cost_factor
        self.static_paths: Optional[List[PathBundle]] = static_paths
        self.edge_select_func = edge_select_func
        self.edge_select_value: Optional[Any] = edge_select_value
        self.reoptimize_flows_on_each_placement: bool = (
            reoptimize_flows_on_each_placement
        )

        # Termination parameters for place_demand algorithm
        self.max_no_progress_iterations: int = max_no_progress_iterations
        self.max_total_iterations: int = max_total_iterations

        # Diminishing-returns cutoff parameters
        self.diminishing_returns_enabled: bool = diminishing_returns_enabled
        self.diminishing_returns_window: int = diminishing_returns_window
        self.diminishing_returns_epsilon_frac: float = diminishing_returns_epsilon_frac

        # Dictionary to track all flows by their FlowIndex.
        self.flows: Dict[Tuple, Flow] = {}

        # Track the best path cost found to enforce maximum path cost constraints.
        self.best_path_cost: Optional[base.Cost] = None

        # Internal flow ID counter.
        self._next_flow_id: int = 0

        # Basic placement metrics (cumulative totals over lifetime of this policy)
        self._metrics_totals: Dict[str, float] = {
            "spf_calls_total": 0.0,
            "flows_created_total": 0.0,
            "reopt_calls_total": 0.0,
            "place_iterations_total": 0.0,
        }
        # Snapshot of last place_demand call
        self.last_metrics: Dict[str, float] = {}

        # Cache for edge selectors to avoid rebuilding fabric callables
        # Keyed by (edge_select, effective_select_value)
        self._edge_selector_cache: Dict[Tuple[base.EdgeSelect, Any], Callable] = {}

        # Validate static_paths versus max_flow_count constraints.
        if static_paths:
            if max_flow_count is not None and len(static_paths) != max_flow_count:
                raise ValueError(
                    "If set, max_flow_count must be equal to the number of static paths."
                )
            self.max_flow_count = len(static_paths)
        if (
            flow_placement == FlowPlacement.EQUAL_BALANCED
            and self.max_flow_count is None
        ):
            raise ValueError("max_flow_count must be set for EQUAL_BALANCED placement.")

    def deep_copy(self) -> FlowPolicy:
        """Return a deep copy of this policy including flows."""
        return copy.deepcopy(self)

    @property
    def flow_count(self) -> int:
        """Number of flows currently tracked by the policy."""
        return len(self.flows)

    @property
    def placed_demand(self) -> float:
        """Sum of all placed flow volumes across flows."""
        return sum(flow.placed_flow for flow in self.flows.values())

    def _get_next_flow_id(self) -> int:
        """Retrieve and increment the internal flow id counter.

        Returns:
            int: Next available flow id.
        """
        next_flow_id = self._next_flow_id
        self._next_flow_id += 1
        return next_flow_id

    def _build_flow_index(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: Hashable,
        flow_id: int,
    ) -> FlowIndex:
        """Construct a `FlowIndex` to track flows.

        Args:
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            flow_id: Unique identifier for this flow.

        Returns:
            FlowIndex: Identifier for the flow.
        """
        return FlowIndex(src_node, dst_node, flow_class, flow_id)

    def _get_path_bundle(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        min_flow: Optional[float] = None,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ) -> Optional[PathBundle]:
        """Find a path bundle from src_node to dst_node.

        Optionally exclude certain edges or nodes.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            min_flow: Minimum flow threshold for selection.
            excluded_edges: Set of edges to exclude.
            excluded_nodes: Set of nodes to exclude.

        Returns:
            PathBundle | None: Bundle if found and cost-constrained; otherwise None.

        Raises:
            ValueError: If the selected path algorithm is not supported.
        """
        effective_select_value = (
            min_flow if min_flow is not None else self.edge_select_value
        )
        # Determine whether we can use SPF's internal fast path.
        # Fast path is available when:
        #  - no custom edge selector is provided
        #  - no custom select value is required (uses MIN_CAP internally)
        # In that case, we pass only the EdgeSelect enum to spf.spf and avoid
        # constructing an edge_select_func, which unlocks specialized inner loops.
        use_spf_fast_path = (
            self.edge_select_func is None and effective_select_value is None
        )

        edge_select_func = None
        if not use_spf_fast_path:
            # Build (and cache) a selector when fast path is not applicable
            if self.edge_select_func is None:
                cache_key = (self.edge_select, effective_select_value)
                edge_select_func = self._edge_selector_cache.get(cache_key)
                if edge_select_func is None:
                    edge_select_func = edge_select.edge_select_fabric(
                        edge_select=self.edge_select,
                        select_value=effective_select_value,
                        excluded_edges=None,
                        excluded_nodes=None,
                        edge_select_func=None,
                    )
                    self._edge_selector_cache[cache_key] = edge_select_func
            else:
                # Respect a user-provided selector (do not cache)
                edge_select_func = edge_select.edge_select_fabric(
                    edge_select=self.edge_select,
                    select_value=effective_select_value,
                    excluded_edges=None,
                    excluded_nodes=None,
                    edge_select_func=self.edge_select_func,
                )

        if self.path_alg == base.PathAlg.SPF:
            path_func = spf.spf
        else:
            raise ValueError(f"Unsupported path algorithm {self.path_alg}")

        # Count SPF invocations for metrics
        self._metrics_totals["spf_calls_total"] += 1.0

        if use_spf_fast_path:
            cost, pred = path_func(
                flow_graph,
                src_node=src_node,
                edge_select=self.edge_select,
                edge_select_func=None,
                multipath=self.multipath,
                excluded_edges=excluded_edges,
                excluded_nodes=excluded_nodes,
                dst_node=dst_node,
            )
        else:
            cost, pred = path_func(
                flow_graph,
                src_node=src_node,
                edge_select=self.edge_select,
                edge_select_func=edge_select_func,
                multipath=self.multipath,
                excluded_edges=excluded_edges,
                excluded_nodes=excluded_nodes,
                dst_node=dst_node,
            )

        if dst_node in pred:
            dst_cost = cost[dst_node]
            # Update best_path_cost if we found a cheaper path.
            if self.best_path_cost is None or dst_cost < self.best_path_cost:
                self.best_path_cost = dst_cost

            # Enforce maximum path cost constraints, if specified.
            if self.max_path_cost or self.max_path_cost_factor:
                max_path_cost_factor = self.max_path_cost_factor or 1.0
                max_path_cost = self.max_path_cost or float("inf")
                if dst_cost > min(
                    max_path_cost, self.best_path_cost * max_path_cost_factor
                ):
                    return None

            return PathBundle(src_node, dst_node, pred, dst_cost)

        return None

    def _create_flow(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: Hashable,
        min_flow: Optional[float] = None,
        path_bundle: Optional[PathBundle] = None,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ) -> Optional[Flow]:
        """Create a new flow and register it within the policy.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            min_flow: Minimum flow threshold for path selection.
            path_bundle: Optionally, a precomputed path bundle.
            excluded_edges: Edges to exclude during path-finding.
            excluded_nodes: Nodes to exclude during path-finding.

        Returns:
            Flow | None: Newly created flow, or None if no valid path bundle is found.
        """
        # Try last path bundle reuse for this (src,dst) if available and still valid
        if path_bundle is None:
            last_pb: Optional[PathBundle] = getattr(self, "_last_path_bundle", None)
            if (
                last_pb is not None
                and last_pb.src_node == src_node
                and last_pb.dst_node == dst_node
            ):
                # Attempt to reuse by checking that all edges exist and have remaining capacity >= min_flow
                can_reuse = True
                # Require at least MIN_FLOW to be deliverable to consider reuse
                min_required = (
                    float(min_flow) if min_flow is not None else float(base.MIN_FLOW)
                )
                edges = flow_graph.get_edges()
                # Respect exclusions if provided
                if excluded_edges and any(e in excluded_edges for e in last_pb.edges):
                    can_reuse = False
                if excluded_nodes and any(
                    n in excluded_nodes for n in getattr(last_pb, "nodes", set())
                ):
                    can_reuse = False
                for e_id in last_pb.edges:
                    if e_id not in edges:
                        can_reuse = False
                        break
                    cap = edges[e_id][3].get("capacity", 0.0)
                    flow = edges[e_id][3].get("flow", 0.0)
                    if (cap - flow) < min_required:
                        can_reuse = False
                        break
                if can_reuse:
                    path_bundle = last_pb

        path_bundle = path_bundle or self._get_path_bundle(
            flow_graph, src_node, dst_node, min_flow, excluded_edges, excluded_nodes
        )
        if not path_bundle:
            return None

        flow_index = self._build_flow_index(
            src_node, dst_node, flow_class, self._get_next_flow_id()
        )
        flow = Flow(path_bundle, flow_index)
        self.flows[flow_index] = flow
        self._metrics_totals["flows_created_total"] += 1.0
        # Cache last path bundle for potential reuse within this demand's placement session
        self._last_path_bundle = path_bundle
        return flow

    def _create_flows(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: Hashable,
        min_flow: Optional[float] = None,
    ) -> None:
        """Create the initial set of flows for a new demand.

        If static paths are defined, use them directly; otherwise, create flows via
        path-finding.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            min_flow: Minimum flow threshold for path selection.

        Raises:
            ValueError: If the static paths do not match the demand's source/destination.
        """
        if self.static_paths:
            for path_bundle in self.static_paths:
                if (
                    path_bundle.src_node == src_node
                    and path_bundle.dst_node == dst_node
                ):
                    self._create_flow(
                        flow_graph,
                        src_node,
                        dst_node,
                        flow_class,
                        min_flow,
                        path_bundle,
                    )
                else:
                    raise ValueError(
                        "Source and destination nodes of static paths do not match demand."
                    )
        else:
            for _ in range(self.min_flow_count):
                self._create_flow(flow_graph, src_node, dst_node, flow_class, min_flow)

    def _delete_flow(
        self, flow_graph: StrictMultiDiGraph, flow_index: FlowIndex
    ) -> None:
        """Delete a flow from the policy and remove it from the graph.

        Args:
            flow_graph: The network graph.
            flow_index: The key identifying the flow to delete.

        Raises:
            KeyError: If the specified flow_index does not exist.
        """
        flow = self.flows.pop(flow_index)
        flow.remove_flow(flow_graph)

    def _reoptimize_flow(
        self,
        flow_graph: StrictMultiDiGraph,
        flow_index: FlowIndex,
        headroom: float = 0.0,
    ) -> Optional[Flow]:
        """Re-optimize a flow by finding a new path that can accommodate headroom.

        If no better path is found, restore the original path.

        Args:
            flow_graph: The network graph.
            flow_index: The key identifying the flow to update.
            headroom: Additional volume to accommodate on the new path.

        Returns:
            Flow | None: Updated flow if successful; otherwise None.
        """
        flow = self.flows[flow_index]
        current_flow_volume = flow.placed_flow
        new_min_volume = current_flow_volume + headroom
        flow.remove_flow(flow_graph)

        path_bundle = self._get_path_bundle(
            flow_graph,
            flow.path_bundle.src_node,
            flow.path_bundle.dst_node,
            new_min_volume,
            flow.excluded_edges,
            flow.excluded_nodes,
        )
        # If no suitable alternative path is found or the new path is the same set of edges,
        # revert to the original path.
        if not path_bundle or path_bundle.edges == flow.path_bundle.edges:
            flow.place_flow(flow_graph, current_flow_volume, self.flow_placement)
            return None

        new_flow = Flow(
            path_bundle, flow_index, flow.excluded_edges, flow.excluded_nodes
        )
        new_flow.place_flow(flow_graph, current_flow_volume, self.flow_placement)
        self.flows[flow_index] = new_flow
        try:
            self._metrics_totals["reopt_calls_total"] += 1.0
        except Exception:
            pass
        return new_flow

    def place_demand(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: Hashable,
        volume: float,
        target_flow_volume: Optional[float] = None,
        min_flow: Optional[float] = None,
    ) -> Tuple[float, float]:
        """Place demand volume on the graph by splitting or creating flows as needed.

        Optionally re-optimize flows based on the policy configuration.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            volume: The demand volume to place.
            target_flow_volume: The target volume to aim for on each flow.
            min_flow: Minimum flow threshold for path selection.

        Returns:
            tuple[float, float]: (placed_flow, remaining_volume).

        Raises:
            RuntimeError: If an infinite loop is detected due to misconfigured flow policy
                         parameters, or if maximum iteration limit is exceeded.
        """
        # If flows exist but reference edges that no longer exist (e.g., after
        # a graph rebuild), prune them so that placement can recreate valid flows.
        if self.flows:
            edges = flow_graph.get_edges()
            invalid = [
                flow_index
                for flow_index, flow in list(self.flows.items())
                if any(
                    eid not in edges
                    for eid in getattr(flow.path_bundle, "edges", set())
                )
            ]
            for flow_index in invalid:
                # Remove from internal registry; nothing to remove from graph for stale ids
                self.flows.pop(flow_index, None)

        if not self.flows:
            self._create_flows(flow_graph, src_node, dst_node, flow_class, min_flow)

        flow_queue = deque(self.flows.values())
        target_flow_volume = target_flow_volume or volume

        # Metrics snapshot at entry
        totals_before = dict(self._metrics_totals)
        initial_request = volume

        total_placed_flow = 0.0
        consecutive_no_progress = 0
        total_iterations = 0

        # Track diminishing returns over a sliding window
        recent_placements = deque(maxlen=self.diminishing_returns_window)
        cutoff_triggered = False

        while volume >= base.MIN_FLOW and flow_queue:
            flow = flow_queue.popleft()
            placed_flow, _ = flow.place_flow(
                flow_graph, min(target_flow_volume, volume), self.flow_placement
            )
            volume -= placed_flow
            total_placed_flow += placed_flow
            total_iterations += 1
            recent_placements.append(placed_flow)
            self._metrics_totals["place_iterations_total"] += 1.0

            # Track progress to detect infinite loops in flow creation/optimization
            if placed_flow < base.MIN_FLOW:
                consecutive_no_progress += 1
                # Occasional debug to aid troubleshooting of misconfigured policies
                if consecutive_no_progress == 1 or (consecutive_no_progress % 25 == 0):
                    import logging as _logging

                    if self._logger.isEnabledFor(_logging.DEBUG):
                        self._logger.debug(
                            "place_demand no-progress: src=%s dst=%s vol_left=%.6g target=%.6g "
                            "flows=%d queue=%d iters=%d last_cost=%s edge_sel=%s placement=%s multipath=%s",
                            str(getattr(flow, "src_node", "")),
                            str(getattr(flow, "dst_node", "")),
                            float(volume),
                            float(target_flow_volume),
                            len(self.flows),
                            len(flow_queue),
                            total_iterations,
                            str(
                                getattr(
                                    getattr(flow, "path_bundle", None), "cost", None
                                )
                            ),
                            self.edge_select.name,
                            self.flow_placement.name,
                            str(self.multipath),
                        )
                if consecutive_no_progress >= self.max_no_progress_iterations:
                    # This indicates an infinite loop where flows keep being created
                    # but can't place any meaningful volume
                    raise RuntimeError(
                        f"Infinite loop detected in place_demand: "
                        f"{consecutive_no_progress} consecutive iterations with no progress. "
                        f"This typically indicates misconfigured flow policy parameters "
                        f"(e.g., non-capacity-aware edge selection with high max_flow_count)."
                    )
            else:
                consecutive_no_progress = 0  # Reset counter on progress

            # Safety net for pathological cases
            if total_iterations > self.max_total_iterations:
                raise RuntimeError(
                    f"Maximum iteration limit ({self.max_total_iterations}) exceeded in place_demand."
                )

            # Diminishing-returns cutoff: if the recent placements collectively fall
            # below a meaningful threshold, stop iterating to avoid chasing dust.
            if (
                self.diminishing_returns_enabled
                and len(recent_placements) == self.diminishing_returns_window
            ):
                recent_sum = sum(recent_placements)
                threshold = max(
                    base.MIN_FLOW,
                    self.diminishing_returns_epsilon_frac * float(initial_request),
                )
                if recent_sum < threshold:
                    # Gracefully stop iterating for this demand; leave remaining volume.
                    import logging as _logging

                    if self._logger.isEnabledFor(_logging.DEBUG):
                        self._logger.debug(
                            "place_demand cutoff: src=%s dst=%s recent_sum=%.6g threshold=%.6g "
                            "remaining=%.6g flows=%d iters=%d edge_sel=%s placement=%s multipath=%s",
                            str(src_node),
                            str(dst_node),
                            float(recent_sum),
                            float(threshold),
                            float(volume),
                            len(self.flows),
                            total_iterations,
                            self.edge_select.name,
                            self.flow_placement.name,
                            str(self.multipath),
                        )
                    cutoff_triggered = True
                    break

            # If the flow can accept more volume, attempt to create or update.
            if (
                target_flow_volume - flow.placed_flow >= base.MIN_FLOW
                and not self.static_paths
            ):
                if not self.max_flow_count or len(self.flows) < self.max_flow_count:
                    # Avoid unbounded flow creation under non-capacity-aware selection
                    # with PROPORTIONAL placement when no progress was made.
                    non_cap_selects = {
                        base.EdgeSelect.ALL_MIN_COST,
                        base.EdgeSelect.SINGLE_MIN_COST,
                    }
                    if (
                        placed_flow < base.MIN_FLOW
                        and self.flow_placement == FlowPlacement.PROPORTIONAL
                        and self.edge_select in non_cap_selects
                    ):
                        new_flow = None
                    else:
                        new_flow = self._create_flow(
                            flow_graph, src_node, dst_node, flow_class
                        )
                else:
                    new_flow = self._reoptimize_flow(
                        flow_graph, flow.flow_index, headroom=base.MIN_FLOW
                    )
                if new_flow:
                    flow_queue.append(new_flow)
                    import logging as _logging

                    if self._logger.isEnabledFor(_logging.DEBUG):
                        self._logger.debug(
                            "place_demand appended flow: total_flows=%d new_cost=%s",
                            len(self.flows),
                            str(getattr(new_flow.path_bundle, "cost", None)),
                        )

        # For EQUAL_BALANCED placement, rebalance flows to maintain equal volumes.
        if self.flow_placement == FlowPlacement.EQUAL_BALANCED and len(self.flows) > 0:
            target_flow_volume_eq = self.placed_demand / float(len(self.flows))
            # If flows are not already near balanced, rebalance them.
            if any(
                abs(target_flow_volume_eq - f.placed_flow) >= base.MIN_FLOW
                for f in self.flows.values()
            ):
                # Perform a single rebalance pass; do not recurse into rebalancing again
                prev_reopt = self.reoptimize_flows_on_each_placement
                self.reoptimize_flows_on_each_placement = False
                try:
                    total_placed_flow, excess_flow = self.rebalance_demand(
                        flow_graph,
                        src_node,
                        dst_node,
                        flow_class,
                        target_flow_volume_eq,
                    )
                    volume += excess_flow
                finally:
                    self.reoptimize_flows_on_each_placement = prev_reopt

        # Optionally re-run optimization for all flows after placement.
        if self.reoptimize_flows_on_each_placement:
            for flow in self.flows.values():
                self._reoptimize_flow(flow_graph, flow.flow_index)

        # Update last_metrics snapshot

        totals_after = self._metrics_totals
        self.last_metrics = {
            "placed": float(total_placed_flow),
            "remaining": float(volume),
            "iterations": float(total_iterations),
            "flows_created": float(
                totals_after["flows_created_total"]
                - totals_before["flows_created_total"]
            ),
            "spf_calls": float(
                totals_after["spf_calls_total"] - totals_before["spf_calls_total"]
            ),
            "reopt_calls": float(
                totals_after["reopt_calls_total"] - totals_before["reopt_calls_total"]
            ),
            "cutoff_triggered": float(1.0 if cutoff_triggered else 0.0),
            "initial_request": float(initial_request),
        }

        return total_placed_flow, volume

    def get_metrics(self) -> Dict[str, float]:
        """Return cumulative placement metrics for this policy instance.

        Returns:
            dict[str, float]: Totals including 'spf_calls_total', 'flows_created_total',
                'reopt_calls_total', and 'place_iterations_total'.
        """
        return dict(self._metrics_totals)

    def rebalance_demand(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: Hashable,
        target_flow_volume: float,
    ) -> Tuple[float, float]:
        """Rebalance demand across existing flows towards the target volume per flow.

        Achieved by removing all flows from the graph and re-placing them.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            target_flow_volume: The desired volume per flow.

        Returns:
            tuple[float, float]: Same semantics as `place_demand`.
        """
        volume = self.placed_demand
        self.remove_demand(flow_graph)
        return self.place_demand(
            flow_graph, src_node, dst_node, flow_class, volume, target_flow_volume
        )

    def remove_demand(self, flow_graph: StrictMultiDiGraph) -> None:
        """Removes all flows from the network graph without clearing internal state.
        This allows subsequent re-optimization.

        Args:
            flow_graph: The network graph.
        """
        for flow in list(self.flows.values()):
            flow.remove_flow(flow_graph)


def get_flow_policy(flow_policy_config: FlowPolicyConfig) -> FlowPolicy:
    """Create a policy instance from a configuration preset.

    Args:
        flow_policy_config: A FlowPolicyConfig enum value specifying the desired policy.

    Returns:
        FlowPolicy: Pre-configured policy instance.

    Raises:
        ValueError: If an unknown FlowPolicyConfig value is provided.
    """
    if flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_ECMP:
        # Hop-by-hop equal-cost balanced routing (similar to IP forwarding with ECMP).
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=base.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,  # Single flow from the perspective of the flow object,
            # but multipath can create parallel SPF paths.
        )
    elif flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_WCMP:
        # Hop-by-hop weighted ECMP (WCMP) over equal-cost paths (proportional split).
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=base.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_WCMP_UNLIM:
        # Traffic engineering with WCMP (proportional split) and capacity-aware selection.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=base.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_ECMP_UP_TO_256_LSP:
        # TE with up to 256 LSPs using ECMP flow placement.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=base.EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            max_flow_count=256,
            reoptimize_flows_on_each_placement=True,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_ECMP_16_LSP:
        # TE with 16 LSPs using ECMP flow placement.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=base.EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            min_flow_count=16,
            max_flow_count=16,
            reoptimize_flows_on_each_placement=True,
        )
    else:
        raise ValueError(f"Unknown flow policy config: {flow_policy_config}")
