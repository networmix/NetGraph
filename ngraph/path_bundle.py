from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Set, Tuple

from ngraph.algorithms.common import Cost, PathTuple, resolve_to_paths
from ngraph.graph import DstNodeID, EdgeID, MultiDiGraph, NodeID, SrcNodeID


@dataclass
class Path:
    path_tuple: PathTuple
    cost: Cost
    edges: Set[EdgeID] = field(init=False, default_factory=set, repr=False)
    nodes: Set[NodeID] = field(init=False, default_factory=set, repr=False)
    edge_tuples: Set[Tuple[EdgeID]] = field(init=False, default_factory=set, repr=False)

    def __post_init__(self):
        for node_edges in self.path_tuple:
            self.nodes.add(node_edges[0])
            self.edges.update(node_edges[1])
            self.edge_tuples.add(tuple(node_edges[1]))

    def __getitem__(self, idx: int) -> Tuple:
        return self.path_tuple[idx]

    def __iter__(self) -> Iterator:
        return iter(self.path_tuple)

    def __lt__(self, other: Path):
        return self.cost < other.cost

    def __eq__(self, other: Path):
        return self.path_tuple == other.path_tuple

    def __hash__(self) -> int:
        return hash((self.path_tuple, self.cost))


class PathBundle:
    def __init__(
        self,
        src_node: SrcNodeID,
        dst_node: DstNodeID,
        pred: Dict[DstNodeID, Dict[SrcNodeID, List[EdgeID]]],
        cost: Cost,
    ):
        self.src_node: SrcNodeID = src_node
        self.dst_node: DstNodeID = dst_node
        self.cost: Optional[Cost] = cost
        self.pred: Dict[DstNodeID, Dict[SrcNodeID, List[EdgeID]]] = {src_node: {}}
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
        return (self.src_node, self.dst_node, self.cost, tuple(sorted(self.edges))) == (
            other.src_node,
            other.dst_node,
            other.cost,
            tuple(sorted(other.edges)),
        )

    def __hash__(self) -> int:
        return hash(
            (self.src_node, self.dst_node, self.cost, tuple(sorted(self.edges)))
        )

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

    def contains(self, other: PathBundle) -> bool:
        return self.edges.issuperset(other.edges)
