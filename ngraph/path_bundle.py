from collections import deque
from dataclasses import dataclass, field
from email.generator import Generator
from typing import Dict, Hashable, Optional, Set, Tuple, Union

from ngraph.algorithms.common import resolve_to_paths


@dataclass
class Path:
    path_tuple: Tuple
    cost: Optional[Union[int, float]] = None
    edges: Set = field(init=False, default_factory=set)
    nodes: Set = field(init=False, default_factory=set)

    def __post_init__(self):
        for node_edges in self.path_tuple:
            self.nodes.add(node_edges[0])
            self.edges.update(node_edges[1])


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

    def resolve_to_paths(self, resolve_parallel_edges: bool = False) -> Generator:
        for path_tuple in resolve_to_paths(
            self.src_node,
            self.dst_node,
            self.pred,
            resolve_parallel_edges=resolve_parallel_edges,
        ):
            yield Path(path_tuple, self.cost)
