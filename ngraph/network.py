from __future__ import annotations

import uuid
import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.max_flow import calc_max_flow
from ngraph.lib.algorithms.base import FlowPlacement


def new_base64_uuid() -> str:
    """
    Generates a Base64-encoded UUID without padding (22 characters).

    Returns:
        str: A 22-character base64 URL-safe string.
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


@dataclass(slots=True)
class Node:
    """
    Represents a node in the network.

    Each node is uniquely identified by its name, which is used as the key
    in the Network's node dictionary.

    Attributes:
        name (str): The unique name of the node.
        attrs (Dict[str, Any]): Optional extra metadata. For example:
            {
                "type": "node",          # auto-tagged on add_node
                "coords": [lat, lon],    # user-provided
                "region": "west_coast"   # user-provided
            }
    """

    name: str
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Link:
    """
    Represents a link connecting two nodes in the network.

    The 'source' and 'target' fields reference node names. A unique link ID
    is auto-generated from source, target, and a random Base64-encoded UUID,
    allowing multiple distinct links between the same pair of nodes.

    Attributes:
        source (str): Name of the source node.
        target (str): Name of the target node.
        capacity (float): Link capacity (default 1.0).
        cost (float): Link cost (default 1.0).
        attrs (Dict[str, Any]): Optional extra metadata. For example:
            {
                "type": "link",         # auto-tagged on add_link
                "distance_km": 1500,    # user-provided
            }
        id (str): Auto-generated unique link identifier, e.g. "SEA|DEN|abc123..."
    """

    source: str
    target: str
    capacity: float = 1.0
    cost: float = 1.0
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """
        Combines source, target, and a random UUID to generate the link's ID.
        """
        self.id = f"{self.source}|{self.target}|{new_base64_uuid()}"


@dataclass(slots=True)
class Network:
    """
    A container for network nodes and links.

    Attributes:
        nodes (Dict[str, Node]): Mapping node_name -> Node object.
        links (Dict[str, Link]): Mapping link_id -> Link object.
        attrs (Dict[str, Any]): Optional metadata about the network.
    """

    nodes: Dict[str, Node] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """
        Adds a node to the network (keyed by node.name).

        Auto-tags the node with node.attrs["type"] = "node" if not set.

        Args:
            node (Node): The node to add.

        Raises:
            ValueError: If a node with the same name already exists.
        """
        node.attrs.setdefault("type", "node")
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """
        Adds a link to the network (keyed by the link's auto-generated ID).

        Auto-tags the link with link.attrs["type"] = "link" if not set.

        Args:
            link (Link): The link to add.

        Raises:
            ValueError: If source or target node is missing from the network.
        """
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        link.attrs.setdefault("type", "link")
        self.links[link.id] = link

    def to_strict_multidigraph(self, add_reverse: bool = True) -> StrictMultiDiGraph:
        """
        Creates a StrictMultiDiGraph representation of this Network.

        Args:
            add_reverse (bool): If True, adds a reverse edge for each link (default True).

        Returns:
            StrictMultiDiGraph: A directed multigraph representation of the network.
        """
        graph = StrictMultiDiGraph()

        # Add nodes
        for node_name, node in self.nodes.items():
            graph.add_node(node_name, **node.attrs)

        # Add edges
        for link_id, link in self.links.items():
            # Forward edge
            graph.add_edge(
                link.source,
                link.target,
                key=link.id,
                capacity=link.capacity,
                cost=link.cost,
                **link.attrs,
            )
            # Reverse edge (if requested)
            if add_reverse:
                reverse_id = f"{link.id}_rev"
                graph.add_edge(
                    link.target,
                    link.source,
                    key=reverse_id,
                    capacity=link.capacity,
                    cost=link.cost,
                    **link.attrs,
                )

        return graph

    def select_nodes_by_path(self, path: str) -> List[Node]:
        """
        Returns nodes matching a path-based search.

        1) Returns nodes whose name is exactly 'path' or starts with 'path/'.
        2) If none found, tries names starting with 'path-'.
        3) If still none, returns nodes whose names start with 'path' (partial match).

        Args:
            path (str): The path/prefix to search.

        Returns:
            List[Node]: A list of matching Node objects.

        Examples:
            path="SEA/clos_instance/spine" might match
            "SEA/clos_instance/spine/myspine-1".
            path="S" might match "S1", "S2" (partial match fallback).
        """
        # 1) Exact or slash-based
        result = [
            n
            for n in self.nodes.values()
            if n.name == path or n.name.startswith(f"{path}/")
        ]
        if result:
            return result

        # 2) Dash-based
        result = [n for n in self.nodes.values() if n.name.startswith(f"{path}-")]
        if result:
            return result

        # 3) Partial fallback
        return [
            n for n in self.nodes.values() if n.name.startswith(path) and n.name != path
        ]

    def max_flow(
        self,
        source_path: str,
        sink_path: str,
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> float:
        """
        Computes the maximum flow between selected source and sink nodes.

        Selects source nodes matching 'source_path' and sink nodes matching 'sink_path'.
        Attaches a pseudo-node 'source' connecting to each source node with infinite
        capacity edges, and similarly a pseudo-node 'sink' from each sink node. Then
        calls calc_max_flow on the resulting graph.

        Args:
            source_path (str): Path/prefix to select source nodes.
            sink_path (str): Path/prefix to select sink nodes.
            shortest_path (bool): If True, uses only the shortest paths (default False).
            flow_placement (FlowPlacement): Load balancing across parallel edges.

        Returns:
            float: The maximum flow found from source to sink.

        Raises:
            ValueError: If no nodes match source_path or sink_path.
        """
        # 1) Select source and sink nodes
        sources = self.select_nodes_by_path(source_path)
        sinks = self.select_nodes_by_path(sink_path)

        if not sources:
            raise ValueError(f"No source nodes found matching path '{source_path}'.")
        if not sinks:
            raise ValueError(f"No sink nodes found matching path '{sink_path}'.")

        # 2) Build the graph
        graph = self.to_strict_multidigraph()

        # 3) Add pseudo-nodes for multi-source / multi-sink flow
        graph.add_node("source")
        graph.add_node("sink")

        for src_node in sources:
            graph.add_edge("source", src_node.name, capacity=float("inf"), cost=0)
        for sink_node in sinks:
            graph.add_edge(sink_node.name, "sink", capacity=float("inf"), cost=0)

        # 4) Calculate max flow
        return calc_max_flow(
            graph,
            "source",
            "sink",
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )
