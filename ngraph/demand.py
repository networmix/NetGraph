from __future__ import annotations
from itertools import repeat
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    List,
    Optional,
    Set,
    Tuple,
    Generator,
    NamedTuple,
)
from ngraph.algorithms.calc_cap import calc_graph_cap
from ngraph.algorithms.place_flow import FlowPlacement, place_flow_on_graph

from ngraph.graph import MultiDiGraph
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


class FlowPolicy:
    def __init__(
        self,
        path_alg: PathAlg,
        flow_placement: FlowPlacement,
        edge_select: common.EdgeSelect,
        path_bundle_list: Optional[List[PathBundle]] = None,
    ):
        self.path_alg: PathAlg = path_alg
        self.flow_placement: FlowPlacement = flow_placement
        self.edge_select: common.EdgeSelect = edge_select
        self.path_bundle_list: Optional[List[PathBundle]] = path_bundle_list

    def get_path_bundle(
        self,
        flow_graph: MultiDiGraph,
        src_node: Hashable,
        dst_node: Hashable,
    ) -> Optional[PathBundle]:
        if self.path_bundle_list:
            while True:
                for path_bundle in self.path_bundle_list:
                    yield path_bundle
        else:
            while True:
                edge_select_func = common.edge_select_fabric(
                    edge_select=self.edge_select
                )
                if self.path_alg == PathAlg.BFS:
                    path_func = bfs.bfs
                elif self.path_alg == PathAlg.SPF:
                    path_func = spf.spf
                _, pred = path_func(
                    flow_graph, src_node=src_node, edge_select_func=edge_select_func
                )
                if dst_node in pred:
                    yield PathBundle(src_node, dst_node, pred)
                return


class Demand:
    def __init__(
        self,
        src_node: Hashable,
        dst_node: Hashable,
        volume: float,
        flow_policy: FlowPolicy,
        label: Optional[Any] = None,
    ):
        self.src_node: Hashable = src_node
        self.dst_node: Hashable = dst_node
        self.volume: float = volume
        self.flow_policy = flow_policy
        self.label: Optional[Any] = label

        self.flow_index: Tuple = (self.src_node, self.dst_node, label)
        self.placed_flow: float = 0
        self.nodes: Set = set()
        self.edges: Set = set()

    def place(
        self,
        flow_graph: MultiDiGraph,
        max_fraction: float = 1,
    ) -> Tuple[float, float]:
        if max_fraction > 0:
            to_place = min(self.volume - self.placed_flow, self.volume * max_fraction)
        else:
            to_place = self.volume if self.volume == float("inf") else 0

        placed_flow = 0
        while path_bundle := next(
            self.flow_policy.get_path_bundle(flow_graph, self.src_node, self.dst_node),
            None,
        ):
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
            self.placed_flow += placed_flow

            if to_place < MIN_FLOW or flow_placement_meta.placed_flow < MIN_FLOW:
                break
        return placed_flow, to_place


FLOW_POLICY_MAP = {
    FlowPolicyConfig.SHORTEST_PATHS_BALANCED: FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
        edge_select=common.EdgeSelect.ALL_MIN_COST,
    ),
    FlowPolicyConfig.SHORTEST_PATHS_PROPORTIONAL: FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=common.EdgeSelect.ALL_MIN_COST,
    ),
    FlowPolicyConfig.ALL_PATHS_PROPORTIONAL: FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=common.EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
    ),
}
