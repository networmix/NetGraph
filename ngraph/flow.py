from __future__ import annotations
from enum import IntEnum
from collections import deque
from typing import Any, Dict, Hashable, Iterator, List, Optional, Set, Tuple, NamedTuple
from ngraph.algorithms.place_flow import (
    FlowPlacement,
    place_flow_on_graph,
    remove_flow_from_graph,
)
from ngraph.graph import DstNodeID, EdgeID, MultiDiGraph, NodeID, SrcNodeID
from ngraph.algorithms import spf, common
from ngraph.path_bundle import PathBundle


class FlowPolicyConfig(IntEnum):
    SHORTEST_PATHS_ECMP = 1
    SHORTEST_PATHS_UCMP = 2
    TE_UCMP_UNLIM = 3
    TE_ECMP_UP_TO_256_LSP = 4
    TE_ECMP_16_LSP = 5


class FlowIndex(NamedTuple):
    src_node: SrcNodeID
    dst_node: DstNodeID
    label: Hashable
    flow_id: int


class FlowPolicy:
    """
    FlowPolicy realizes a demand through one or more Flows.
    """

    def __init__(
        self,
        path_alg: common.PathAlg,
        flow_placement: FlowPlacement,
        edge_select: common.EdgeSelect,
        multipath: bool,
        min_flow_count: int = 1,
        max_flow_count: Optional[int] = None,
        edge_filter: Optional[common.EdgeFilter] = None,
        filter_value: Optional[Any] = None,
        max_path_cost: Optional[common.Cost] = None,
        max_path_cost_factor: Optional[float] = None,
        static_paths: Optional[List[PathBundle]] = None,
    ):
        self.path_alg: common.PathAlg = path_alg
        self.flow_placement: FlowPlacement = flow_placement
        self.edge_select: common.EdgeSelect = edge_select
        self.multipath: bool = multipath
        self.min_flow_count: int = min_flow_count
        self.max_flow_count: Optional[int] = max_flow_count
        self.edge_filter: Optional[common.EdgeFilter] = edge_filter
        self.filter_value: Optional[Any] = filter_value
        self.max_path_cost: Optional[common.Cost] = max_path_cost
        self.max_path_cost_factor: Optional[float] = max_path_cost_factor
        self.static_paths: Optional[List[PathBundle]] = static_paths

        self.flows: Dict[Tuple, Flow] = {}
        self.best_path_cost: Optional[common.Cost] = None
        self._next_flow_id: int = 0

        if static_paths:
            if max_flow_count is not None and len(static_paths) != max_flow_count:
                raise ValueError(
                    "if set, max_flow_count must be equal to the number of static paths"
                )
            self.max_flow_count = len(static_paths)
        if flow_placement == FlowPlacement.EQUAL_BALANCED:
            if self.max_flow_count is None:
                raise ValueError(
                    "max_flow_count must be set for EQUAL_BALANCED placement"
                )

    @property
    def flow_count(self) -> int:
        return len(self.flows)

    @property
    def placed_demand(self) -> float:
        return sum(flow.placed_flow for flow in self.flows.values())

    def _get_next_flow_id(self) -> int:
        next_flow_id = self._next_flow_id
        self._next_flow_id += 1
        return next_flow_id

    def _build_flow_index(
        self, src_node: SrcNodeID, dst_node: DstNodeID, label: Hashable, flow_id: int
    ) -> Tuple:
        return FlowIndex(src_node, dst_node, label, flow_id)

    def _get_path_bundle(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        min_flow: Optional[float] = None,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ) -> Optional[PathBundle]:

        edge_select_func = common.edge_select_fabric(
            edge_select=self.edge_select,
            select_value=min_flow,
            edge_filter=self.edge_filter,
            filter_value=self.filter_value,
            excluded_edges=excluded_edges,
            excluded_nodes=excluded_nodes,
        )

        if self.path_alg == common.PathAlg.SPF:
            path_func = spf.spf
        else:
            raise ValueError(f"Unsupported path algorithm {self.path_alg}")

        cost, pred = path_func(
            flow_graph,
            src_node=src_node,
            edge_select_func=edge_select_func,
            multipath=self.multipath,
        )

        if dst_node in pred:
            dst_cost = cost[dst_node]
            if self.best_path_cost is None:
                self.best_path_cost = dst_cost
            if self.max_path_cost or self.max_path_cost_factor:
                max_path_cost_factor = self.max_path_cost_factor or 1
                max_path_cost = self.max_path_cost or float("inf")
                if dst_cost > min(
                    max_path_cost, self.best_path_cost * max_path_cost_factor
                ):
                    return
            return PathBundle(src_node, dst_node, pred, dst_cost)

    def _create_flow(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        label: Hashable,
        min_flow: Optional[float] = None,
        path_bundle: Optional[PathBundle] = None,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ) -> Optional[Flow]:
        path_bundle = path_bundle or self._get_path_bundle(
            flow_graph,
            src_node,
            dst_node,
            min_flow,
            excluded_edges,
            excluded_nodes,
        )
        if not path_bundle:
            return
        flow_index = self._build_flow_index(
            src_node, dst_node, label, self._get_next_flow_id()
        )
        flow = Flow(path_bundle, flow_index)
        self.flows[flow_index] = flow
        return flow

    def _create_flows(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        label: Hashable,
        min_flow: Optional[float] = None,
    ) -> None:
        if self.static_paths:
            for path_bundle in self.static_paths:
                if (
                    path_bundle.src_node == src_node
                    and path_bundle.dst_node == dst_node
                ):
                    self._create_flow(
                        flow_graph, src_node, dst_node, label, min_flow, path_bundle
                    )
                else:
                    raise ValueError(
                        "Source and destination nodes of static paths do not match demand"
                    )
        else:
            for _ in range(self.min_flow_count):
                self._create_flow(flow_graph, src_node, dst_node, label, min_flow)

    def _delete_flow(self, flow_graph: MultiDiGraph, flow_index: FlowIndex) -> None:
        flow = self.flows.pop(flow_index)
        flow.remove_flow(flow_graph)

    def _reoptimize_flow(
        self, flow_graph: MultiDiGraph, flow_index: FlowIndex, headroom: float = 0
    ) -> Optional[Flow]:
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
        if not path_bundle or path_bundle == flow.path_bundle:
            # Could not find a path with enough capacity, so we restore the old flow
            flow.place_flow(flow_graph, flow_volume, self.flow_placement)
            return
        new_flow = Flow(
            path_bundle, flow_index, flow.excluded_edges, flow.excluded_nodes
        )
        new_flow.place_flow(flow_graph, flow_volume, self.flow_placement)
        self.flows[flow_index] = new_flow
        return new_flow

    def place_demand(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        label: Hashable,
        volume: float,
        target_flow_volume: Optional[float] = None,
        min_flow: Optional[float] = None,
    ) -> Tuple:
        if not self.flows:
            self._create_flows(flow_graph, src_node, dst_node, label, min_flow)

        flow_queue = deque(self.flows.values())
        target_flow_volume = target_flow_volume or volume

        total_placed_flow = 0
        c = 0
        while volume >= common.MIN_FLOW and flow_queue:
            flow = flow_queue.popleft()
            placed_flow, _ = flow.place_flow(
                flow_graph, min(target_flow_volume, volume), self.flow_placement
            )
            volume -= placed_flow
            total_placed_flow += placed_flow
            if (
                target_flow_volume - flow.placed_flow >= common.MIN_FLOW
                and not self.static_paths
            ):
                if not self.max_flow_count or len(self.flows) < self.max_flow_count:
                    # create new flow if it is possible
                    new_flow = self._create_flow(flow_graph, src_node, dst_node, label)
                else:
                    # try to reoptimize the current flow
                    new_flow = self._reoptimize_flow(
                        flow_graph, flow.flow_index, headroom=common.MIN_FLOW
                    )
                if new_flow:
                    # either a new flow was created or an existing flow was reoptimized
                    flow_queue.append(new_flow)
            c += 1
            if c > 10000:
                raise RuntimeError("Infinite loop detected")
        if self.flow_placement == FlowPlacement.EQUAL_BALANCED:
            # Rebalance flows if they are not equal
            target_flow_volume = self.placed_demand / len(self.flows)

            if any(
                abs(target_flow_volume - flow.placed_flow) >= common.MIN_FLOW
                for flow in self.flows.values()
            ):
                total_placed_flow, excess_flow = self.rebalance_demand(
                    flow_graph, src_node, dst_node, label, target_flow_volume
                )
                volume += excess_flow
        return total_placed_flow, volume

    def rebalance_demand(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        label: Hashable,
        target_flow_volume: float,
    ) -> Tuple:
        # Rebalance demand across flows to make them close to target
        volume = self.placed_demand
        self.remove_demand(flow_graph)
        return self.place_demand(
            flow_graph,
            src_node,
            dst_node,
            label,
            volume,
            target_flow_volume,
        )

    def remove_demand(
        self,
        flow_graph: MultiDiGraph,
    ) -> None:
        for flow in list(self.flows.values()):
            flow.remove_flow(flow_graph)


class Flow:
    """
    Flow is a fraction of a demand applied along a particular PathBundle in a graph.
    """

    def __init__(
        self,
        path_bundle: PathBundle,
        flow_index: Hashable,
        excluded_edges: Optional[Set[EdgeID]] = None,
        excluded_nodes: Optional[Set[NodeID]] = None,
    ):
        self.path_bundle: PathBundle = path_bundle
        self.flow_index: Hashable = flow_index
        self.excluded_edges: Set[EdgeID] = excluded_edges or set()
        self.excluded_nodes: Set[NodeID] = excluded_nodes or set()
        self.src_node: SrcNodeID = path_bundle.src_node
        self.dst_node: DstNodeID = path_bundle.dst_node
        self.placed_flow: float = 0

    def __str__(self) -> str:
        return f"Flow(flow_index={self.flow_index}, placed_flow={self.placed_flow})"

    def place_flow(
        self,
        flow_graph: MultiDiGraph,
        to_place: float,
        flow_placement: FlowPlacement,
    ) -> Tuple[float, float]:

        placed_flow = 0
        if to_place >= common.MIN_FLOW:
            flow_placement_meta = place_flow_on_graph(
                flow_graph,
                self.src_node,
                self.dst_node,
                self.path_bundle.pred,
                to_place,
                self.flow_index,
                flow_placement,
            )
            placed_flow += flow_placement_meta.placed_flow
            to_place = flow_placement_meta.remaining_flow
            self.placed_flow += placed_flow
        return placed_flow, to_place

    def remove_flow(self, flow_graph: MultiDiGraph) -> None:
        remove_flow_from_graph(flow_graph, self.flow_index)
        self.placed_flow = 0


def get_flow_policy(flow_policy_config: FlowPolicyConfig) -> FlowPolicy:
    if flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_ECMP:
        """Hop-by-hop equal-cost balanced, e.g. IP forwarding with ECMP."""
        return FlowPolicy(
            path_alg=common.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=common.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,  # single flow following shortest paths
        )
    elif flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_UCMP:
        """Hop-by-hop with proportional flow placement, e.g. IP forwarding with per-hop UCMP."""
        return FlowPolicy(
            path_alg=common.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=common.EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,  # single flow following shortest paths
        )
    elif flow_policy_config == FlowPolicyConfig.TE_UCMP_UNLIM:
        """'Ideal' TE, e.g. multiple MPLS LSPs with UCMP flow placement."""
        return FlowPolicy(
            path_alg=common.PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=common.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_ECMP_UP_TO_256_LSP:
        """TE with 16 LSPs, e.g. 16 parallel MPLS LSPs with ECMP flow placement."""
        return FlowPolicy(
            path_alg=common.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=common.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
            max_flow_count=256,
        )
    elif flow_policy_config == FlowPolicyConfig.TE_ECMP_16_LSP:
        """TE with 16 LSPs, e.g. 16 parallel MPLS LSPs with ECMP flow placement."""
        return FlowPolicy(
            path_alg=common.PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=common.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
            min_flow_count=16,
            max_flow_count=16,
        )
    else:
        raise ValueError(f"Unknown flow policy config: {flow_policy_config}")
