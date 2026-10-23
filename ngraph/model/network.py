"""Network topology modeling with Node, Link, RiskGroup, and Network classes.

These classes carry no analysis machinery and can be used on their own.
Nodes, links and risk groups are immutable records; a Network holds them in
editable dicts and its edit methods replace records.
"""

from __future__ import annotations

import re
from base64 import urlsafe_b64encode
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional
from uuid import uuid4

from ngraph.model.risk import MembershipIndex
from ngraph.utils.values import (
    frozen_attrs,
    frozen_dict,
    own_scalars,
    owned_dict,
    physical,
    scalar,
)

if TYPE_CHECKING:
    from ngraph.model.risk import RiskGroup


@dataclass(frozen=True)
class DirectedLink:
    """One analysis direction of a stored physical link."""

    link: str
    direction: Literal["forward", "reverse"]

    def __post_init__(self) -> None:
        if not isinstance(self.link, str) or not self.link:
            raise ValueError("link: expected a nonempty physical link id")
        if self.direction not in ("forward", "reverse"):
            raise ValueError(f"link {self.link}: direction must be forward or reverse")
        own_scalars(self, "directed link", ("link", "direction"))


@dataclass(frozen=True)
class Node:
    """Network node, keyed by its unique name in ``Network.nodes``.

    Attributes:
        name (str): Unique identifier for the node.
        disabled (bool): Whether the node is disabled in the scenario configuration.
        risk_groups (AbstractSet[str]): Names of the risk groups this node belongs
            to, stored as a frozenset.
        attrs (Dict[str, Any]): Finite JSON metadata (e.g., coordinates, region),
            checked and stored read-only at construction.
    """

    name: str
    disabled: bool = False
    risk_groups: AbstractSet[str] = frozenset()
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        own_scalars(self, "node", ("name",))
        label = f"node {self.name}"
        own_scalars(self, label, ("disabled",))
        object.__setattr__(self, "risk_groups", _names(self.risk_groups, label))
        object.__setattr__(self, "attrs", frozen_attrs(self.attrs, f"{label}.attrs"))


@dataclass(frozen=True)
class Link:
    """One directed link between two nodes.

    The model stores a single direction (``source`` -> ``target``). When the
    prepared native graph is built, a reverse
    edge is added automatically for each link to provide bidirectional
    connectivity.

    Attributes:
        source (str): Name of the source node.
        target (str): Name of the target node.
        capacity (float): Finite nonnegative link capacity (default 1.0),
            promoted to binary64 at construction.
        cost (float): Link cost (default 1.0).
        disabled (bool): Whether the link is disabled.
        risk_groups (AbstractSet[str]): Names of the risk groups this link belongs
            to, stored as a frozenset.
        attrs (Dict[str, Any]): Finite JSON metadata (e.g., distance), checked
            and stored read-only at construction.
        id (str): Unique identifier. ``Network.add_link`` assigns the
            deterministic form "{source}|{target}|<seq>", where <seq> is a
            per-(source, target) insertion sequence number, once; links never
            added to a Network keep a provisional uuid-suffixed id.
    """

    source: str
    target: str
    capacity: float = 1.0
    cost: float = 1.0
    disabled: bool = False
    risk_groups: AbstractSet[str] = frozenset()
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate the fields and assign a provisional unique ID.

        Network.add_link replaces it with the deterministic
        "source|target|<seq>" form; the uuid suffix only guarantees
        uniqueness for links never added to a Network.
        """
        own_scalars(self, "link", ("source", "target"))
        label = f"link {self.source}->{self.target}"
        own_scalars(self, label, ("cost", "disabled"))
        object.__setattr__(
            self, "capacity", physical(self.capacity, f"{label}.capacity")
        )
        object.__setattr__(self, "risk_groups", _names(self.risk_groups, label))
        object.__setattr__(self, "attrs", frozen_attrs(self.attrs, f"{label}.attrs"))
        suffix = urlsafe_b64encode(uuid4().bytes)[:-2].decode("ascii")
        object.__setattr__(self, "id", f"{self.source}|{self.target}|{suffix}")


def _names(values: Any, label: str) -> frozenset[str]:
    if isinstance(values, str):
        raise ValueError(f"{label}.risk_groups: expected a collection of names")
    return frozenset(scalar(name, f"{label}.risk_groups") for name in values)


@dataclass(frozen=True)
class Network:
    """Scenario-level topology: nodes, links, and risk groups.

    Holds persistent state only (nodes and links disabled in the scenario
    configuration). For temporary exclusions, pass a graph-owned Eligibility
    through the native operation's options.

    The dicts stay editable; their values are immutable records, so an edit
    replaces a record. ``prepare`` keeps a read-only view of these dicts, so
    later edits do not reach a prepared scenario.

    Attributes:
        nodes (Dict[str, Node]): Mapping from node name -> Node object.
        links (Dict[str, Link]): Mapping from link ID -> Link object.
        risk_groups (Dict[str, RiskGroup]): Top-level risk groups by name.
        attrs (Dict[str, Any]): Optional metadata about the network.
    """

    nodes: Dict[str, Node] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    risk_groups: Dict[str, RiskGroup] = field(default_factory=dict)
    attrs: Dict[str, Any] = field(default_factory=dict)
    _link_seq: Dict[tuple, int] = field(default_factory=dict, init=False, repr=False)

    def snapshot(self) -> Network:
        """Return a read-only view sharing this network's immutable records.

        Each dict is copied by reference, under plain string keys, into a
        read-only dict of its own; ``attrs`` is checked as JSON and frozen.
        """
        view = Network(
            owned_dict(self.nodes, "network.nodes"),
            owned_dict(self.links, "network.links"),
            owned_dict(self.risk_groups, "network.risk_groups"),
            frozen_attrs(self.attrs, "network.attrs"),
        )
        object.__setattr__(view, "_link_seq", frozen_dict(self._link_seq))
        return view

    def add_node(self, node: Node) -> None:
        """Add a node to the network (keyed by node.name).

        Args:
            node (Node): Node to add.

        Raises:
            ValueError: If a node with the same name already exists.
        """
        if not isinstance(node, Node):
            raise TypeError("add_node: expected Node")
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """Add a link to the network, assigning its deterministic ID.

        The link's ID is assigned here, once, as "source|target|<seq>", where
        <seq> is a per-(source, target) insertion sequence number, so ids and
        their sort order are stable across identical scenario builds.

        Args:
            link (Link): Link to add.

        Raises:
            ValueError: If the link's source or target node does not exist.
            ValueError: If this Link object was already added to a network;
                add ``dataclasses.replace(link)`` to place a copy.
            ValueError: If the generated "source|target|<seq>" id collides with
                an existing one, which distinct endpoint pairs can do when node
                names contain '|' (e.g. 'a|b'->'c' vs 'a'->'b|c').
        """
        if not isinstance(link, Link):
            raise TypeError("add_link: expected Link")
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        # Reassign a deterministic per-pair sequence id. The uuid suffix from
        # construction makes parallel links sort in a rebuild-dependent order,
        # which breaks seeded reproducibility of failure sampling and makes
        # link ids unstable across identical scenario builds.
        if "_placed" in vars(link):
            raise ValueError(
                f"Link '{link.id}' has already been added to a network; "
                "add dataclasses.replace(link) to place a copy."
            )
        pair = (link.source, link.target)
        seq = self._link_seq.get(pair, 0)
        new_id = f"{link.source}|{link.target}|{seq}"
        if new_id in self.links:
            # Distinct endpoint pairs can render to the same string when node
            # names contain '|' (e.g. 'a|b'->'c' vs 'a'->'b|c'); refuse
            # rather than silently overwriting the earlier link.
            raise ValueError(
                f"Link id '{new_id}' already exists; node names containing "
                "'|' can make distinct endpoint pairs ambiguous."
            )
        self.links[new_id] = link
        self._link_seq[pair] = seq + 1
        # The id is completed once, when the link joins its network.
        object.__setattr__(link, "id", new_id)
        object.__setattr__(link, "_placed", True)

    def replace_node(self, name: str, **changes: Any) -> Node:
        """Replace a node by a copy with the given field changes."""
        if name not in self.nodes:
            raise ValueError(f"Node '{name}' does not exist.")
        node = self.nodes[name] = replace(self.nodes[name], **changes)
        return node

    def replace_link(self, link_id: str, **changes: Any) -> Link:
        """Replace a link by a copy with the given field changes; its id stays.

        The endpoints are the link's identity: to move a link, add a new one.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        endpoints = sorted({"source", "target"} & changes.keys())
        if endpoints:
            raise ValueError(
                f"Link '{link_id}': {' and '.join(endpoints)} cannot change; "
                "add a new link instead."
            )
        link = replace(self.links[link_id], **changes)
        object.__setattr__(link, "id", link_id)
        object.__setattr__(link, "_placed", True)
        self.links[link_id] = link
        return link

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[Node]]:
        r"""Select and group nodes by regex pattern on node name.

        Uses re.match() (anchored at start of string). Grouping behavior:
        - With capturing groups: label is "|"-joined non-None captures.
        - Without captures: label is the original pattern string.

        For attribute-based grouping, use a selector dict such as
        ``{"group_by": "attr_name"}``.

        Args:
            path: Regex pattern for node name.

        Returns:
            A fresh mapping from group label to a fresh list of nodes.
        """
        pattern = re.compile(path)
        groups_map: Dict[str, List[Node]] = {}

        for node in self.nodes.values():
            match = pattern.match(node.name)
            if match:
                captures = match.groups()
                if captures:
                    label = "|".join(c for c in captures if c is not None)
                else:
                    label = path
                groups_map.setdefault(label, []).append(node)

        return groups_map

    def disable_node(self, node_name: str) -> None:
        """Mark a node as disabled.

        Args:
            node_name (str): Name of the node to disable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        self.replace_node(node_name, disabled=True)

    def enable_node(self, node_name: str) -> None:
        """Mark a node as enabled.

        Args:
            node_name (str): Name of the node to enable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        self.replace_node(node_name, disabled=False)

    def disable_link(self, link_id: str) -> None:
        """Mark a link as disabled.

        Args:
            link_id (str): ID of the link to disable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        self.replace_link(link_id, disabled=True)

    def enable_link(self, link_id: str) -> None:
        """Mark a link as enabled.

        Args:
            link_id (str): ID of the link to enable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        self.replace_link(link_id, disabled=False)

    def enable_all(self) -> None:
        """Mark all nodes and links as enabled."""
        for name in self.nodes:
            self.replace_node(name, disabled=False)
        for link_id in self.links:
            self.replace_link(link_id, disabled=False)

    def disable_all(self) -> None:
        """Mark all nodes and links as disabled."""
        for name in self.nodes:
            self.replace_node(name, disabled=True)
        for link_id in self.links:
            self.replace_link(link_id, disabled=True)

    def get_links_between(self, source: str, target: str) -> List[str]:
        """Retrieve the IDs of all direct links from source to target.

        Args:
            source (str): Source node name.
            target (str): Target node name.

        Returns:
            List[str]: Link IDs for every direct source -> target link. Empty
                if the nodes are unconnected or unknown.
        """
        matches = []
        for link_id, link in self.links.items():
            if link.source == source and link.target == target:
                matches.append(link_id)
        return matches

    def find_links(
        self,
        source_regex: Optional[str] = None,
        target_regex: Optional[str] = None,
        any_direction: bool = False,
    ) -> List[Link]:
        """Search for links by regex on source and/or target node names.

        Unlike selector paths (which anchor at the start via ``re.match``),
        these patterns use unanchored ``re.search`` and match anywhere in the
        node name; anchor explicitly (``^...$``) for exact-name matching.

        Args:
            source_regex (Optional[str]): Regex matched against link.source;
                None matches every source.
            target_regex (Optional[str]): Regex matched against link.target;
                None matches every target.
            any_direction (bool): If True, also match reversed source/target.

        Returns:
            List[Link]: Matching Link objects, deduplicated by link ID.
        """
        src_pat = re.compile(source_regex) if source_regex else None
        tgt_pat = re.compile(target_regex) if target_regex else None

        results = []
        seen_ids = set()

        for link in self.links.values():
            forward_match = (not src_pat or src_pat.search(link.source)) and (
                not tgt_pat or tgt_pat.search(link.target)
            )
            reverse_match = False
            if any_direction:
                reverse_match = (not src_pat or src_pat.search(link.target)) and (
                    not tgt_pat or tgt_pat.search(link.source)
                )

            if forward_match or reverse_match:
                if link.id not in seen_ids:
                    results.append(link)
                    seen_ids.add(link.id)

        return results

    def disable_risk_group(self, name: str, recursive: bool = True) -> None:
        """Disable every node/link that has 'name' in its risk_groups.

        Unknown group names are ignored.

        Args:
            name (str): Name of the risk group to disable.
            recursive (bool): If True, also disable members of child groups,
                transitively.
        """
        index = MembershipIndex.build(self)
        if name not in index.groups:
            return
        members = index.members(name, recursive)
        for node_name in sorted(members.nodes):
            self.disable_node(node_name)
        for link_id in sorted(members.links):
            self.disable_link(link_id)

    def enable_risk_group(self, name: str, recursive: bool = True) -> None:
        """Enable every node/link that has 'name' in its risk_groups.

        Unknown group names are ignored. A node or link in several risk
        groups is re-enabled even if other groups containing it remain
        disabled.

        Args:
            name (str): Name of the risk group to enable.
            recursive (bool): If True, also enable members of child groups,
                transitively.
        """
        index = MembershipIndex.build(self)
        if name not in index.groups:
            return
        members = index.members(name, recursive)
        for node_name in sorted(members.nodes):
            self.enable_node(node_name)
        for link_id in sorted(members.links):
            self.enable_link(link_id)
