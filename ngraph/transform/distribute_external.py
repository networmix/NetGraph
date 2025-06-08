from dataclasses import dataclass
from typing import List, Sequence

from ngraph.network import Link, Network, Node
from ngraph.scenario import Scenario
from ngraph.transform.base import NetworkTransform, register_transform


@dataclass
class _StripeChooser:
    """Round-robin stripe selection."""

    width: int

    def stripes(self, nodes: List[Node]) -> List[List[Node]]:
        return [nodes[i : i + self.width] for i in range(0, len(nodes), self.width)]

    def select(self, index: int, stripes: List[List[Node]]) -> List[Node]:
        return stripes[index % len(stripes)]


@register_transform("DistributeExternalConnectivity")
class DistributeExternalConnectivity(NetworkTransform):
    """Attach (or create) remote nodes and link them to attachment stripes.

    Args:
        remote_locations: Iterable of node names, e.g. ``["den", "sea"]``.
        attachment_path: Regex matching nodes that accept the links.
        stripe_width: Number of attachment nodes per stripe (≥ 1).
        link_count: Number of links per remote node (default ``1``).
        capacity: Per-link capacity.
        cost: Per-link cost metric.
        remote_prefix: Prefix used when creating remote node names (default ``""``).
    """

    def __init__(
        self,
        remote_locations: Sequence[str],
        attachment_path: str,
        stripe_width: int,
        link_count: int = 1,
        capacity: float = 1.0,
        cost: float = 1.0,
        remote_prefix: str = "",
    ) -> None:
        if stripe_width < 1:
            raise ValueError("stripe_width must be ≥ 1")
        self.remotes = list(remote_locations)
        self.attachment_path = attachment_path
        self.link_count = link_count
        self.capacity = capacity
        self.cost = cost
        self.remote_prefix = remote_prefix
        self.chooser = _StripeChooser(width=stripe_width)
        self.label = f"Distribute {len(self.remotes)} remotes"

    def apply(self, scenario: Scenario) -> None:
        net: Network = scenario.network

        attachments = [
            n
            for _, nodes in net.select_node_groups_by_path(self.attachment_path).items()
            for n in nodes
            if not n.disabled
        ]
        if not attachments:
            raise RuntimeError("No enabled attachment nodes matched.")

        attachments.sort(key=lambda n: n.name)
        stripes = self.chooser.stripes(attachments)

        for idx, short in enumerate(self.remotes):
            remote = _ensure_remote_node(net, short, self.remote_prefix)
            stripe = self.chooser.select(idx, stripes)
            _connect_remote(
                net, remote, stripe, self.capacity, self.cost, self.link_count
            )


def _ensure_remote_node(net: Network, short_name: str, prefix: str) -> Node:
    """Return an existing or newly created remote node."""
    full_name = f"{prefix}{short_name}"
    if full_name not in net.nodes:
        net.add_node(Node(name=full_name, attrs={"type": "remote"}))
    return net.nodes[full_name]


def _connect_remote(
    net: Network,
    remote: Node,
    stripe: Sequence[Node],
    capacity: float,
    cost: float,
    link_count: int = 1,
) -> None:
    """Create links remote → attachment (one-way) if absent."""
    for att in stripe:
        # always add new links on each apply; do not re-add remote nodes
        for _ in range(link_count):
            net.add_link(
                Link(source=remote.name, target=att.name, capacity=capacity, cost=cost)
            )
