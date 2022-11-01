from __future__ import annotations
from enum import IntEnum
from typing import (
    Any,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)
from ngraph.algorithms.place_flow import FlowPlacement, place_flow_on_graph
from ngraph.graph import DstNodeID, EdgeID, MultiDiGraph, NodeID, SrcNodeID
from ngraph.algorithms import spf, bfs, common
from ngraph.path_bundle import PathBundle


MIN_FLOW = 2 ** (-12)


class PathAlg(IntEnum):
    """
    Types of path finding algorithms
    """

    SPF = 1
    BFS = 2


class FlowPolicyConfig(IntEnum):
    SHORTEST_PATHS_BALANCED = 1
    SHORTEST_PATHS_PROPORTIONAL = 2
    ALL_PATHS_PROPORTIONAL = 3
    LSP_16_BALANCED = 4


class FlowPolicy:
    def __init__(
        self,
        path_alg: PathAlg,
        flow_placement: FlowPlacement,
        edge_select: common.EdgeSelect,
        multipath: bool,
        path_bundle_limit: int = 0,
        edge_filter: Optional[common.EdgeFilter] = None,
        filter_value: Optional[Any] = None,
    ):
        self.path_alg: PathAlg = path_alg
        self.flow_placement: FlowPlacement = flow_placement
        self.edge_select: common.EdgeSelect = edge_select
        self.multipath: bool = multipath
        self.path_bundle_limit: int = path_bundle_limit
        self.edge_filter: Optional[common.EdgeFilter] = edge_filter
        self.filter_value: Optional[Any] = filter_value
        self.path_bundle_count: int = 0

    def get_path_bundle(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        min_flow: Optional[float] = None,
    ) -> Optional[PathBundle]:
        if self.edge_filter:
            flow_graph = flow_graph.filter(
                edge_filter=common.edge_filter_fabric(
                    edge_filter=self.edge_filter,
                    filter_value=self.filter_value,
                )
            )
        if min_flow:
            if self.edge_select not in [
                common.EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
                common.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
                common.EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            ]:
                raise RuntimeError(
                    "min_flow can be used only with capacity-aware edge selectors"
                )
            edge_select_func = common.edge_select_fabric(
                edge_select=self.edge_select, select_value=min_flow
            )
        else:
            edge_select_func = common.edge_select_fabric(edge_select=self.edge_select)
        if self.path_alg == PathAlg.BFS:
            path_func = bfs.bfs
        elif self.path_alg == PathAlg.SPF:
            path_func = spf.spf
        cost, pred = path_func(
            flow_graph,
            src_node=src_node,
            edge_select_func=edge_select_func,
            multipath=self.multipath,
        )
        if dst_node in pred:
            return PathBundle(src_node, dst_node, pred, cost[dst_node])

    def get_path_bundle_iter(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        min_flow: Optional[float] = None,
    ) -> Optional[Iterator[PathBundle]]:
        while True:
            if (
                self.path_bundle_limit
                and self.path_bundle_count >= self.path_bundle_limit
            ) or not (
                path_bundle := self.get_path_bundle(
                    flow_graph, src_node, dst_node, min_flow
                )
            ):
                return
            self.path_bundle_count += 1
            yield path_bundle

    def get_all_path_bundles(
        self,
        flow_graph: MultiDiGraph,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        min_flow: Optional[float] = None,
    ) -> List[PathBundle]:
        exclude_edges = set()
        path_bundle_list = []
        path_bundle_count = 0
        while True:
            if (
                self.path_bundle_limit and path_bundle_count >= self.path_bundle_limit
            ) or not (
                path_bundle := self.get_path_bundle(
                    flow_graph, src_node, dst_node, min_flow
                )
            ):
                return path_bundle_list
            path_bundle_list.append(path_bundle)
            path_bundle_count += 1
            exclude_edges.update(path_bundle.edges)
            flow_graph = flow_graph.filter(
                edge_filter=lambda edge_id, _: edge_id not in exclude_edges
            )


class Demand:
    def __init__(
        self,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        volume: float,
        flow_policy: Optional[FlowPolicy] = None,
        label: Optional[Any] = None,
    ):
        self.src_node: SrcNodeID = src_node
        self.dst_node: DstNodeID = dst_node
        self.volume: float = volume
        self.flow_policy = flow_policy
        self.label: Optional[Any] = label

        self.flow_index: Tuple = (self.src_node, self.dst_node, label)
        self.placed_flow: float = 0
        self.nodes: Set[NodeID] = set()
        self.edges: Set[EdgeID] = set()

    def __repr__(self) -> str:
        return f"Demand(src_node={self.src_node}, dst_node={self.dst_node}, volume={self.volume}, label={self.label}, placed_flow={self.placed_flow})"

    def place(
        self,
        flow_graph: MultiDiGraph,
        max_fraction: float = 1,
        atomic: bool = False,
    ) -> Tuple[float, float]:
        if not self.flow_policy:
            raise RuntimeError("flow_policy is not set")

        if max_fraction > 0:
            to_place = min(self.volume - self.placed_flow, self.volume * max_fraction)
        else:
            to_place = self.volume if self.volume == float("inf") else 0
        min_flow = to_place if atomic else None
        placed_flow = 0
        while (
            path_bundle := next(
                self.flow_policy.get_path_bundle_iter(
                    flow_graph, self.src_node, self.dst_node, min_flow=min_flow
                ),
                None,
            )
        ) and to_place >= MIN_FLOW:
            flow_placement_meta = place_flow_on_graph(
                flow_graph,
                self.src_node,
                self.dst_node,
                path_bundle.pred,
                to_place,
                self.flow_index,
                flow_placement=self.flow_policy.flow_placement,
            )
            placed_flow += flow_placement_meta.placed_flow
            to_place = flow_placement_meta.remaining_flow
            self.nodes.update(flow_placement_meta.nodes)
            self.edges.update(flow_placement_meta.edges)

            if to_place < MIN_FLOW or flow_placement_meta.placed_flow < MIN_FLOW:
                break
        self.placed_flow += placed_flow
        return placed_flow, to_place

    def place_path_bundle(
        self,
        flow_graph: MultiDiGraph,
        path_bundle: PathBundle,
        flow_placement: FlowPlacement,
        max_fraction: float = 1,
    ) -> Tuple[float, float]:
        if max_fraction > 0:
            to_place = min(self.volume - self.placed_flow, self.volume * max_fraction)
        else:
            to_place = self.volume if self.volume == float("inf") else 0

        placed_flow = 0
        if to_place >= MIN_FLOW:
            flow_placement_meta = place_flow_on_graph(
                flow_graph,
                self.src_node,
                self.dst_node,
                path_bundle.pred,
                to_place,
                self.flow_index,
                flow_placement,
            )
            placed_flow += flow_placement_meta.placed_flow
            to_place = flow_placement_meta.remaining_flow
            self.nodes.update(flow_placement_meta.nodes)
            self.edges.update(flow_placement_meta.edges)
        self.placed_flow += placed_flow
        return placed_flow, to_place


# TODO: Replace with fabric to avoid accidential object re-use
FLOW_POLICY_MAP = {
    FlowPolicyConfig.SHORTEST_PATHS_BALANCED: FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
        edge_select=common.EdgeSelect.ALL_MIN_COST,
        multipath=True,
    ),
    FlowPolicyConfig.SHORTEST_PATHS_PROPORTIONAL: FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=common.EdgeSelect.ALL_MIN_COST,
        multipath=True,
    ),
    FlowPolicyConfig.ALL_PATHS_PROPORTIONAL: FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=common.EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
        multipath=True,
    ),
    # FlowPolicyConfig.LSP_16_BALANCED: FlowPolicy(
    #     path_alg=PathAlg.SPF,
    #     flow_placement=FlowPlacement.EQUAL_BALANCED,
    #     edge_select=common.EdgeSelect.SINGLE_MIN_COST,
    #     multipath=False,
    #     path_bundle_limit=16,
    # ),
}
