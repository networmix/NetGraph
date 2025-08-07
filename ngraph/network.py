"""Network topology modeling with Node, Link, RiskGroup, and Network classes."""

from __future__ import annotations

import base64
import re
import uuid
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.algorithms.max_flow import (
    calc_max_flow,
    run_sensitivity,
    saturated_edges,
)
from ngraph.lib.algorithms.types import FlowSummary
from ngraph.lib.graph import StrictMultiDiGraph


def new_base64_uuid() -> str:
    """Generate a Base64-encoded, URL-safe UUID (22 characters, no padding).

    Returns:
        str: A 22-character Base64 URL-safe string with trailing '=' removed.
    """
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


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
    """Represents a directed link between two nodes in the network.

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
        """Generate the link's unique ID upon initialization."""
        self.id = f"{self.source}|{self.target}|{new_base64_uuid()}"


@dataclass
class RiskGroup:
    """Represents a shared-risk or failure domain, which may have nested children.

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


@dataclass
class Network:
    """A container for network nodes and links.

    Network represents the scenario-level topology with persistent state (nodes/links
    that are disabled in the scenario configuration). For temporary exclusion of
    nodes/links during analysis (e.g., failure simulation), use NetworkView instead
    of modifying the Network's disabled states.

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
        """Add a node to the network (keyed by node.name).

        Args:
            node (Node): Node to add.

        Raises:
            ValueError: If a node with the same name already exists.
        """
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists in the network.")
        self.nodes[node.name] = node

    def add_link(self, link: Link) -> None:
        """Add a link to the network (keyed by the link's auto-generated ID).

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
        """Create a StrictMultiDiGraph representation of this Network.

        Only includes nodes and links that are not disabled in the scenario.
        Optionally adds reverse edges.

        Args:
            add_reverse (bool): If True, also add a reverse edge for each link.

        Returns:
            StrictMultiDiGraph: A directed multigraph representation of the network.
        """
        return self._build_graph(add_reverse=add_reverse)

    def _build_graph(
        self,
        add_reverse: bool = True,
        excluded_nodes: Optional[AbstractSet[str]] = None,
        excluded_links: Optional[AbstractSet[str]] = None,
    ) -> StrictMultiDiGraph:
        """Create a StrictMultiDiGraph with optional exclusions.

        Args:
            add_reverse: If True, add reverse edges for each link.
            excluded_nodes: Additional nodes to exclude beyond disabled ones.
            excluded_links: Additional links to exclude beyond disabled ones.

        Returns:
            StrictMultiDiGraph with specified exclusions applied.
        """
        if excluded_nodes is None:
            excluded_nodes = set()
        if excluded_links is None:
            excluded_links = set()

        graph = StrictMultiDiGraph()

        # Collect all nodes to exclude (scenario-disabled + analysis exclusions)
        all_excluded_nodes = excluded_nodes | {
            name for name, nd in self.nodes.items() if nd.disabled
        }

        # Add enabled nodes
        for node_name, node in self.nodes.items():
            if node_name not in all_excluded_nodes:
                graph.add_node(node_name, **node.attrs)

        # Add enabled links
        for link_id, link in self.links.items():
            if (
                link_id not in excluded_links
                and not link.disabled
                and link.source not in all_excluded_nodes
                and link.target not in all_excluded_nodes
            ):
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
        """Select and group nodes using a regex pattern or attribute directive.

        If ``path`` begins with ``"attr:"``, the remainder specifies an attribute
        name. Nodes are grouped by the value of this attribute; nodes without the
        attribute are ignored. Otherwise, ``path`` is treated as a regular
        expression anchored at the start of each node name. If the pattern
        includes capturing groups, the group label joins captures with ``"|"``.
        Without capturing groups, the label is the pattern string itself.

        Args:
            path: Regular expression pattern or ``"attr:<name>"`` directive.

        Returns:
            Mapping from group label to list of matching nodes.
        """
        if path.startswith("attr:"):
            attr_name = path[5:]
            groups_map: Dict[str, List[Node]] = {}
            for node in self.nodes.values():
                value = node.attrs.get(attr_name)
                if value is not None:
                    label = str(value)
                    groups_map.setdefault(label, []).append(node)
            return groups_map

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
        """Compute maximum flow between groups of source nodes and sink nodes.

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
        return self._max_flow_internal(
            self, source_path, sink_path, mode, shortest_path, flow_placement
        )

    def _max_flow_internal(
        self,
        context: Any,  # Network or NetworkView
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: Optional[FlowPlacement] = None,
    ) -> Dict[Tuple[str, str], float]:
        """Internal max flow computation that works with Network or NetworkView."""
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        src_groups = context.select_node_groups_by_path(source_path)
        snk_groups = context.select_node_groups_by_path(sink_path)

        if not src_groups:
            raise ValueError(f"No source nodes found matching '{source_path}'.")
        if not snk_groups:
            raise ValueError(f"No sink nodes found matching '{sink_path}'.")

        # Build the graph once for all computations
        base_graph = context.to_strict_multidigraph()

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

            # Check for overlapping nodes in combined mode
            combined_src_names = {node.name for node in combined_src_nodes}
            combined_snk_names = {node.name for node in combined_snk_nodes}
            if combined_src_names & combined_snk_names:
                flow_val = 0.0
            else:
                flow_val = self._compute_flow_single_group(
                    combined_src_nodes,
                    combined_snk_nodes,
                    shortest_path,
                    flow_placement,
                    prebuilt_graph=base_graph,
                )
            return {(combined_src_label, combined_snk_label): flow_val}

        elif mode == "pairwise":
            results: Dict[Tuple[str, str], float] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        src_names = {node.name for node in src_nodes}
                        snk_names = {node.name for node in snk_nodes}
                        if src_names & snk_names:
                            flow_val = 0.0
                        else:
                            flow_val = self._compute_flow_single_group(
                                src_nodes,
                                snk_nodes,
                                shortest_path,
                                flow_placement,
                                prebuilt_graph=base_graph,
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
        prebuilt_graph: Optional[StrictMultiDiGraph] = None,
    ) -> float:
        """Attach a pseudo-source and pseudo-sink to the provided node lists,
        then run calc_max_flow. Returns the resulting flow from all
        sources to all sinks as a single float.

        Scenario-disabled nodes are excluded from flow computation.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            shortest_path (bool): If True, restrict flows to shortest paths only.
            flow_placement (Optional[FlowPlacement]): Strategy for placing flow among
                parallel equal-cost paths. If None, defaults to FlowPlacement.PROPORTIONAL.
            prebuilt_graph (Optional[StrictMultiDiGraph]): If provided, use this graph
                instead of creating a new one. The graph will be copied to avoid modification.

        Returns:
            float: The computed max flow value, or 0.0 if no active sources or sinks.
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            return 0.0

        # Use prebuilt graph if provided, otherwise create new one
        if prebuilt_graph is not None:
            graph = prebuilt_graph.copy()
        else:
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

    def _compute_flow_with_summary_single_group(
        self,
        sources: List[Node],
        sinks: List[Node],
        shortest_path: bool,
        flow_placement: Optional[FlowPlacement],
    ) -> Tuple[float, FlowSummary]:
        """Compute maximum flow with detailed analytics summary for a single group.

        Creates pseudo-source and pseudo-sink nodes, connects them to the provided
        source and sink nodes, then computes the maximum flow along with a detailed
        FlowSummary containing edge flows, residual capacities, and min-cut analysis.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            shortest_path (bool): If True, restrict flows to shortest paths only.
            flow_placement (Optional[FlowPlacement]): Strategy for placing flow among
                parallel equal-cost paths. If None, defaults to FlowPlacement.PROPORTIONAL.

        Returns:
            Tuple[float, FlowSummary]: A tuple containing:
                - float: The computed maximum flow value
                - FlowSummary: Detailed analytics including edge flows, residual capacities,
                  reachable nodes, and min-cut edges
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            empty_summary = FlowSummary(
                total_flow=0.0,
                edge_flow={},
                residual_cap={},
                reachable=set(),
                min_cut=[],
                cost_distribution={},
            )
            return 0.0, empty_summary

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
            return_summary=True,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )

    def _compute_flow_with_graph_single_group(
        self,
        sources: List[Node],
        sinks: List[Node],
        shortest_path: bool,
        flow_placement: Optional[FlowPlacement],
    ) -> Tuple[float, StrictMultiDiGraph]:
        """Compute maximum flow with flow-assigned graph for a single group.

        Creates pseudo-source and pseudo-sink nodes, connects them to the provided
        source and sink nodes, then computes the maximum flow and returns both the
        flow value and the graph with flow assignments on edges.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            shortest_path (bool): If True, restrict flows to shortest paths only.
            flow_placement (Optional[FlowPlacement]): Strategy for placing flow among
                parallel equal-cost paths. If None, defaults to FlowPlacement.PROPORTIONAL.

        Returns:
            Tuple[float, StrictMultiDiGraph]: A tuple containing:
                - float: The computed maximum flow value
                - StrictMultiDiGraph: The graph with flow assignments on edges, including
                  the pseudo-source and pseudo-sink nodes
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            base_graph = self.to_strict_multidigraph()
            return 0.0, base_graph

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
            return_graph=True,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )

    def _compute_flow_detailed_single_group(
        self,
        sources: List[Node],
        sinks: List[Node],
        shortest_path: bool,
        flow_placement: Optional[FlowPlacement],
    ) -> Tuple[float, FlowSummary, StrictMultiDiGraph]:
        """Compute maximum flow with complete analytics and graph.

        Returns flow values, detailed analytics summary, and flow-assigned graphs.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): How parallel equal-cost paths are handled.

        Returns:
            Tuple[float, FlowSummary, StrictMultiDiGraph]:
                Mapping from (src_label, snk_label) to (flow_value, summary, flow_graph) tuples.

        Raises:
            ValueError: If no matching source or sink groups found, or invalid mode.
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            base_graph = self.to_strict_multidigraph()
            empty_summary = FlowSummary(
                total_flow=0.0,
                edge_flow={},
                residual_cap={},
                reachable=set(),
                min_cut=[],
                cost_distribution={},
            )
            return 0.0, empty_summary, base_graph

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
            return_summary=True,
            return_graph=True,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )

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
        """Retrieve all link IDs that connect the specified source node
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
        """Search for links using optional regex patterns for source or target node names.

        Args:
            source_regex (Optional[str]): Regex to match link.source. If None, matches all sources.
            target_regex (Optional[str]): Regex to match link.target. If None, matches all targets.
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
        """Disable all nodes/links that have 'name' in their risk_groups.
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
        """Enable all nodes/links that have 'name' in their risk_groups.
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

    def saturated_edges(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        tolerance: float = 1e-10,
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], List[Tuple[str, str, str]]]:
        """Identify saturated (bottleneck) edges in max flow solutions between node groups.

        Returns a dictionary mapping (source_label, sink_label) to lists of saturated edge tuples.

        Args:
            source_path (str): Regex pattern for selecting source nodes.
            sink_path (str): Regex pattern for selecting sink nodes.
            mode (str): Either "combine" or "pairwise".
                - "combine": Treat all matched sources as one group,
                  and all matched sinks as one group. Returns a single entry.
                - "pairwise": Compute flow for each (source_group, sink_group) pair.
            tolerance (float): Tolerance for considering an edge saturated.
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): Determines how parallel equal-cost paths
                are handled.

        Returns:
            Dict[Tuple[str, str], List[Tuple[str, str, str]]]: Mapping from
                (src_label, snk_label) to lists of saturated edge tuples (u, v, key).

        Raises:
            ValueError: If no matching source or sink groups are found, or invalid mode.
        """
        return self._saturated_edges_internal(
            self, source_path, sink_path, mode, tolerance, shortest_path, flow_placement
        )

    def sensitivity_analysis(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        change_amount: float = 1.0,
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]:
        """Perform sensitivity analysis on capacity changes for max flow solutions.

        Tests changing each saturated edge capacity by change_amount and measures
        the resulting change in total flow.

        Args:
            source_path (str): Regex pattern for selecting source nodes.
            sink_path (str): Regex pattern for selecting sink nodes.
            mode (str): Either "combine" or "pairwise".
                - "combine": Treat all matched sources as one group,
                  and all matched sinks as one group. Returns a single entry.
                - "pairwise": Compute flow for each (source_group, sink_group) pair.
            change_amount (float): Amount to change capacity for testing
                (positive=increase, negative=decrease).
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): Determines how parallel equal-cost paths
                are handled.

        Returns:
            Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]: Mapping from
                (src_label, snk_label) to dictionaries of edge sensitivity values.
                Each inner dict maps edge tuples (u, v, key) to flow change values.

        Raises:
            ValueError: If no matching source or sink groups are found, or invalid mode.
        """
        return self._sensitivity_analysis_internal(
            self,
            source_path,
            sink_path,
            mode,
            change_amount,
            shortest_path,
            flow_placement,
        )

    def _saturated_edges_internal(
        self,
        context: Any,  # Network or NetworkView
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        tolerance: float = 1e-10,
        shortest_path: bool = False,
        flow_placement: Optional[FlowPlacement] = None,
    ) -> Dict[Tuple[str, str], List[Tuple[str, str, str]]]:
        """Internal saturated edges computation that works with Network or NetworkView."""
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        src_groups = context.select_node_groups_by_path(source_path)
        snk_groups = context.select_node_groups_by_path(sink_path)

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
                return {(combined_src_label, combined_snk_label): []}

            # Check for overlapping nodes in combined mode
            combined_src_names = {node.name for node in combined_src_nodes}
            combined_snk_names = {node.name for node in combined_snk_nodes}
            if combined_src_names & combined_snk_names:
                saturated_list = []
            else:
                saturated_list = self._compute_saturated_edges_single_group(
                    combined_src_nodes,
                    combined_snk_nodes,
                    tolerance,
                    shortest_path,
                    flow_placement,
                )
            return {(combined_src_label, combined_snk_label): saturated_list}

        elif mode == "pairwise":
            results: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        src_names = {node.name for node in src_nodes}
                        snk_names = {node.name for node in snk_nodes}
                        if src_names & snk_names:
                            saturated_list = []
                        else:
                            saturated_list = self._compute_saturated_edges_single_group(
                                src_nodes,
                                snk_nodes,
                                tolerance,
                                shortest_path,
                                flow_placement,
                            )
                    else:
                        saturated_list = []
                    results[(src_label, snk_label)] = saturated_list
            return results

        else:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")

    def _compute_saturated_edges_single_group(
        self,
        sources: List[Node],
        sinks: List[Node],
        tolerance: float,
        shortest_path: bool,
        flow_placement: Optional[FlowPlacement],
    ) -> List[Tuple[str, str, str]]:
        """Compute saturated edges for a single group of sources and sinks.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            tolerance (float): Tolerance for considering an edge saturated.
            shortest_path (bool): If True, restrict flows to shortest paths only.
            flow_placement (Optional[FlowPlacement]): Strategy for placing flow among
                parallel equal-cost paths.

        Returns:
            List[Tuple[str, str, str]]: List of saturated edge tuples (u, v, key).
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            return []

        graph = self.to_strict_multidigraph()
        graph.add_node("source")
        graph.add_node("sink")

        # Connect pseudo-source to active sources
        for src_node in active_sources:
            graph.add_edge("source", src_node.name, capacity=float("inf"), cost=0)

        # Connect active sinks to pseudo-sink
        for sink_node in active_sinks:
            graph.add_edge(sink_node.name, "sink", capacity=float("inf"), cost=0)

        return saturated_edges(
            graph,
            "source",
            "sink",
            tolerance=tolerance,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )

    def _compute_sensitivity_single_group(
        self,
        sources: List[Node],
        sinks: List[Node],
        change_amount: float,
        shortest_path: bool,
        flow_placement: Optional[FlowPlacement],
    ) -> Dict[Tuple[str, str, str], float]:
        """Compute sensitivity analysis for a single group of sources and sinks.

        Args:
            sources (List[Node]): List of source nodes.
            sinks (List[Node]): List of sink nodes.
            change_amount (float): Amount to change capacity for testing.
            shortest_path (bool): If True, restrict flows to shortest paths only.
            flow_placement (Optional[FlowPlacement]): Strategy for placing flow among
                parallel equal-cost paths.

        Returns:
            Dict[Tuple[str, str, str], float]: Mapping from edge tuples to flow changes.
        """
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        active_sources = [s for s in sources if not s.disabled]
        active_sinks = [s for s in sinks if not s.disabled]

        if not active_sources or not active_sinks:
            return {}

        graph = self.to_strict_multidigraph()
        graph.add_node("source")
        graph.add_node("sink")

        # Connect pseudo-source to active sources
        for src_node in active_sources:
            graph.add_edge("source", src_node.name, capacity=float("inf"), cost=0)

        # Connect active sinks to pseudo-sink
        for sink_node in active_sinks:
            graph.add_edge(sink_node.name, "sink", capacity=float("inf"), cost=0)

        return run_sensitivity(
            graph,
            "source",
            "sink",
            change_amount=change_amount,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
            copy_graph=False,
        )

    def _sensitivity_analysis_internal(
        self,
        context: Any,  # Network or NetworkView
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        change_amount: float = 1.0,
        shortest_path: bool = False,
        flow_placement: Optional[FlowPlacement] = None,
    ) -> Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]:
        """Internal sensitivity analysis computation that works with Network or NetworkView."""
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        src_groups = context.select_node_groups_by_path(source_path)
        snk_groups = context.select_node_groups_by_path(sink_path)

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
                return {(combined_src_label, combined_snk_label): {}}

            # Check for overlapping nodes in combined mode
            combined_src_names = {node.name for node in combined_src_nodes}
            combined_snk_names = {node.name for node in combined_snk_nodes}
            if combined_src_names & combined_snk_names:
                sensitivity_dict = {}
            else:
                sensitivity_dict = self._compute_sensitivity_single_group(
                    combined_src_nodes,
                    combined_snk_nodes,
                    change_amount,
                    shortest_path,
                    flow_placement,
                )
            return {(combined_src_label, combined_snk_label): sensitivity_dict}

        elif mode == "pairwise":
            results: Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        src_names = {node.name for node in src_nodes}
                        snk_names = {node.name for node in snk_nodes}
                        if src_names & snk_names:
                            sensitivity_dict = {}
                        else:
                            sensitivity_dict = self._compute_sensitivity_single_group(
                                src_nodes,
                                snk_nodes,
                                change_amount,
                                shortest_path,
                                flow_placement,
                            )
                    else:
                        sensitivity_dict = {}
                    results[(src_label, snk_label)] = sensitivity_dict
            return results

        else:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")

    def max_flow_with_summary(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Tuple[float, FlowSummary]]:
        """Compute maximum flow with detailed analytics summary.

        Returns both flow values and FlowSummary objects containing detailed
        analytics including edge flows, residual capacities, and min-cut analysis.

        Args:
            source_path (str): Regex pattern for selecting source nodes.
            sink_path (str): Regex pattern for selecting sink nodes.
            mode (str): Either "combine" or "pairwise".
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): How parallel equal-cost paths are handled.

        Returns:
            Dict[Tuple[str, str], Tuple[float, FlowSummary]]: Mapping from
                (src_label, snk_label) to (flow_value, summary) tuples.

        Raises:
            ValueError: If no matching source or sink groups found, or invalid mode.
        """
        return self._max_flow_with_summary_internal(
            self, source_path, sink_path, mode, shortest_path, flow_placement
        )

    def _max_flow_with_summary_internal(
        self,
        context: Any,  # Network or NetworkView
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: Optional[FlowPlacement] = None,
    ) -> Dict[Tuple[str, str], Tuple[float, FlowSummary]]:
        """Internal max flow with summary computation that works with Network or NetworkView."""
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        src_groups = context.select_node_groups_by_path(source_path)
        snk_groups = context.select_node_groups_by_path(sink_path)

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
                empty_summary = FlowSummary(
                    total_flow=0.0,
                    edge_flow={},
                    residual_cap={},
                    reachable=set(),
                    min_cut=[],
                    cost_distribution={},
                )
                return {(combined_src_label, combined_snk_label): (0.0, empty_summary)}

            # Check for overlapping nodes in combined mode
            combined_src_names = {node.name for node in combined_src_nodes}
            combined_snk_names = {node.name for node in combined_snk_nodes}
            if combined_src_names & combined_snk_names:
                empty_summary = FlowSummary(
                    total_flow=0.0,
                    edge_flow={},
                    residual_cap={},
                    reachable=set(),
                    min_cut=[],
                    cost_distribution={},
                )
                return {(combined_src_label, combined_snk_label): (0.0, empty_summary)}
            else:
                flow_val, summary = self._compute_flow_with_summary_single_group(
                    combined_src_nodes,
                    combined_snk_nodes,
                    shortest_path,
                    flow_placement,
                )
            return {(combined_src_label, combined_snk_label): (flow_val, summary)}

        elif mode == "pairwise":
            results: Dict[Tuple[str, str], Tuple[float, FlowSummary]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        src_names = {node.name for node in src_nodes}
                        snk_names = {node.name for node in snk_nodes}
                        if src_names & snk_names:
                            empty_summary = FlowSummary(
                                total_flow=0.0,
                                edge_flow={},
                                residual_cap={},
                                reachable=set(),
                                min_cut=[],
                                cost_distribution={},
                            )
                            flow_val, summary = 0.0, empty_summary
                        else:
                            flow_val, summary = (
                                self._compute_flow_with_summary_single_group(
                                    src_nodes, snk_nodes, shortest_path, flow_placement
                                )
                            )
                    else:
                        empty_summary = FlowSummary(
                            total_flow=0.0,
                            edge_flow={},
                            residual_cap={},
                            reachable=set(),
                            min_cut=[],
                            cost_distribution={},
                        )
                        flow_val, summary = 0.0, empty_summary
                    results[(src_label, snk_label)] = (flow_val, summary)
            return results

        else:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")

    def max_flow_with_graph(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]:
        """Compute maximum flow and return the flow-assigned graph.

        Returns both flow values and the modified graphs containing flow assignments.

        Args:
            source_path (str): Regex pattern for selecting source nodes.
            sink_path (str): Regex pattern for selecting sink nodes.
            mode (str): Either "combine" or "pairwise".
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): How parallel equal-cost paths are handled.

        Returns:
            Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]: Mapping from
                (src_label, snk_label) to (flow_value, flow_graph) tuples.

        Raises:
            ValueError: If no matching source or sink groups found, or invalid mode.
        """
        return self._max_flow_with_graph_internal(
            self, source_path, sink_path, mode, shortest_path, flow_placement
        )

    def _max_flow_with_graph_internal(
        self,
        context: Any,  # Network or NetworkView
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: Optional[FlowPlacement] = None,
    ) -> Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]:
        """Internal max flow with graph computation that works with Network or NetworkView."""
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        src_groups = context.select_node_groups_by_path(source_path)
        snk_groups = context.select_node_groups_by_path(sink_path)

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
                base_graph = context.to_strict_multidigraph()
                return {(combined_src_label, combined_snk_label): (0.0, base_graph)}

            # Check for overlapping nodes in combined mode
            combined_src_names = {node.name for node in combined_src_nodes}
            combined_snk_names = {node.name for node in combined_snk_nodes}
            if combined_src_names & combined_snk_names:
                base_graph = context.to_strict_multidigraph()
                return {(combined_src_label, combined_snk_label): (0.0, base_graph)}
            else:
                flow_val, flow_graph = self._compute_flow_with_graph_single_group(
                    combined_src_nodes,
                    combined_snk_nodes,
                    shortest_path,
                    flow_placement,
                )
            return {(combined_src_label, combined_snk_label): (flow_val, flow_graph)}

        elif mode == "pairwise":
            results: Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        src_names = {node.name for node in src_nodes}
                        snk_names = {node.name for node in snk_nodes}
                        if src_names & snk_names:
                            base_graph = context.to_strict_multidigraph()
                            flow_val, flow_graph = 0.0, base_graph
                        else:
                            flow_val, flow_graph = (
                                self._compute_flow_with_graph_single_group(
                                    src_nodes, snk_nodes, shortest_path, flow_placement
                                )
                            )
                    else:
                        base_graph = context.to_strict_multidigraph()
                        flow_val, flow_graph = 0.0, base_graph
                    results[(src_label, snk_label)] = (flow_val, flow_graph)
            return results

        else:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")

    def max_flow_detailed(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]:
        """Compute maximum flow with complete analytics and graph.

        Returns flow values, detailed analytics summary, and flow-assigned graphs.

        Args:
            source_path (str): Regex pattern for selecting source nodes.
            sink_path (str): Regex pattern for selecting sink nodes.
            mode (str): Either "combine" or "pairwise".
            shortest_path (bool): If True, flows are constrained to shortest paths.
            flow_placement (FlowPlacement): How parallel equal-cost paths are handled.

        Returns:
            Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]:
                Mapping from (src_label, snk_label) to (flow_value, summary, flow_graph) tuples.

        Raises:
            ValueError: If no matching source or sink groups found, or invalid mode.
        """
        return self._max_flow_detailed_internal(
            self, source_path, sink_path, mode, shortest_path, flow_placement
        )

    def _max_flow_detailed_internal(
        self,
        context: Any,  # Network or NetworkView
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: Optional[FlowPlacement] = None,
    ) -> Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]:
        """Internal max flow detailed computation that works with Network or NetworkView."""
        if flow_placement is None:
            flow_placement = FlowPlacement.PROPORTIONAL

        src_groups = context.select_node_groups_by_path(source_path)
        snk_groups = context.select_node_groups_by_path(sink_path)

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
                base_graph = context.to_strict_multidigraph()
                empty_summary = FlowSummary(
                    total_flow=0.0,
                    edge_flow={},
                    residual_cap={},
                    reachable=set(),
                    min_cut=[],
                    cost_distribution={},
                )
                return {
                    (combined_src_label, combined_snk_label): (
                        0.0,
                        empty_summary,
                        base_graph,
                    )
                }

            # Check for overlapping nodes in combined mode
            combined_src_names = {node.name for node in combined_src_nodes}
            combined_snk_names = {node.name for node in combined_snk_nodes}
            if combined_src_names & combined_snk_names:
                base_graph = context.to_strict_multidigraph()
                empty_summary = FlowSummary(
                    total_flow=0.0,
                    edge_flow={},
                    residual_cap={},
                    reachable=set(),
                    min_cut=[],
                    cost_distribution={},
                )
                return {
                    (combined_src_label, combined_snk_label): (
                        0.0,
                        empty_summary,
                        base_graph,
                    )
                }
            else:
                flow_val, summary, flow_graph = (
                    self._compute_flow_detailed_single_group(
                        combined_src_nodes,
                        combined_snk_nodes,
                        shortest_path,
                        flow_placement,
                    )
                )
            return {
                (combined_src_label, combined_snk_label): (
                    flow_val,
                    summary,
                    flow_graph,
                )
            }

        elif mode == "pairwise":
            results: Dict[
                Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]
            ] = {}
            for src_label, src_nodes in src_groups.items():
                for snk_label, snk_nodes in snk_groups.items():
                    if src_nodes and snk_nodes:
                        src_names = {node.name for node in src_nodes}
                        snk_names = {node.name for node in snk_nodes}
                        if src_names & snk_names:
                            base_graph = context.to_strict_multidigraph()
                            empty_summary = FlowSummary(
                                total_flow=0.0,
                                edge_flow={},
                                residual_cap={},
                                reachable=set(),
                                min_cut=[],
                                cost_distribution={},
                            )
                            flow_val, summary, flow_graph = (
                                0.0,
                                empty_summary,
                                base_graph,
                            )
                        else:
                            flow_val, summary, flow_graph = (
                                self._compute_flow_detailed_single_group(
                                    src_nodes, snk_nodes, shortest_path, flow_placement
                                )
                            )
                    else:
                        base_graph = context.to_strict_multidigraph()
                        empty_summary = FlowSummary(
                            total_flow=0.0,
                            edge_flow={},
                            residual_cap={},
                            reachable=set(),
                            min_cut=[],
                            cost_distribution={},
                        )
                        flow_val, summary, flow_graph = 0.0, empty_summary, base_graph
                    results[(src_label, snk_label)] = (flow_val, summary, flow_graph)
            return results

        else:
            raise ValueError(f"Invalid mode '{mode}'. Must be 'combine' or 'pairwise'.")
