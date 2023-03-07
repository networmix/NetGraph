from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from ngraph.lib import common
from ngraph.lib.flow import FlowPolicy, FlowPolicyConfig
from ngraph.lib.graph import EdgeID, MultiDiGraph, NodeID
from ngraph.lib.demand import Demand


LinkID = int


@dataclass
class Node:
    """
    Node represents a node in a network.
    """

    node_id: NodeID


@dataclass
class Link:
    """
    Link represents a bidirectional connection between two nodes.
    """

    node_a: NodeID
    node_z: NodeID
    metric: float
    capacity: float
    edges: List[EdgeID] = field(default_factory=list)
    link_id: LinkID = field(default=None)


class Net:
    """
    Net class represents a network.
    """

    def __init__(self):
        self.graph: MultiDiGraph = MultiDiGraph()
        self.nodes: Dict[NodeID, Node] = {}
        self.links: Dict[LinkID, Link] = {}
        self._next_link_id: LinkID = 0

    def _get_next_link_id(self) -> LinkID:
        next_link_id = self._next_link_id
        self._next_link_id += 1
        return next_link_id

    def add_nodes_from(self, nodes: Iterable[Node]) -> Net:
        for node in nodes:
            self.nodes[node.node_id] = node
        self.sync_graph()
        return self

    def add_links_from(self, links: Iterable[Link]) -> Net:
        for link in links:
            if link.node_a not in self.nodes:
                raise ValueError(f"Node {link.node_a} not found")
            if link.node_z not in self.nodes:
                raise ValueError(f"Node {link.node_z} not found")

            link_id = self._get_next_link_id()
            link.link_id = link_id
            self.links[link_id] = link
        self.sync_graph()
        return self

    def sync_graph(self) -> None:
        for node_id, node in self.nodes.items():
            if node_id not in self.graph:
                self.graph.add_node(node_id, **asdict(node))
            else:
                node_attr = self.graph.get_node_attr(node_id)
                node_attr.update(asdict(node))

        for _, link in self.links.items():
            if not link.edges:
                edge1_id = self.graph.add_edge(
                    link.node_a,
                    link.node_z,
                )
                edge_attr = self.graph.get_edge_attr(edge1_id)
                edge_attr.update(asdict(link))
                edge2_id = self.graph.add_edge(
                    link.node_z,
                    link.node_a,
                )
                link.edges = [edge1_id, edge2_id]

            edge1_id, edge2_id = link.edges
            edge_attr = self.graph.get_edge_attr(edge1_id)
            edge_attr.update(asdict(link))
            edge_attr = self.graph.get_edge_attr(edge2_id)
            edge_attr.update(asdict(link))

        common.init_flow_graph(self.graph)
