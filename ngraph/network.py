from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
        attrs (Dict[str, Any]): Optional metadata (e.g., type, coordinates, region).
                                Set attrs["disabled"] = True to mark the node as inactive.
                                Defaults to an empty dict.
    """

    name: str
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
        attrs (Dict[str, Any]): Optional metadata (e.g., type, distance).
                                Set attrs["disabled"] = True to mark link as inactive.
                                Defaults to an empty dict.
        id (str): Auto-generated unique identifier in the form
                  "{source}|{target}|<base64_uuid>".
    """

    source: str
    target: str
    capacity: float = 1.0
    cost: float = 1.0
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = field(init=False)

    def __post_init__(self) -> None:
        """
        Generate the link's unique ID by combining source, target,
        and a random Base64-encoded UUID.
        """
        self.id = f"{self.source}|{self.target}|{new_base64_uuid()}"


@dataclass(slots=True)
class Network:
    """
    A container for network nodes and links.

    Attributes:
        nodes (Dict[str, Node]): Mapping from node name -> Node object.
        links (Dict[str, Link]): Mapping from link ID -> Link object.
        attrs (Dict[str, Any]): Optional metadata about the network.
    """

    nodes: Dict[str, Node] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """
        Add a node to the network (keyed by node.name).

        Auto-tags node.attrs["type"] = "node" if not already set,
        and node.attrs["disabled"] = False if not specified.

        Args:
            node: Node to add.

        Raises:
            ValueError: If a node with the same name already exists.
        """
        node.attrs.setdefault("type", "node")
        node.attrs.setdefault("disabled", False)
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """
        Add a link to the network (keyed by the link's auto-generated ID).

        Auto-tags link.attrs["type"] = "link" if not already set,
        and link.attrs["disabled"] = False if not specified.

        Args:
            link: Link to add.

        Raises:
            ValueError: If the link's source or target node does not exist.
        """
        if link.source not in self.nodes:
            raise ValueError(f"Source node '{link.source}' not found in network.")
        if link.target not in self.nodes:
            raise ValueError(f"Target node '{link.target}' not found in network.")

        link.attrs.setdefault("type", "link")
        link.attrs.setdefault("disabled", False)
        self.links[link.id] = link

    def to_strict_multidigraph(self, add_reverse: bool = True) -> StrictMultiDiGraph:
        """
        Create a StrictMultiDiGraph representation of this Network.

        Nodes and links whose attrs["disabled"] == True are omitted.

        Args:
            add_reverse: If True, also add a reverse edge for each link.

        Returns:
            StrictMultiDiGraph: A directed multigraph representation of the network.
        """
        graph = StrictMultiDiGraph()

        # Identify disabled nodes for quick checks
        disabled_nodes = {
            name
            for name, node in self.nodes.items()
            if node.attrs.get("disabled", False)
        }

        # Add enabled nodes
        for node_name, node in self.nodes.items():
            if not node.attrs.get("disabled", False):
                graph.add_node(node_name, **node.attrs)

        # Add enabled links
        for link_id, link in self.links.items():
            if link.attrs.get("disabled", False):
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

        This method uses re.match(), so the pattern is anchored at the start
        of the node name. If the pattern includes capturing groups,
        the group label is formed by joining all non-None captures with '|'.
        If no capturing groups exist, the group label is the original
        pattern string.

        Args:
            path: A Python regular expression pattern (e.g., "^foo", "bar(\\d+)", etc.).

        Returns:
            Dict[str, List[Node]]: A mapping from group label -> list of matching nodes.
        """
        pattern = re.compile(path)
        groups_map: Dict[str, List[Node]] = {}

        for node in self.nodes.values():
            m = pattern.match(node.name)
            if m:
                captures = m.groups()
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
            source_path: Regex pattern for selecting source nodes.
            sink_path: Regex pattern for selecting sink nodes.
            mode: Either "combine" or "pairwise".
                - "combine": Treat all matched sources as one group,
                  and all matched sinks as one group. Returns a single dict entry.
                - "pairwise": Compute flow for each (source_group, sink_group) pair.
            shortest_path: If True, flows are constrained to shortest paths.
            flow_placement: Determines how parallel equal-cost paths are handled.

        Returns:
            Dict[Tuple[str, str], float]: Flow values for each (src_label, snk_label) pair.

        Raises:
            ValueError: If no matching source or sink groups are found,
                        or if the mode is invalid.
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
        flow_placement: FlowPlacement,
    ) -> float:
        """
        Attach a pseudo-source and pseudo-sink to the provided node lists,
        then run calc_max_flow. Returns the resulting flow from all
        sources to all sinks as a single float.

        Disabled nodes are excluded from flow computation.

        Args:
            sources: List of source nodes.
            sinks: List of sink nodes.
            shortest_path: If True, use only shortest paths for flow.
            flow_placement: Strategy for placing flow among parallel equal-cost paths.

        Returns:
            float: The computed maximum flow value, or 0.0 if there are no active sources or sinks.
        """
        active_sources = [s for s in sources if not s.attrs.get("disabled", False)]
        active_sinks = [s for s in sinks if not s.attrs.get("disabled", False)]

        if not active_sources or not active_sinks:
            return 0.0

        graph = self.to_strict_multidigraph()
        graph.add_node("source")
        graph.add_node("sink")

        for src_node in active_sources:
            graph.add_edge("source", src_node.name, capacity=float("inf"), cost=0)
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
            node_name: Name of the node to disable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' does not exist.")
        self.nodes[node_name].attrs["disabled"] = True

    def enable_node(self, node_name: str) -> None:
        """
        Mark a node as enabled.

        Args:
            node_name: Name of the node to enable.

        Raises:
            ValueError: If the specified node does not exist.
        """
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' does not exist.")
        self.nodes[node_name].attrs["disabled"] = False

    def disable_link(self, link_id: str) -> None:
        """
        Mark a link as disabled.

        Args:
            link_id: ID of the link to disable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        self.links[link_id].attrs["disabled"] = True

    def enable_link(self, link_id: str) -> None:
        """
        Mark a link as enabled.

        Args:
            link_id: ID of the link to enable.

        Raises:
            ValueError: If the specified link does not exist.
        """
        if link_id not in self.links:
            raise ValueError(f"Link '{link_id}' does not exist.")
        self.links[link_id].attrs["disabled"] = False

    def enable_all(self) -> None:
        """
        Mark all nodes and links as enabled.
        """
        for node in self.nodes.values():
            node.attrs["disabled"] = False
        for link in self.links.values():
            link.attrs["disabled"] = False

    def disable_all(self) -> None:
        """
        Mark all nodes and links as disabled.
        """
        for node in self.nodes.values():
            node.attrs["disabled"] = True
        for link in self.links.values():
            link.attrs["disabled"] = True

    def get_links_between(self, source: str, target: str) -> List[str]:
        """
        Retrieve all link IDs that connect the specified source node to the target node.

        Args:
            source: Name of the source node.
            target: Name of the target node.

        Returns:
            List[str]: All link IDs where (link.source == source and link.target == target).
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
            source_regex: Regex pattern to match link.source. If None, matches all.
            target_regex: Regex pattern to match link.target. If None, matches all.
            any_direction: If True, also match links where source and target are reversed.

        Returns:
            List[Link]: A list of Link objects that match the provided criteria.
                        If both patterns are None, returns all links.
        """
        if source_regex:
            src_pat = re.compile(source_regex)
        else:
            src_pat = None
        if target_regex:
            tgt_pat = re.compile(target_regex)
        else:
            tgt_pat = None

        results = []
        for link in self.links.values():
            if src_pat and not src_pat.search(link.source):
                continue
            if tgt_pat and not tgt_pat.search(link.target):
                continue
            results.append(link)

        if any_direction:
            for link in self.links.values():
                if src_pat and not src_pat.search(link.target):
                    continue
                if tgt_pat and not tgt_pat.search(link.source):
                    continue
                results.append(link)

        return results
