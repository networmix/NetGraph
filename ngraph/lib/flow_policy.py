from __future__ import annotations

import copy
from collections import deque
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ngraph.lib.flow import Flow, FlowIndex
from ngraph.lib.algorithms import spf, base, edge_select
from ngraph.lib.algorithms.place_flow import FlowPlacement
from ngraph.lib.graph import AttrDict, NodeID, EdgeID, StrictMultiDiGraph
from ngraph.lib.path_bundle import PathBundle


class FlowPolicyConfig(IntEnum):
    """
    Enumerates supported flow policy configurations.
    """

    SHORTEST_PATHS_ECMP = 1
    SHORTEST_PATHS_UCMP = 2
    TE_UCMP_UNLIM = 3
    TE_ECMP_UP_TO_256_LSP = 4
    TE_ECMP_16_LSP = 5


class FlowPolicy:
    """
    Manages the placement and management of flows (demands) on a network graph.

    A FlowPolicy converts a demand into one or more Flow objects subject to
    capacity constraints and user-specified configurations such as path
    selection algorithms and flow placement methods.
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
                [StrictMultiDiGraph, NodeID, NodeID, Dict[EdgeID, AttrDict]],
                Tuple[base.Cost, List[EdgeID]],
            ]
        ] = None,
        edge_select_value: Optional[Any] = None,
        reoptimize_flows_on_each_placement: bool = False,
    ) -> None:
        """
        Initializes a FlowPolicy instance.

        Args:
            path_alg: The path algorithm to use (e.g., SPF).
            flow_placement: Strategy for placing flows (e.g., EQUAL_BALANCED, PROPORTIONAL).
            edge_select: Mode for edge selection (e.g., ALL_MIN_COST).
            multipath: Whether to allow multiple parallel paths at the SPF stage.
            min_flow_count: Minimum number of flows to create for a demand.
            max_flow_count: Maximum number of flows allowable for a demand.
            max_path_cost: Absolute cost limit for allowable paths.
            max_path_cost_factor: Relative cost factor limit (multiplying the best path cost).
            static_paths: Predefined paths to force flows onto, if provided.
            edge_select_func: Custom function for edge selection, if needed.
            edge_select_value: Additional parameter for certain edge selection strategies.
            reoptimize_flows_on_each_placement: If True, re-run path optimization after every placement.

        Raises:
            ValueError: If static_paths length does not match max_flow_count,
                        or if EQUAL_BALANCED placement is used without a
                        specified max_flow_count.
        """
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

        # Dictionary to track all flows by their FlowIndex.
        self.flows: Dict[Tuple, Flow] = {}

        # Track the best path cost found to enforce maximum path cost constraints.
        self.best_path_cost: Optional[base.Cost] = None

        # Internal flow ID counter.
        self._next_flow_id: int = 0

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
        """
        Creates and returns a deep copy of this FlowPolicy, including all flows.

        Returns:
            A new FlowPolicy object that is a deep copy of the current instance.
        """
        return copy.deepcopy(self)

    @property
    def flow_count(self) -> int:
        """
        Returns the number of flows currently tracked by the policy.
        """
        return len(self.flows)

    @property
    def placed_demand(self) -> float:
        """
        Returns the sum of all placed flow volumes across flows.
        """
        return sum(flow.placed_flow for flow in self.flows.values())

    def _get_next_flow_id(self) -> int:
        """
        Retrieves and increments the internal flow ID counter.

        Returns:
            The next available integer flow ID.
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
        Constructs a FlowIndex tuple used as a dictionary key to track flows.

        Args:
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            flow_id: Unique identifier for this flow.

        Returns:
            A FlowIndex instance containing the specified parameters.
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
        """
        Finds a path or set of paths from src_node to dst_node, optionally excluding
        certain edges or nodes.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            min_flow: Minimum flow threshold for selection.
            excluded_edges: Set of edges to exclude.
            excluded_nodes: Set of nodes to exclude.

        Returns:
            A valid PathBundle if one is found and it satisfies cost constraints;
            otherwise, None.

        Raises:
            ValueError: If the selected path algorithm is not supported.
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
        flow_class: int,
        min_flow: Optional[float] = None,
        path_bundle: Optional[PathBundle] = None,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ) -> Optional[Flow]:
        """
        Creates a new Flow and registers it within the policy.

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
            The newly created Flow, or None if no valid path bundle is found.
        """
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
        return flow

    def _create_flows(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: int,
        min_flow: Optional[float] = None,
    ) -> None:
        """
        Creates the initial set of flows for a new demand.

        If static paths are defined, they are used directly; otherwise, flows
        are created via path-finding.

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
        """
        Deletes a flow from the policy and removes it from the network graph.

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
        """
        Re-optimizes an existing flow by finding a new path that can accommodate
        additional volume headroom. If no better path is found, the original path is restored.

        Args:
            flow_graph: The network graph.
            flow_index: The key identifying the flow to re-optimize.
            headroom: Additional volume to accommodate on the new path.

        Returns:
            The updated Flow if re-optimization is successful; otherwise, None.
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
        return new_flow

    def place_demand(
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        flow_class: int,
        volume: float,
        target_flow_volume: Optional[float] = None,
        min_flow: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Places the given demand volume on the network graph by splitting or creating
        flows as needed. Optionally re-optimizes flows based on the policy configuration.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            volume: The demand volume to place.
            target_flow_volume: The target volume to aim for on each flow.
            min_flow: Minimum flow threshold for path selection.

        Returns:
            A tuple (placed_flow, remaining_volume) where placed_flow is the total
            volume successfully placed and remaining_volume is any unplaced volume.

        Raises:
            RuntimeError: If an infinite loop is detected (safety net).
        """
        if not self.flows:
            self._create_flows(flow_graph, src_node, dst_node, flow_class, min_flow)

        flow_queue = deque(self.flows.values())
        target_flow_volume = target_flow_volume or volume

        total_placed_flow = 0.0
        iteration_count = 0

        while volume >= base.MIN_FLOW and flow_queue:
            flow = flow_queue.popleft()
            placed_flow, _ = flow.place_flow(
                flow_graph, min(target_flow_volume, volume), self.flow_placement
            )
            volume -= placed_flow
            total_placed_flow += placed_flow

            # If the flow can accept more volume, attempt to create or re-optimize.
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

            iteration_count += 1
            if iteration_count > 10000:
                raise RuntimeError("Infinite loop detected in place_demand.")

        # For EQUAL_BALANCED placement, rebalance flows to maintain equal volumes.
        if self.flow_placement == FlowPlacement.EQUAL_BALANCED and len(self.flows) > 0:
            target_flow_volume = self.placed_demand / float(len(self.flows))
            # If flows are not already near balanced, rebalance them.
            if any(
                abs(target_flow_volume - f.placed_flow) >= base.MIN_FLOW
                for f in self.flows.values()
            ):
                total_placed_flow, excess_flow = self.rebalance_demand(
                    flow_graph, src_node, dst_node, flow_class, target_flow_volume
                )
                volume += excess_flow

        # Optionally re-run optimization for all flows after placement.
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
        Rebalances the demand across existing flows so that their volumes are closer
        to the target_flow_volume. This is achieved by removing all flows from
        the network graph and re-placing them.

        Args:
            flow_graph: The network graph.
            src_node: The source node identifier.
            dst_node: The destination node identifier.
            flow_class: The flow class or type identifier.
            target_flow_volume: The desired volume per flow.

        Returns:
            A tuple (placed_flow, remaining_volume) similar to place_demand().
        """
        volume = self.placed_demand
        self.remove_demand(flow_graph)
        return self.place_demand(
            flow_graph, src_node, dst_node, flow_class, volume, target_flow_volume
        )

    def remove_demand(self, flow_graph: StrictMultiDiGraph) -> None:
        """
        Removes all flows from the network graph without clearing internal state.
        This allows subsequent re-optimization.

        Args:
            flow_graph: The network graph.
        """
        for flow in list(self.flows.values()):
            flow.remove_flow(flow_graph)


def get_flow_policy(flow_policy_config: FlowPolicyConfig) -> FlowPolicy:
    """
    Factory method to create and return a FlowPolicy instance based on the provided configuration.

    Args:
        flow_policy_config: A FlowPolicyConfig enum value specifying the desired policy.

    Returns:
        A pre-configured FlowPolicy instance corresponding to the specified configuration.

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
    elif flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_UCMP:
        # Hop-by-hop with proportional flow placement (e.g., per-hop UCMP).
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=base.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_UCMP_UNLIM:
        # "Ideal" TE with multiple MPLS LSPs and UCMP flow placement.
        return FlowPolicy(
            path_alg=base.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=base.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
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
