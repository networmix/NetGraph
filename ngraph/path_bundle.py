from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Hashable, Iterator, Optional, Set, Tuple, Union

from ngraph.algorithms.common import resolve_to_paths
from ngraph.graph import MultiDiGraph


@dataclass
class Path:
    path_tuple: Tuple
    cost: Optional[Union[int, float]] = None
    edges: Set = field(init=False, default_factory=set, repr=False)
    nodes: Set = field(init=False, default_factory=set, repr=False)

    def __post_init__(self):
        for node_edges in self.path_tuple:
            self.nodes.add(node_edges[0])
            self.edges.update(node_edges[1])

    def __getitem__(self, idx: int) -> Tuple:
        return self.path_tuple[idx]

    def __iter__(self) -> Iterator:
        return iter(self.path_tuple)


class PathBundle:
    def __init__(
        self,
        src_node: Hashable,
        dst_node: Hashable,
        pred: Dict,
        cost: Optional[float] = None,
    ):
        self.src_node: Hashable = src_node
        self.dst_node: Hashable = dst_node
        self.cost: Optional[float] = cost
        self.pred: Dict = {src_node: {}}
        self.edges: Set = set()
        self.nodes: Set = set([src_node])

        queue = deque([dst_node])
        while queue:
            node = queue.popleft()
            self.nodes.add(node)
            for prev_node, edges_list in pred[node].items():
                self.pred.setdefault(node, {})[prev_node] = edges_list
                self.edges.update(edges_list)
                if prev_node != src_node:
                    queue.append(prev_node)

    @classmethod
    def from_path(
        cls,
        path: Path,
    ) -> PathBundle:

        pred = {path[0][0]: {}}
        for node_edges_1, node_edges_2 in zip(path[1:], path[:-1]):
            pred.setdefault(node_edges_1[0], {})[node_edges_2[0]] = list(
                node_edges_2[1]
            )
        return PathBundle(path[0][0], path[-1][0], pred, path.cost)

    def resolve_to_paths(self, split_parallel_edges: bool = False) -> Iterator[Path]:
        for path_tuple in resolve_to_paths(
            self.src_node,
            self.dst_node,
            self.pred,
            split_parallel_edges,
        ):
            yield Path(path_tuple, self.cost)

    def resolve_edges(self, graph: MultiDiGraph) -> None:
        new_pred = {}
        for dst_node in self.pred:
            new_pred.setdefault(dst_node, {})
            for src_node in self.pred[dst_node]:
                new_pred[dst_node][src_node] = list(graph[src_node][dst_node].keys())
        self.pred = new_pred
