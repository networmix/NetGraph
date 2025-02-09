from __future__ import annotations
import uuid
import base64
from dataclasses import dataclass, field
from typing import Any, Dict


def new_base64_uuid() -> str:
    """
    Generate a Base64-encoded UUID without padding (a string with 22 characters).
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


@dataclass(slots=True)
class Node:
    """
    Represents a node in the network.

    Each node is uniquely identified by its name, which is used as the key
    in the Network's node dictionary.

    :param name: The unique name of the node.
    :param attrs: Optional extra metadata for the node. For example:
                  {
                     "type": "node",          # auto-tagged upon add_node
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
    is auto-generated from the source, target, and a random Base64-encoded UUID,
    allowing multiple distinct links between the same nodes.

    :param source: Unique name of the source node.
    :param target: Unique name of the target node.
    :param capacity: Link capacity (default 1.0).
    :param latency: Link latency (default 1.0).
    :param cost: Link cost (default 1.0).
    :param attrs: Optional extra metadata for the link. For example:
                  {
                     "type": "link",              # auto-tagged upon add_link
                     "distance_km": 1500,         # user-provided
                     "fiber_provider": "Lumen",   # user-provided
                  }
    :param id: Auto-generated unique link identifier, e.g. "SEA-DEN-abCdEf..."
    """

    source: str
    target: str
    capacity: float = 1.0
    latency: float = 1.0
    cost: float = 1.0
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """
        Auto-generate a unique link ID by combining the source, target,
        and a random Base64-encoded UUID.
        """
        self.id = f"{self.source}-{self.target}-{new_base64_uuid()}"


@dataclass(slots=True)
class Network:
    """
    A container for network nodes and links.

    Nodes are stored in a dictionary keyed by their unique names (:attr:`Node.name`).
    Links are stored in a dictionary keyed by their auto-generated IDs (:attr:`Link.id`).
    The 'attrs' dict allows extra network metadata.

    :param nodes: Mapping from node name -> Node object.
    :param links: Mapping from link id -> Link object.
    :param attrs: Optional extra metadata for the network itself.
    """

    nodes: Dict[str, Node] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """
        Add a node to the network, keyed by its :attr:`Node.name`.

        This method also auto-tags the node with ``node.attrs["type"] = "node"``
        if it's not already set.

        :param node: The Node to add.
        :raises ValueError: If a node with the same name is already in the network.
        """
        node.attrs.setdefault("type", "node")
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """
        Add a link to the network, keyed by its auto-generated :attr:`Link.id`.

        This method also auto-tags the link with ``link.attrs["type"] = "link"``
        if it's not already set.

        :param link: The Link to add.
        :raises ValueError: If the source/target node is not present in the network.
        """
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        link.attrs.setdefault("type", "link")
        self.links[link.id] = link
