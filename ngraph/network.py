from __future__ import annotations

import uuid
import base64
from dataclasses import dataclass, field
from typing import Any, Dict


def new_base64_uuid() -> str:
    """Generates a Base64-encoded UUID without padding (22 characters)."""
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


@dataclass(slots=True)
class Node:
    """
    Represents a node in the network.

    Each node is uniquely identified by its name, which is used as the key
    in the Network's node dictionary.

    Attributes:
        name (str): The unique name of the node.
        attrs (Dict[str, Any]): Optional extra metadata for the node. For example:
            {
                "type": "node",           # auto-tagged upon add_node
                "coords": [lat, lon],     # user-provided
                "region": "west_coast"    # user-provided
            }
    """

    name: str
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Link:
    """
    Represents a link connecting two nodes in the network.

    The 'source' and 'target' fields reference node names. A unique link ID
    is auto-generated from the source, target, and a random Base64-encoded UUID,
    allowing multiple distinct links between the same nodes.

    Attributes:
        source (str): Unique name of the source node.
        target (str): Unique name of the target node.
        capacity (float): Link capacity (default is 1.0).
        cost (float): Link cost (default is 1.0).
        attrs (Dict[str, Any]): Optional extra metadata for the link.
            For example:
            {
                "type": "link",                # auto-tagged upon add_link
                "distance_km": 1500,           # user-provided
                "fiber_provider": "Lumen",     # user-provided
            }
        id (str): Auto-generated unique link identifier, e.g. "SEA-DEN-abCdEf..."
    """

    source: str
    target: str
    capacity: float = 1.0
    cost: float = 1.0
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """Auto-generates a unique link ID by combining the source, target, and a random Base64-encoded UUID."""
        self.id = f"{self.source}|{self.target}|{new_base64_uuid()}"


@dataclass(slots=True)
class Network:
    """
    A container for network nodes and links.

    Nodes are stored in a dictionary keyed by their unique names (Node.name).
    Links are stored in a dictionary keyed by their auto-generated IDs (Link.id).
    The 'attrs' dict allows extra network metadata.

    Attributes:
        nodes (Dict[str, Node]): Mapping from node name -> Node object.
        links (Dict[str, Link]): Mapping from link ID -> Link object.
        attrs (Dict[str, Any]): Optional extra metadata for the network.
    """

    nodes: Dict[str, Node] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """
        Adds a node to the network, keyed by its name.

        This method also auto-tags the node with ``node.attrs["type"] = "node"``
        if it's not already set.

        Args:
            node (Node): The node to add.

        Raises:
            ValueError: If a node with the same name is already in the network.
        """
        node.attrs.setdefault("type", "node")
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """
        Adds a link to the network, keyed by its auto-generated ID.

        This method also auto-tags the link with ``link.attrs["type"] = "link"``
        if it's not already set.

        Args:
            link (Link): The link to add.

        Raises:
            ValueError: If the source or target node is not present in the network.
        """
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        link.attrs.setdefault("type", "link")
        self.links[link.id] = link
