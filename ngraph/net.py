from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from ngraph.lib import common
from ngraph.lib.max_flow import calc_max_flow
from ngraph.lib.flow_policy import FlowPolicy, FlowPolicyConfig
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
    Link represents a connection between two nodes.
    """

    node_a: NodeID
    node_z: NodeID
    metric: float
    capacity: float
    edges: List[EdgeID] = field(default_factory=list)
    link_id: LinkID = field(default=None)
    bidirectional: bool = True


class Net:
    """
    Net class represents a network.
    """

    def __init__(self):
        self.graph: MultiDiGraph = MultiDiGraph()
        self.nodes: Dict[NodeID, Node] = {}
        self.links: Dict[LinkID, Link] = {}
        self.virtlinks: Set[LinkID] = set()
        self.virtnodes: Set[NodeID] = set()
        self._next_link_id: LinkID = 0
        self._next_virtlink_id: LinkID = -1

    def _get_next_link_id(self) -> LinkID:
        next_link_id = self._next_link_id
        self._next_link_id += 1
        return next_link_id

    def _get_next_virtlink_id(self) -> LinkID:
        next_virtlink_id = self._next_virtlink_id
        self._next_virtlink_id -= 1
        return next_virtlink_id

    def add_nodes_from(self, nodes: Iterable[Node]) -> Net:
        for node in nodes:
            self.add_node(node)
        return self

    def add_links_from(self, links: Iterable[Link]) -> Net:
        for link in links:
            self.add_link(link)
        return self

    def add_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"Node {node.node_id} already exists")

        self.nodes[node.node_id] = node
        self.graph.add_node(node.node_id, flows={}, flow=0)

    def add_link(self, link: Link) -> None:
        if link.node_a not in self.nodes:
            raise ValueError(f"Node {link.node_a} not found")
        if link.node_z not in self.nodes:
            raise ValueError(f"Node {link.node_z} not found")

        link_id = self._get_next_link_id()
        link.link_id = link_id
        self.links[link_id] = link

        link.edges.append(
            self.graph.add_edge(link.node_a, link.node_z, flows={}, flow=0)
        )
        if link.bidirectional:
            link.edges.append(
                self.graph.add_edge(link.node_z, link.node_a, flows={}, flow=0)
            )

        for edge_id in link.edges:
            edge_attr = self.graph.get_edge_attr(edge_id)
            edge_attr.update(asdict(link))

    def create_virtnode(self, node_name: NodeID) -> None:
        if node_name in self.nodes:
            raise ValueError(
                f"Node {node_name} already exists. Cannot create virtual node with same name."
            )
        if node_name in self.virtnodes:
            raise ValueError(f"Virtual node {node_name} already exists.")
        self.virtnodes.add(node_name)
        self.graph.add_node(node_name, flows={}, flow=0, virtual=True)

    def create_virtlink(
        self, node_a: NodeID, node_z: NodeID, metric=0, capacity=float("inf")
    ) -> EdgeID:
        if node_a not in self.graph:
            raise ValueError(f"Node {node_a} not found")
        if node_z not in self.graph:
            raise ValueError(f"Node {node_z} not found")
        virtlink_id = self._get_next_virtlink_id()
        self.virtlinks.add(virtlink_id)
        self.graph.add_edge(
            node_a,
            node_z,
            edge_id=virtlink_id,
            virtual=True,
            metric=metric,
            capacity=capacity,
        )
        return virtlink_id

    def remove_virtnode(self, node_name: NodeID) -> None:
        if node_name not in self.virtnodes:
            raise ValueError(f"Virtual node {node_name} not found")
        adj_in = self.graph.get_adj_in()
        adj_out = self.graph.get_adj_out()
        edges_to_remove = []
        for neighbor in adj_in[node_name]:
            for edge_id in adj_in[node_name][neighbor]:
                edges_to_remove.append(edge_id)
        for neighbor in adj_out[node_name]:
            for edge_id in adj_out[node_name][neighbor]:
                edges_to_remove.append(edge_id)
        for edge_id in edges_to_remove:
            self.remove_virtlink(edge_id)
        self.virtnodes.remove(node_name)
        self.graph.remove_node(node_name)

    def remove_virtlink(self, virtlink_id: LinkID) -> None:
        if virtlink_id not in self.virtlinks:
            raise ValueError(f"Virtual link {virtlink_id} not found")
        self.virtlinks.remove(virtlink_id)
        self.graph.remove_edge_by_id(virtlink_id)

    def remove_all_virtual(self) -> None:
        for virtnode in list(self.virtnodes):
            self.remove_virtnode(virtnode)

    def max_flow(
        self,
        src_nodes: Iterable[NodeID],
        dst_nodes: Iterable[NodeID],
        shortest_path: bool = False,
        flow_placement: common.FlowPlacement = common.FlowPlacement.PROPORTIONAL,
    ) -> float:
        """
        Returns the maximum flow in the network between the given sources and destinations.
        """

        # Add virtual source and sink nodes
        virt_src = "source"
        virt_dst = "sink"
        self.create_virtnode(virt_src)
        for src_node in src_nodes:
            self.create_virtlink(virt_src, src_node)
        self.create_virtnode(virt_dst)
        for dst_node in dst_nodes:
            self.create_virtlink(dst_node, virt_dst)

        max_flow = calc_max_flow(
            self.graph, virt_src, virt_dst, flow_placement, shortest_path
        )
        self.remove_virtnode(virt_src)
        self.remove_virtnode(virt_dst)
        return max_flow

    def clear_flow_graph(self) -> None:
        common.init_flow_graph(self.graph)
