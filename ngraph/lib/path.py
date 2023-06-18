from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from functools import cached_property
from typing import Dict, Iterator, List, Optional, Set, Tuple

from ngraph.lib.common import Cost, PathTuple
from ngraph.lib.graph import EdgeID, MultiDiGraph, NodeID


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
            self.edge_tuples.add(node_edges[1])

    def __getitem__(self, idx: int) -> Tuple:
        return self.path_tuple[idx]

    def __iter__(self) -> Iterator:
        return iter(self.path_tuple)

    def __lt__(self, other: Path):
        return self.cost < other.cost

    def __eq__(self, other: Path):
        return self.path_tuple == other.path_tuple and self.cost == other.cost

    def __hash__(self) -> int:
        return hash((self.path_tuple, self.cost))

    def __repr__(self) -> str:
        return f"Path({self.path_tuple}, {self.cost})"

    @cached_property
    def edges_seq(self) -> Tuple[Tuple[EdgeID]]:
        return tuple(edge_tuple for _, edge_tuple in self.path_tuple[:-1])

    @cached_property
    def nodes_seq(self) -> Tuple[NodeID]:
        return tuple(node for node, _ in self.path_tuple)

    def get_sub_path(
        self, dst_node: NodeID, graph: MultiDiGraph, cost_attr: str = "metric"
    ) -> Path:
        edges_dict = graph.get_edges()
        new_path_tuple = []
        new_cost = 0
        for node_edge_tuple in self.path_tuple:
            new_path_tuple.append(node_edge_tuple)
            new_cost += min(
                edges_dict[edge_id][-1][cost_attr] for edge_id in node_edge_tuple[1]
            )
            if node_edge_tuple[0] == dst_node:
                break
        return Path(new_path_tuple, new_cost)
