from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional, NamedTuple, Hashable
import concurrent.futures


from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.common import init_flow_graph
from ngraph.lib.max_flow import calc_max_flow


class LinkID(NamedTuple):
    src_node: Hashable
    dst_node: Hashable
    unique_id: Hashable


class Node:
    def __init__(self, node_id: str, node_type: str = "simple", **attributes: Dict):
        self.node_id: str = node_id
        self.node_type: str = node_type
        self.attributes: Dict[str, Any] = {
            "node_id": node_id,
            "node_type": node_type,
            "plane_ids": [],
            "total_link_capacity": 0,
            "non_transit": False,
            "transit_only": False,  # no local sinks/sources
        }
        self.update_attributes(**attributes)
        self.sub_nodes: Dict[str, "Node"] = {}  # Used if node_type is 'composite'
        self.sub_links: Dict[str, "Link"] = {}  # Used if node_type is 'composite'

    def add_sub_node(self, sub_node_id: str, **attributes: Any):
        # Logic to add a sub-node to a composite node
        ...

    def add_sub_link(
        self, sub_link_id: str, sub_node1: str, sub_node2: str, **attributes: Any
    ):
        # Logic to add a sub-link to a composite node
        ...

    def update_attributes(self, **attributes: Any):
        """
        Update the attributes of the node.
        """
        self.attributes.update(attributes)


class Link:
    def __init__(
        self,
        node1: str,
        node2: str,
        link_id: Optional[LinkID] = None,
        **attributes: Dict,
    ):
        self.link_id: str = (
            LinkID(node1, node2, str(uuid.uuid4())) if link_id is None else link_id
        )
        self.node1: str = node1
        self.node2: str = node2
        self.attributes: Dict[str, Any] = {
            "link_id": self.link_id,
            "node1": node1,
            "node2": node2,
            "plane_ids": [],
            "capacity": 0,
            "metric": 0,
        }
        self.update_attributes(**attributes)

    def update_attributes(self, **attributes: Any):
        """
        Update the attributes of the link.
        """
        self.attributes.update(attributes)


class Network:
    def __init__(self):
        self.planes: Dict[str, MultiDiGraph] = {}  # Key is plane_id
        self.nodes: Dict[str, Node] = {}  # Key is unique node_id
        self.links: Dict[str, Link] = {}  # Key is unique link_id

    @staticmethod
    def generate_edge_id(from_node: str, to_node: str, link_id: LinkID) -> str:
        """
        Generate a unique edge ID for a link between two nodes.
        """
        return LinkID(from_node, to_node, link_id[2])

    def add_plane(self, plane_id: str):
        self.planes[plane_id] = init_flow_graph(MultiDiGraph())

    def add_node(
        self,
        node_id: str,
        plane_ids: Optional[List[str]] = None,
        node_type: str = "simple",
        **attributes: Any,
    ) -> str:
        new_node = Node(node_id, node_type, **attributes)
        self.nodes[new_node.node_id] = new_node

        if plane_ids is None:
            plane_ids = self.planes.keys()

        for plane_id in plane_ids:
            self.planes[plane_id].add_node(new_node.node_id, **attributes)
            new_node.attributes["plane_ids"].append(plane_id)
        return new_node.node_id

    def add_link(
        self,
        node1: str,
        node2: str,
        plane_ids: Optional[List[str]] = None,
        **attributes: Any,
    ) -> str:
        new_link = Link(node1, node2, **attributes)
        self.links[new_link.link_id] = new_link

        if plane_ids is None:
            plane_ids = self.planes.keys()

        for plane_id in plane_ids:
            self.planes[plane_id].add_edge(
                node1,
                node2,
                edge_id=self.generate_edge_id(node1, node2, new_link.link_id),
                capacity=new_link.attributes["capacity"] / len(plane_ids),
                metric=new_link.attributes["metric"],
            )
            self.planes[plane_id].add_edge(
                node2,
                node1,
                edge_id=self.generate_edge_id(node2, node1, new_link.link_id),
                capacity=new_link.attributes["capacity"] / len(plane_ids),
                metric=new_link.attributes["metric"],
            )
            new_link.attributes["plane_ids"].append(plane_id)

        # Update the total link capacity of the nodes
        self.nodes[node1].attributes["total_link_capacity"] += new_link.attributes[
            "capacity"
        ]
        self.nodes[node2].attributes["total_link_capacity"] += new_link.attributes[
            "capacity"
        ]
        return new_link.link_id

    @staticmethod
    def plane_max_flow(plane_id, plane_graph, src_node, dst_nodes) -> Optional[float]:
        """
        Calculate the maximum flow between src and dst for a single plane.
        There can be multiple dst nodes, they all are attached to the same virtual sink node.
        """
        if src_node in plane_graph:
            for dst_node in dst_nodes:
                if dst_node in plane_graph:
                    # add a pseudo node to the graph to act as the sink for the max flow calculation
                    plane_graph.add_edge(
                        dst_node,
                        "sink",
                        edge_id=-1,
                        capacity=2**32,
                        metric=0,
                        flow=0,
                        flows={},
                    )
            if "sink" in plane_graph:
                return calc_max_flow(plane_graph, src_node, "sink")

    def calc_max_flow(
        self, src_nodes: List[str], dst_nodes: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate the maximum flow between each of the src nodes and all of the dst nodes.
        All the dst nodes are attached to the same virtual sink node.
        Runs the calculation in parallel for all planes and src nodes.
        """
        with concurrent.futures.ProcessPoolExecutor() as executor:
            future_to_plane_source = {}
            for plane_id in self.planes:
                for src_node in src_nodes:
                    future_to_plane_source[
                        executor.submit(
                            self.plane_max_flow,
                            plane_id,
                            self.planes[plane_id],
                            src_node,
                            dst_nodes,
                        )
                    ] = (plane_id, src_node, dst_nodes)

            results = {}
            for future in concurrent.futures.as_completed(future_to_plane_source):
                plane_id, src_node, dst_nodes = future_to_plane_source[future]
                results.setdefault(src_node, {})
                results[src_node].setdefault(tuple(dst_nodes), {})
                results[src_node][tuple(dst_nodes)][plane_id] = future.result()
        return results
