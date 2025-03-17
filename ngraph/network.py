from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.algorithms.max_flow import calc_max_flow
from ngraph.lib.graph import StrictMultiDiGraph


def new_base64_uuid() -> str:
    """
    Generate a Base64-encoded, URL-safe UUID (22 characters, no padding).

    Returns:
        str: A 22-character Base64 URL-safe string with trailing '=' removed.
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


@dataclass(slots=True)
class Node:
    """
    Represents a node in the network.

    Each node is uniquely identified by its name, which is used as
    the key in the Network's node dictionary.

    Attributes:
        name (str): Unique identifier for the node.
        disabled (bool): Whether the node is disabled (excluded from calculations).
        risk_groups (Set[str]): Set of risk group names this node belongs to.
        attrs (Dict[str, Any]): Additional metadata (e.g., coordinates, region).
    """

    name: str
    disabled: bool = False
    risk_groups: Set[str] = field(default_factory=set)
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Link:
    """
    Represents a directed link between two nodes in the network.

    Attributes:
        source (str): Name of the source node.
        target (str): Name of the target node.
        capacity (float): Link capacity (default 1.0).
        cost (float): Link cost (default 1.0).
        disabled (bool): Whether the link is disabled.
        risk_groups (Set[str]): Set of risk group names this link belongs to.
        attrs (Dict[str, Any]): Additional metadata (e.g., distance).
        id (str): Auto-generated unique identifier: "{source}|{target}|<base64_uuid>".
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
        """
        Generate the link's unique ID upon initialization.
        """
        self.id = f"{self.source}|{self.target}|{new_base64_uuid()}"


@dataclass(slots=True)
class RiskGroup:
    """
    Represents a shared-risk or failure domain, which may have nested children.

    Attributes:
        name (str): Unique name of this risk group.
        children (List[RiskGroup]): Subdomains in a nested structure.
        disabled (bool): Whether this group was declared disabled on load.
        attrs (Dict[str, Any]): Additional metadata for the risk group.
    """

    name: str
    children: List[RiskGroup] = field(default_factory=list)
    disabled: bool = False
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Network:
    """
    A container for network nodes and links.

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

    def add_node(self, node: Node) -> None:
        """
        Add a node to the network (keyed by node.name).

        Args:
            node (Node): Node to add.

        Raises:
            ValueError: If a node with the same name already exists.
        """
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """
        Add a link to the network (keyed by the link's auto-generated ID).

        Args:
            link (Link): Link to add.

        Raises:
            ValueError: If the link's source or target node does not exist.
        """
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        self.links[link.id] = link

    def to_strict_multidigraph(self, add_reverse: bool = True) -> StrictMultiDiGraph:
        """
        Create a StrictMultiDiGraph representation of this Network.

        Skips disabled nodes/links. Optionally adds reverse edges.

        Args:
            add_reverse (bool): If True, also add a reverse edge for each link.

        Returns:
            StrictMultiDiGraph: A directed multigraph representation of the network.
        """
        graph = StrictMultiDiGraph()
        disabled_nodes = {name for name, nd in self.nodes.items() if nd.disabled}

        # Add enabled nodes
        for node_name, node in self.nodes.items():
            if not node.disabled:
                graph.add_node(node_name, **node.attrs)

        # Add enabled links
        for link_id, link in self.links.items():
            if link.disabled:
                continue
            if link.source in disabled_nodes or link.target in disabled_nodes:
                continue

            # Add forward edge
            graph.add_edge(
                link.source,
                link.target,
                key=link_id,
                capacity=link.capacity,
                cost=link.cost,
                **link.attrs,
            )

            # Optionally add reverse edge
            if add_reverse:
                reverse_id = f"{link_id}_rev"
                graph.add_edge(
                    link.target,
                    link.source,
                    key=reverse_id,
                    capacity=link.capacity,
                    cost=link.cost,
                    **link.attrs,
                )

        return graph

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[Node]]:
        """
        Select and group nodes whose names match a given regular expression.

        Uses re.match(), so the pattern is anchored at the start of the node name.
        If the pattern includes capturing groups, the group label is formed by
        joining all non-None captures with '|'. If no capturing groups exist,
        the group label is the original pattern string.

        Args:
            path (str): A Python regular expression pattern (e.g., "^foo", "bar(\\d+)", etc.).

        Returns:
            Dict[str, List[Node]]: A mapping from group label -> list of matching nodes.
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

    def max_flow(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], float]:
        """
        Compute maximum flow between groups of source nodes and sink nodes.

        Returns a dictionary of flow values keyed by (source_label, sink_label).

        Args:
            source_path (str): Regex pattern for selecting source nodes.
            sink_path (str): Regex pattern for selecting sink nodes.
            mode (str): Either "combine" or "pairwise".
                - "combine": Treat all matched sources as one group,
                  and all matched sinks as one group. Returns a single entry.
                - "pairwise": Compute flow for each (source_group, sink_group) pair.
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): Determines how parallel equal-cost paths
                are handled.

        Returns:
            Dict[Tuple[str, str], float]: Flow values keyed by (src_label, snk_label).

        Raises:
            ValueError: If no matching source or sink groups are found, or invalid mode.
        """
        src_groups = self.select_node_groups_by_path(source_path)
        snk_groups = self.select_node_groups_by_path(sink_path)

        if not src_groups:
            raise ValueError(f"No source nodes found matching '{source_path}'.")
        if not snk_groups:
            raise ValueError(f"No sink nodes found matching '{sink_path}'.")

        if mode == "combine":
            combined_src_nodes: List[Node] = []
            combined_snk_nodes: List[Node] = []
            combined_src_label = "|".join(sorted(src_groups.keys()))
            combined_snk_label = "|".join(sorted(snk_groups.keys()))

            for group_nodes in src_groups.values():
                combined_src_nodes.extend(group_nodes)
            for group_nodes in snk_groups.values():
                combined_snk_nodes.extend(group_nodes)

            if not combined_src_nodes or not combined_snk_nodes:
                return {(combined_src_label, combined_snk_label): 0.0}

            flow_val = self._compute_flow_single_group(
                combined_src_nodes, combined_snk_nodes, shortest_path, flow_placement
            )
            return {(combined_src_label, combined_snk_label): flow_val}

        elif mode == "pairwise":
            results: Dict[Tuple[str, str], float] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        flow_val = self._compute_flow_single_group(
                            src_nodes, snk_nodes, shortest_path, flow_placement
                        )
                    else:
                        flow_val = 0.0
                    results[(src_label, snk_label)] = flow_val
            return results

        else:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")

    def _compute_flow_single_group(
        self,
        sources: List[Node],
        sinks: List[Node],
        shortest_path: bool,
        flow_placement: Optional[FlowPlacement],
    ) -> float:
        """
        Attach a pseudo-source and pseudo-sink to the provided node lists,
        then run calc_max_flow. Returns the resulting flow from all
        sources to all sinks as a single float.

        Disabled nodes are excluded from flow computation.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            shortest_path (bool): If True, restrict flows to shortest paths only.
            flow_placement (FlowPlacement or None): Strategy for placing flow among
                parallel equal-cost paths. If None, defaults to FlowPlacement.PROPORTIONAL.

        Returns:
            float: The computed max flow value, or 0.0 if no active sources or sinks.
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            return 0.0

        graph = self.to_strict_multidigraph()
        graph.add_node("source")
        graph.add_node("sink")

        # Connect pseudo-source to active sources
        for src_node in active_sources:
            graph.add_edge("source", src_node.name, capacity=float("inf"), cost=0)

        # Connect active sinks to pseudo-sink
        for sink_node in active_sinks:
            graph.add_edge(sink_node.name, "sink", capacity=float("inf"), cost=0)

        return calc_max_flow(
            graph,
            "source",
            "sink",
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )

    def disable_node(self, node_name: str) -> None:
        """
        Mark a node as disabled.

        Args:
            node_name (str): Name of the node to disable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' does not exist.")
        self.nodes[node_name].disabled = True

    def enable_node(self, node_name: str) -> None:
        """
        Mark a node as enabled.

        Args:
            node_name (str): Name of the node to enable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' does not exist.")
        self.nodes[node_name].disabled = False

    def disable_link(self, link_id: str) -> None:
        """
        Mark a link as disabled.

        Args:
            link_id (str): ID of the link to disable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        self.links[link_id].disabled = True

    def enable_link(self, link_id: str) -> None:
        """
        Mark a link as enabled.

        Args:
            link_id (str): ID of the link to enable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        self.links[link_id].disabled = False

    def enable_all(self) -> None:
        """
        Mark all nodes and links as enabled.
        """
        for node in self.nodes.values():
            node.disabled = False
        for link in self.links.values():
            link.disabled = False

    def disable_all(self) -> None:
        """
        Mark all nodes and links as disabled.
        """
        for node in self.nodes.values():
            node.disabled = True
        for link in self.links.values():
            link.disabled = True

    def get_links_between(self, source: str, target: str) -> List[str]:
        """
        Retrieve all link IDs that connect the specified source node
        to the target node.

        Args:
            source (str): Source node name.
            target (str): Target node name.

        Returns:
            List[str]: A list of link IDs for all direct links from source to target.
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
        """
        Search for links using optional regex patterns for source or target node names.

        Args:
            source_regex (str or None): Regex to match link.source. If None, matches all sources.
            target_regex (str or None): Regex to match link.target. If None, matches all targets.
            any_direction (bool): If True, also match reversed source/target.

        Returns:
            List[Link]: A list of unique Link objects that match the criteria.
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
        """
        Disable all nodes/links that have 'name' in their risk_groups.
        If recursive=True, also disable items belonging to child risk groups.

        Args:
            name (str): The name of the risk group to disable.
            recursive (bool): If True, also disable subgroups recursively.
        """
        if name not in self.risk_groups:
            return

        to_disable: Set[str] = set()
        queue = [self.risk_groups[name]]
        while queue:
            grp = queue.pop()
            to_disable.add(grp.name)
            if recursive:
                queue.extend(grp.children)

        # Disable nodes
        for node_name, node_obj in self.nodes.items():
            if node_obj.risk_groups & to_disable:
                self.disable_node(node_name)

        # Disable links
        for link_id, link_obj in self.links.items():
            if link_obj.risk_groups & to_disable:
                self.disable_link(link_id)

    def enable_risk_group(self, name: str, recursive: bool = True) -> None:
        """
        Enable all nodes/links that have 'name' in their risk_groups.
        If recursive=True, also enable items belonging to child risk groups.

        Note:
            If a node or link is in multiple risk groups, enabling this group
            will re-enable that node/link even if other groups containing it
            remain disabled.

        Args:
            name (str): The name of the risk group to enable.
            recursive (bool): If True, also enable subgroups recursively.
        """
        if name not in self.risk_groups:
            return

        to_enable: Set[str] = set()
        queue = [self.risk_groups[name]]
        while queue:
            grp = queue.pop()
            to_enable.add(grp.name)
            if recursive:
                queue.extend(grp.children)

        # Enable nodes
        for node_name, node_obj in self.nodes.items():
            if node_obj.risk_groups & to_enable:
                self.enable_node(node_name)

        # Enable links
        for link_id, link_obj in self.links.items():
            if link_obj.risk_groups & to_enable:
                self.enable_link(link_id)
