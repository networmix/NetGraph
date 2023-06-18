from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from functools import cached_property
from typing import Dict, Iterator, List, Optional, Set, Tuple

from ngraph.lib.common import (
    Cost,
    resolve_to_paths,
    edge_select_fabric,
    EdgeSelect,
)
from ngraph.lib.graph import EdgeID, MultiDiGraph, NodeID
from ngraph.lib.path import Path


class PathBundle:
    """
    PathBundle is a loopfree collection of equal-cost paths between two nodes.
    """

    def __init__(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]],
        cost: Cost,
    ):
        self.src_node: NodeID = src_node
        self.dst_node: NodeID = dst_node
        self.cost: Cost = cost
        self.pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]] = {src_node: {}}
        self.edges: Set[EdgeID] = set()
        self.edge_tuples: Set[Tuple[EdgeID]] = set()
        self.nodes: Set[NodeID] = set([src_node])
        queue = deque([dst_node])
        while queue:
            node = queue.popleft()
            self.nodes.add(node)
            for prev_node, edges_list in pred[node].items():
                self.pred.setdefault(node, {})[prev_node] = edges_list
                self.edges.update(edges_list)
                self.edge_tuples.add(tuple(edges_list))
                if prev_node != src_node:
                    queue.append(prev_node)

    def __lt__(self, other: PathBundle):
        return self.cost < other.cost

    def __eq__(self, other: PathBundle):
        return (
            self.src_node == other.src_node
            and self.dst_node == other.dst_node
            and self.cost == other.cost
            and self.edges == other.edges
        )

    def __hash__(self) -> int:
        return hash(
            (self.src_node, self.dst_node, self.cost, tuple(sorted(self.edges)))
        )

    def __repr__(self) -> str:
        return f"PathBundle({self.src_node}, {self.dst_node}, {self.pred}, {self.cost})"

    def add(self, other: PathBundle) -> PathBundle:
        if self.dst_node != other.src_node:
            raise ValueError("PathBundle dst_node != other.src_node")
        new_pred = {}
        for dst_node in self.pred:
            new_pred.setdefault(dst_node, {})
            for src_node in self.pred[dst_node]:
                new_pred[dst_node][src_node] = list(self.pred[dst_node][src_node])
        for dst_node in other.pred:
            new_pred.setdefault(dst_node, {})
            for src_node in other.pred[dst_node]:
                new_pred[dst_node][src_node] = list(other.pred[dst_node][src_node])
        return PathBundle(
            self.src_node, other.dst_node, new_pred, self.cost + other.cost
        )

    @classmethod
    def from_path(
        cls,
        path: Path,
        resolve_edges: bool = False,
        graph: Optional[MultiDiGraph] = None,
        edge_select: Optional[EdgeSelect] = None,
        cost_attr: str = "metric",
        capacity_attr: str = "capacity",
    ) -> PathBundle:
        edge_selector = (
            edge_select_fabric(
                edge_select, cost_attr=cost_attr, capacity_attr=capacity_attr
            )
            if resolve_edges
            else None
        )
        src_node = path[0][0]
        dst_node = path[-1][0]
        pred = {src_node: {}}
        cost = 0
        for node_edges_1, node_edges_2 in zip(path[:-1], path[1:]):
            a_node = node_edges_1[0]
            z_node = node_edges_2[0]
            edge_tuple = node_edges_1[1]
            pred.setdefault(z_node, {})[a_node] = list(edge_tuple)
            if resolve_edges:
                min_cost, edge_list = edge_selector(
                    graph, a_node, z_node, graph[a_node][z_node]
                )
                cost += min_cost
                pred[z_node][a_node] = edge_list
        if resolve_edges:
            return PathBundle(src_node, dst_node, pred, cost)
        return PathBundle(src_node, dst_node, pred, path.cost)

    def resolve_to_paths(self, split_parallel_edges: bool = False) -> Iterator[Path]:
        for path_tuple in resolve_to_paths(
            self.src_node,
            self.dst_node,
            self.pred,
            split_parallel_edges,
        ):
            yield Path(path_tuple, self.cost)

    def contains(self, other: PathBundle) -> bool:
        return self.edges.issuperset(other.edges)

    def is_subset_of(self, other: PathBundle) -> bool:
        return self.edges.issubset(other.edges)

    def is_disjoint_from(self, other: PathBundle) -> bool:
        return self.edges.isdisjoint(other.edges)

    def get_sub_path_bundle(
        self,
        new_dst_node: NodeID,
        graph: MultiDiGraph,
        cost_attr: str = "metric",
    ) -> PathBundle:
        if new_dst_node not in self.pred:
            raise ValueError(f"{new_dst_node} not in self.pred")

        edges_dict = graph.get_edges()
        new_pred = {self.src_node: {}}
        new_cost = 0
        queue = deque([(0, new_dst_node)])
        while queue:
            cost_to_node, node = queue.popleft()
            for prev_node, edges_list in self.pred[node].items():
                new_pred.setdefault(node, {})[prev_node] = edges_list
                cost_to_prev_node = cost_to_node + min(
                    edges_dict[edge_id][-1][cost_attr] for edge_id in edges_list
                )
                if prev_node != self.src_node:
                    queue.append((cost_to_prev_node, prev_node))
                else:
                    new_cost = cost_to_prev_node
        return PathBundle(self.src_node, new_dst_node, new_pred, new_cost)
