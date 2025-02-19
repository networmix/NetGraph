from __future__ import annotations
from enum import IntEnum
from collections import deque
from typing import Any, Callable, Dict, Optional, Set, Tuple

from ngraph.lib.flow import Flow, FlowIndex
from ngraph.lib.algorithms.place_flow import FlowPlacement
from ngraph.lib.graph import (
    AttrDict,
    NodeID,
    EdgeID,
    StrictMultiDiGraph,
)
from ngraph.lib.algorithms import spf, base, edge_select
from ngraph.lib.path_bundle import PathBundle


class FlowPolicyConfig(IntEnum):
    """Enumerates supported flow policy configurations."""

    SHORTEST_PATHS_ECMP = 1
    SHORTEST_PATHS_UCMP = 2
    TE_UCMP_UNLIM = 3
    TE_ECMP_UP_TO_256_LSP = 4
    TE_ECMP_16_LSP = 5


class FlowPolicy:
    """
    Encapsulates logic for placing and managing flows (demands) on a network graph.

    A FlowPolicy converts a demand into one or more Flow objects, subject
    to capacity constraints and user-specified configuration (e.g., path
    selection algorithm, flow placement method, etc.).
    """

    def __init__(
        self,
        path_alg: base.PathAlg,
        flow_placement: FlowPlacement,
        edge_select: base.EdgeSelect,
        multipath: bool,
        min_flow_count: int = 1,
        max_flow_count: int | None = None,
        max_path_cost: base.Cost | None = None,
        max_path_cost_factor: float | None = None,
        static_paths: list[PathBundle] | None = None,
        edge_select_func: (
            Callable[
                [StrictMultiDiGraph, NodeID, NodeID, Dict[EdgeID, AttrDict]],
                Tuple[base.Cost, list[EdgeID]],
            ]
            | None
        ) = None,
        edge_select_value: Any | None = None,
        reoptimize_flows_on_each_placement: bool = False,
    ) -> None:
        """
        Initializes a FlowPolicy.

        Args:
            path_alg: The path algorithm to use (e.g., SPF).
            flow_placement: The flow placement strategy (e.g., EQUAL_BALANCED, PROPORTIONAL).
            edge_select: The edge selection mode (e.g., ALL_MIN_COST).
            multipath: Whether to allow multiple parallel paths at the SPF stage.
            min_flow_count: The minimum number of flows to create for a demand.
            max_flow_count: The maximum number of flows allowable for a demand (if any).
            max_path_cost: Absolute limit on allowable path cost.
            max_path_cost_factor: Relative factor limit (multiplying the best path cost).
            static_paths: If provided, flows will be forced onto these static paths.
            edge_select_func: Custom function for edge selection, if needed.
            edge_select_value: Additional parameter used by certain edge selection strategies.
            reoptimize_flows_on_each_placement: If True, flows are re-run through the
                path-finding logic on every placement to ensure a fresh solution.

        Raises:
            ValueError: If max_flow_count is set but does not match the number of static_paths.
            ValueError: If flow_placement=EQUAL_BALANCED is used without a max_flow_count.
        """
        self.path_alg: base.PathAlg = path_alg
        self.flow_placement: FlowPlacement = flow_placement
        self.edge_select: base.EdgeSelect = edge_select
        self.multipath: bool = multipath
        self.min_flow_count: int = min_flow_count
        self.max_flow_count: int | None = max_flow_count
        self.max_path_cost: base.Cost | None = max_path_cost
        self.max_path_cost_factor: float | None = max_path_cost_factor
        self.static_paths: list[PathBundle] | None = static_paths
        self.edge_select_func = edge_select_func
        self.edge_select_value: Any | None = edge_select_value
        self.reoptimize_flows_on_each_placement: bool = (
            reoptimize_flows_on_each_placement
        )

        # All flows tracked by this policy.
        self.flows: Dict[Tuple, Flow] = {}

        # Track the best path cost found so far to enforce max_path_cost_factor.
        self.best_path_cost: base.Cost | None = None

        # Internal flow ID counter.
        self._next_flow_id: int = 0

        # Validate static_paths vs. max_flow_count constraints
        if static_paths:
            if max_flow_count is not None and len(static_paths) != max_flow_count:
                raise ValueError(
                    "If set, max_flow_count must be equal to the number of static paths."
                )
            self.max_flow_count = len(static_paths)
        if flow_placement == FlowPlacement.EQUAL_BALANCED:
            if self.max_flow_count is None:
                raise ValueError(
                    "max_flow_count must be set for EQUAL_BALANCED placement."
                )

    @property
    def flow_count(self) -> int:
        """Number of flows currently tracked by this policy."""
        return len(self.flows)

    @property
    def placed_demand(self) -> float:
        """Sum of all placed flow volumes across all flows."""
        return sum(flow.placed_flow for flow in self.flows.values())

    def _get_next_flow_id(self) -> int:
        """
        Retrieves and increments the internal flow ID counter.

        Returns:
            An integer ID for the next new Flow.
        """
        next_flow_id = self._next_flow_id
        self._next_flow_id += 1
        return next_flow_id

    def _build_flow_index(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: int,
        flow_id: int,
    ) -> FlowIndex:
        """
        Builds a FlowIndex tuple, used as a dictionary key to track flows.

        Args:
            src_node: The source node.
            dst_node: The destination node.
            flow_class: The flow class or type ID.
            flow_id: Unique ID for this flow.

        Returns:
            A FlowIndex object containing these parameters.
        """
        return FlowIndex(src_node, dst_node, flow_class, flow_id)

    def _get_path_bundle(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        min_flow: float | None = None,
        excluded_edges: Set[EdgeID] | None = None,
        excluded_nodes: Set[NodeID] | None = None,
    ) -> PathBundle | None:
        """
        Finds a path (or set of paths) from src_node to dst_node, optionally
        excluding certain edges or nodes.

        Args:
            flow_graph: The underlying network graph.
            src_node: The source node.
            dst_node: The destination node.
            min_flow: A minimum flow threshold used by certain edge selection modes.
            excluded_edges: A set of edges to exclude from path-finding.
            excluded_nodes: A set of nodes to exclude from path-finding.

        Returns:
            A PathBundle if a path is found and passes cost constraints; otherwise None.

        Raises:
            ValueError: If the selected path_alg is not supported.
        """
        edge_select_func = edge_select.edge_select_fabric(
            edge_select=self.edge_select,
            select_value=min_flow or self.edge_select_value,
            excluded_edges=excluded_edges,
            excluded_nodes=excluded_nodes,
            edge_select_func=self.edge_select_func,
        )

        if self.path_alg == base.PathAlg.SPF:
            path_func = spf.spf
        else:
            raise ValueError(f"Unsupported path algorithm {self.path_alg}")

        cost, pred = path_func(
            flow_graph,
            src_node=src_node,
            edge_select_func=edge_select_func,
            multipath=self.multipath,
            excluded_edges=excluded_edges,
            excluded_nodes=excluded_nodes,
        )

        if dst_node in pred:
            dst_cost = cost[dst_node]
            if self.best_path_cost is None:
                self.best_path_cost = dst_cost

            # Enforce maximum path cost constraints
            if self.max_path_cost or self.max_path_cost_factor:
                max_path_cost_factor = self.max_path_cost_factor or 1
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
        flow_class: int,
        min_flow: float | None = None,
        path_bundle: PathBundle | None = None,
        excluded_edges: Set[EdgeID] | None = None,
        excluded_nodes: Set[NodeID] | None = None,
    ) -> Flow | None:
        """
        Creates a new Flow and registers it in self.flows.

        Args:
            flow_graph: The underlying network graph.
            src_node: The source node.
            dst_node: The destination node.
            flow_class: The flow class or type ID.
            min_flow: A minimum flow threshold used by some path-finding modes.
            path_bundle: Optionally, a precomputed path bundle to use.
            excluded_edges: Edges excluded from path-finding.
            excluded_nodes: Nodes excluded from path-finding.

        Returns:
            The newly created Flow, or None if no path bundle could be found.
        """
        path_bundle = path_bundle or self._get_path_bundle(
            flow_graph,
            src_node,
            dst_node,
            min_flow,
            excluded_edges,
            excluded_nodes,
        )
        if not path_bundle:
            return None

        flow_index = self._build_flow_index(
            src_node, dst_node, flow_class, self._get_next_flow_id()
        )
        flow = Flow(path_bundle, flow_index)
        self.flows[flow_index] = flow
        return flow

    def _create_flows(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: int,
        min_flow: float | None = None,
    ) -> None:
        """
        Creates the initial set of flows for a new demand. If static_paths are defined,
        they are used directly; otherwise, the minimum flow count is created via
        path-finding.

        Args:
            flow_graph: The underlying network graph.
            src_node: The source node.
            dst_node: The destination node.
            flow_class: The flow class or type ID.
            min_flow: A minimum flow threshold used by some path-finding modes.

        Raises:
            ValueError: If static_paths do not match the demanded source/destination.
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
        """
        Deletes a flow from the policy and removes it from the graph.

        Args:
            flow_graph: The underlying network graph.
            flow_index: The key identifying the flow to delete.

        Raises:
            KeyError: If the flow_index does not exist in self.flows.
        """
        flow = self.flows.pop(flow_index)
        flow.remove_flow(flow_graph)

    def _reoptimize_flow(
        self,
        flow_graph: StrictMultiDiGraph,
        flow_index: FlowIndex,
        headroom: float = 0,
    ) -> Flow | None:
        """
        Removes and re-finds a path for an existing flow with additional volume headroom.

        If no better path is found, reverts to the old path.

        Args:
            flow_graph: The underlying network graph.
            flow_index: The key identifying the flow to re-optimize.
            headroom: Additional volume to accommodate on the new path.

        Returns:
            The updated Flow if re-optimization was successful; otherwise None.
        """
        flow = self.flows[flow_index]
        flow_volume = flow.placed_flow
        new_min_volume = flow_volume + headroom
        flow.remove_flow(flow_graph)

        path_bundle = self._get_path_bundle(
            flow_graph,
            flow.path_bundle.src_node,
            flow.path_bundle.dst_node,
            new_min_volume,
            flow.excluded_edges,
            flow.excluded_nodes,
        )
        # If no suitable alternative path found, revert
        if not path_bundle or path_bundle.edges == flow.path_bundle.edges:
            flow.place_flow(flow_graph, flow_volume, self.flow_placement)
            return None

        new_flow = Flow(
            path_bundle, flow_index, flow.excluded_edges, flow.excluded_nodes
        )
        new_flow.place_flow(flow_graph, flow_volume, self.flow_placement)
        self.flows[flow_index] = new_flow
        return new_flow

    def place_demand(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: int,
        volume: float,
        target_flow_volume: float | None = None,
        min_flow: float | None = None,
    ) -> Tuple[float, float]:
        """
        Places the given demand volume on the graph, splitting or creating flows
        as needed. May also re-optimize flows if policy configuration allows.

        Args:
            flow_graph: The underlying network graph.
            src_node: The source node.
            dst_node: The destination node.
            flow_class: The flow class or type ID.
            volume: The volume of demand to place.
            target_flow_volume: A target flow volume to aim for each flow.
            min_flow: A minimum flow threshold for path selection.

        Returns:
            A tuple of (placed_flow, remaining_volume). placed_flow is the total
            successfully placed across all flows, and remaining_volume is any
            unplaced remainder.
        """
        if not self.flows:
            self._create_flows(flow_graph, src_node, dst_node, flow_class, min_flow)

        flow_queue = deque(self.flows.values())
        target_flow_volume = target_flow_volume or volume

        total_placed_flow = 0
        c = 0

        # Guard against infinite loops; the logic should eventually exhaust either
        # volume or flows, but we use c>10000 as a safety check.
        while volume >= base.MIN_FLOW and flow_queue:
            flow = flow_queue.popleft()
            placed_flow, _ = flow.place_flow(
                flow_graph, min(target_flow_volume, volume), self.flow_placement
            )
            volume -= placed_flow
            total_placed_flow += placed_flow

            # If the flow can still hold more volume, we attempt to create or re-optimize
            if (
                target_flow_volume - flow.placed_flow >= base.MIN_FLOW
                and not self.static_paths
            ):
                if not self.max_flow_count or len(self.flows) < self.max_flow_count:
                    new_flow = self._create_flow(
                        flow_graph, src_node, dst_node, flow_class
                    )
                else:
                    new_flow = self._reoptimize_flow(
                        flow_graph, flow.flow_index, headroom=base.MIN_FLOW
                    )
                if new_flow:
                    flow_queue.append(new_flow)

            c += 1
            if c > 10000:
                # Potential weak spot: artificial break condition in place of more robust loop logic
                raise RuntimeError("Infinite loop detected")

        # For EQUAL_BALANCED, ensure flows are rebalanced to maintain equal volumes.
        if self.flow_placement == FlowPlacement.EQUAL_BALANCED:
            target_flow_volume = self.placed_demand / len(self.flows)
            if any(
                abs(target_flow_volume - flow.placed_flow) >= base.MIN_FLOW
                for flow in self.flows.values()
            ):
                total_placed_flow, excess_flow = self.rebalance_demand(
                    flow_graph, src_node, dst_node, flow_class, target_flow_volume
                )
                volume += excess_flow

        # If configured, re-run optimization for all flows after placement
        if self.reoptimize_flows_on_each_placement:
            for flow in self.flows.values():
                self._reoptimize_flow(flow_graph, flow.flow_index)

        return total_placed_flow, volume

    def rebalance_demand(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: int,
        target_flow_volume: float,
    ) -> Tuple[float, float]:
        """
        Rebalances the demand across existing flows to make their volumes
        closer to the target_flow_volume. Implementation removes all flows
        and re-places the demand.

        Args:
            flow_graph: The underlying network graph.
            src_node: The source node.
            dst_node: The destination node.
            flow_class: The flow class or type ID.
            target_flow_volume: The flow volume to aim for each flow (if possible).

        Returns:
            A tuple of (placed_flow, remaining_volume) similar to place_demand().
        """
        volume = self.placed_demand
        self.remove_demand(flow_graph)
        return self.place_demand(
            flow_graph,
            src_node,
            dst_node,
            flow_class,
            volume,
            target_flow_volume,
        )

    def remove_demand(
        self,
        flow_graph: StrictMultiDiGraph,
    ) -> None:
        """
        Zeroes out all flows from this policy in the underlying graph but does not
        remove them from the policy's internal state. This allows for re-optimization.

        Args:
            flow_graph: The underlying network graph.
        """
        for flow in list(self.flows.values()):
            flow.remove_flow(flow_graph)


def get_flow_policy(flow_policy_config: FlowPolicyConfig) -> FlowPolicy:
    """
    Factory method to return a FlowPolicy instance based on a FlowPolicyConfig enum.

    Args:
        flow_policy_config: One of the FlowPolicyConfig enum values.

    Returns:
        A FlowPolicy pre-configured for the specified policy approach.

    Raises:
        ValueError: If an unknown FlowPolicyConfig is provided.
    """
    if flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_ECMP:
        # Hop-by-hop equal-cost balanced, e.g. IP forwarding with ECMP.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=base.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,  # single flow following shortest paths
        )
    elif flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_UCMP:
        # Hop-by-hop with proportional flow placement, e.g. IP forwarding with per-hop UCMP.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=base.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,  # single flow following shortest paths
        )
    elif flow_policy_config == FlowPolicyConfig.TE_UCMP_UNLIM:
        # "Ideal" TE, e.g. multiple MPLS LSPs with UCMP flow placement.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=base.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_ECMP_UP_TO_256_LSP:
        # TE with up to 256 LSPs with ECMP flow placement.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=base.EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            max_flow_count=256,
            reoptimize_flows_on_each_placement=True,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_ECMP_16_LSP:
        # TE with 16 LSPs, e.g. 16 parallel MPLS LSPs with ECMP flow placement.
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
