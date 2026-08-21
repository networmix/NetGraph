"""Network topology modeling with Node, Link, RiskGroup, and Network classes.

These classes carry no analysis machinery and can be used on their own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ngraph.utils.ids import new_base64_uuid


@dataclass
class Node:
    """Represents a node in the network.

    Each node is uniquely identified by its name, which is used as
    the key in the Network's node dictionary.

    Attributes:
        name (str): Unique identifier for the node.
        disabled (bool): Whether the node is disabled in the scenario configuration.
        risk_groups (Set[str]): Set of risk group names this node belongs to.
        attrs (Dict[str, Any]): Additional metadata (e.g., coordinates, region).
    """

    name: str
    disabled: bool = False
    risk_groups: Set[str] = field(default_factory=set)
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Link:
    """Represents one directed link between two nodes.

    The model stores a single direction (``source`` -> ``target``). When the
    analysis graph is built (via ``AnalysisContext`` / netgraph-core), a reverse
    edge is added automatically for each link to provide bidirectional
    connectivity.

    Attributes:
        source (str): Name of the source node.
        target (str): Name of the target node.
        capacity (float): Link capacity (default 1.0).
        cost (float): Link cost (default 1.0).
        disabled (bool): Whether the link is disabled.
        risk_groups (Set[str]): Set of risk group names this link belongs to.
        attrs (Dict[str, Any]): Additional metadata (e.g., distance).
        id (str): Unique identifier. ``Network.add_link`` assigns the
            deterministic form "{source}|{target}|<seq>", where <seq> is a
            per-(source, target) insertion sequence number; links never added
            to a Network keep a provisional uuid-suffixed id.
    """

    source: str
    target: str
    capacity: float = 1.0
    cost: float = 1.0
    disabled: bool = False
    risk_groups: Set[str] = field(default_factory=set)
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """Assign a provisional unique ID.

        Network.add_link replaces it with the deterministic
        "source|target|<seq>" form; the uuid suffix only guarantees
        uniqueness for links never added to a Network.
        """
        self.id = f"{self.source}|{self.target}|{new_base64_uuid()}"


@dataclass
class RiskGroup:
    """Represents a shared-risk or failure domain, which may have nested children.

    Risk groups model correlated failures: when a risk group fails, all entities
    (nodes, links) in that group fail together. Hierarchical children enable
    cascading failures (parent failure implies all descendants fail).

    Risk groups can be created three ways:
    1. Direct definition: Explicitly named in YAML risk_groups section
    2. Membership rules: Auto-assign entities based on attribute matching
    3. Generate blocks: Auto-create groups from unique attribute values

    Attributes:
        name (str): Unique name of this risk group.
        children (List[RiskGroup]): Subdomains in a nested structure.
        disabled (bool): Whether this group was declared disabled on load.
        attrs (Dict[str, Any]): Additional metadata for the risk group.
        _membership_raw (Optional[Dict[str, Any]]): Raw membership rule for
            deferred resolution. Internal use only.
    """

    name: str
    children: List[RiskGroup] = field(default_factory=list)
    disabled: bool = False
    attrs: Dict[str, Any] = field(default_factory=dict)
    _membership_raw: Optional[Dict[str, Any]] = field(default=None, repr=False)


@dataclass
class Network:
    """A container for network nodes and links.

    Network represents the scenario-level topology with persistent state (nodes/links
    that are disabled in the scenario configuration). For temporary exclusion of
    nodes/links during analysis (e.g., failure simulation), use node_mask and edge_mask
    parameters when calling NetGraph-Core algorithms.

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
    _selection_cache: Dict[str, Dict[str, List[Node]]] = field(
        default_factory=dict, init=False, repr=False
    )
    _link_seq: Dict[tuple, int] = field(default_factory=dict, init=False, repr=False)

    def add_node(self, node: Node) -> None:
        """Add a node to the network (keyed by node.name).

        Args:
            node (Node): Node to add.

        Raises:
            ValueError: If a node with the same name already exists.
        """
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node
        self._selection_cache.clear()

    def add_link(self, link: Link) -> None:
        """Add a link to the network, assigning its deterministic ID.

        The link's ID is (re)assigned here as "source|target|<seq>", where
        <seq> is a per-(source, target) insertion sequence number, so ids and
        their sort order are stable across identical scenario builds.

        Args:
            link (Link): Link to add.

        Raises:
            ValueError: If the link's source or target node does not exist.
            ValueError: If this Link object was already added to this network.
            ValueError: If the generated "source|target|<seq>" id collides with
                an existing one, which distinct endpoint pairs can do when node
                names contain '|' (e.g. 'a|b'->'c' vs 'a'->'b|c').
        """
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        # Reassign a deterministic per-pair sequence id. The uuid suffix from
        # construction makes parallel links sort in a rebuild-dependent order,
        # which breaks seeded reproducibility of failure sampling and makes
        # link ids unstable across identical scenario builds.
        if self.links.get(link.id) is link:
            raise ValueError(
                f"Link '{link.id}' has already been added to this network."
            )
        pair = (link.source, link.target)
        seq = self._link_seq.get(pair, 0)
        self._link_seq[pair] = seq + 1
        new_id = f"{link.source}|{link.target}|{seq}"
        if new_id in self.links:
            # Distinct endpoint pairs can render to the same string when node
            # names contain '|' (e.g. 'a|b'->'c' vs 'a'->'b|c'); refuse
            # rather than silently overwriting the earlier link.
            raise ValueError(
                f"Link id '{new_id}' already exists; node names containing "
                "'|' can make distinct endpoint pairs ambiguous."
            )
        link.id = new_id
        self.links[link.id] = link

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[Node]]:
        r"""Select and group nodes by regex pattern on node name.

        Uses re.match() (anchored at start of string). Grouping behavior:
        - With capturing groups: label is "|"-joined non-None captures.
        - Without captures: label is the original pattern string.

        Note: For attribute-based grouping, use the unified selector system
        with ``{"group_by": "attr_name"}`` dict selectors.

        Args:
            path: Regex pattern for node name.

        Returns:
            A fresh mapping from group label to a fresh list of nodes; the Node
            objects themselves are shared, so mutating the returned mapping or
            lists does not affect the internal selection cache.
        """
        # Check cache first. A shallow copy protects the cache from caller
        # mutation (groups map and lists are fresh; Node objects are shared).
        cached = self._selection_cache.get(path)
        if cached is not None:
            return {label: list(nodes) for label, nodes in cached.items()}

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

        self._selection_cache[path] = groups_map
        return {label: list(nodes) for label, nodes in groups_map.items()}

    def disable_node(self, node_name: str) -> None:
        """Mark a node as disabled.

        Args:
            node_name (str): Name of the node to disable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' does not exist.")
        self.nodes[node_name].disabled = True

    def enable_node(self, node_name: str) -> None:
        """Mark a node as enabled.

        Args:
            node_name (str): Name of the node to enable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' does not exist.")
        self.nodes[node_name].disabled = False

    def disable_link(self, link_id: str) -> None:
        """Mark a link as disabled.

        Args:
            link_id (str): ID of the link to disable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        self.links[link_id].disabled = True

    def enable_link(self, link_id: str) -> None:
        """Mark a link as enabled.

        Args:
            link_id (str): ID of the link to enable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        self.links[link_id].disabled = False

    def enable_all(self) -> None:
        """Mark all nodes and links as enabled."""
        for node in self.nodes.values():
            node.disabled = False
        for link in self.links.values():
            link.disabled = False

    def disable_all(self) -> None:
        """Mark all nodes and links as disabled."""
        for node in self.nodes.values():
            node.disabled = True
        for link in self.links.values():
            link.disabled = True

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
        if name not in self.risk_groups:
            return

        to_disable: Set[str] = set()
        queue = [self.risk_groups[name]]
        while queue:
            grp = queue.pop()
            if grp.name in to_disable:
                continue
            to_disable.add(grp.name)
            if recursive:
                queue.extend(grp.children)

        for node_name, node_obj in self.nodes.items():
            if node_obj.risk_groups & to_disable:
                self.disable_node(node_name)

        for link_id, link_obj in self.links.items():
            if link_obj.risk_groups & to_disable:
                self.disable_link(link_id)

    def enable_risk_group(self, name: str, recursive: bool = True) -> None:
        """Enable every node/link that has 'name' in its risk_groups.

        Unknown group names are ignored.

        Note:
            If a node or link is in multiple risk groups, enabling this group
            will re-enable that node/link even if other groups containing it
            remain disabled.

        Args:
            name (str): Name of the risk group to enable.
            recursive (bool): If True, also enable members of child groups,
                transitively.
        """
        if name not in self.risk_groups:
            return

        to_enable: Set[str] = set()
        queue = [self.risk_groups[name]]
        while queue:
            grp = queue.pop()
            if grp.name in to_enable:
                continue
            to_enable.add(grp.name)
            if recursive:
                queue.extend(grp.children)

        for node_name, node_obj in self.nodes.items():
            if node_obj.risk_groups & to_enable:
                self.enable_node(node_name)

        for link_id, link_obj in self.links.items():
            if link_obj.risk_groups & to_enable:
                self.enable_link(link_id)
