"""Network topology modeling with Node, Link, RiskGroup, and Network classes."""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ngraph.algorithms.base import FlowPlacement
from ngraph.algorithms.types import FlowSummary
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.logging import get_logger
from ngraph.paths.path import Path as _NGPath
from ngraph.solver.maxflow import (
    max_flow as _solver_max_flow,
)
from ngraph.solver.maxflow import (
    max_flow_detailed as _solver_max_flow_detailed,
)
from ngraph.solver.maxflow import (
    max_flow_with_graph as _solver_max_flow_with_graph,
)
from ngraph.solver.maxflow import (
    max_flow_with_summary as _solver_max_flow_with_summary,
)
from ngraph.solver.maxflow import (
    saturated_edges as _solver_saturated_edges,
)
from ngraph.solver.maxflow import (
    sensitivity_analysis as _solver_sensitivity_analysis,
)
from ngraph.solver.paths import (
    k_shortest_paths as _solver_k_shortest_paths,
)
from ngraph.solver.paths import (
    shortest_path_costs as _solver_shortest_path_costs,
)
from ngraph.solver.paths import (
    shortest_paths as _solver_shortest_paths,
)
from ngraph.utils.ids import new_base64_uuid

LOGGER = get_logger(__name__)


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

    The model stores a single direction (``source`` -> ``target``). When building
    the working graph for analysis, a reverse edge is added by default to provide
    bidirectional connectivity. Disable with ``add_reverse=False`` in
    ``Network.to_strict_multidigraph``.

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

    def to_strict_multidigraph(
        self,
        add_reverse: bool = True,
        *,
        compact: bool = False,
    ) -> StrictMultiDiGraph:
        """Create a StrictMultiDiGraph representation of this Network.

        Only includes nodes and links that are not disabled in the scenario.
        Adds reverse edges by default so links behave bidirectionally in analysis.

        When ``compact=True``, edges receive monotonically increasing integer keys and
        only essential attributes (``capacity`` and ``cost``) are set. When
        ``compact=False``, original network link IDs are used as edge keys and also
        stored on edges as ``link_id`` for traceability, along with any custom
        link attrs.

        Args:
            add_reverse: If True, add a reverse edge for each link.
            compact: If True, omit non-essential attributes and use integer keys.

        Returns:
            StrictMultiDiGraph: Directed multigraph representation of the network.
        """
        return self._build_graph(add_reverse=add_reverse, compact=compact)

    def _build_graph(
        self,
        add_reverse: bool = True,
        excluded_nodes: Optional[AbstractSet[str]] = None,
        excluded_links: Optional[AbstractSet[str]] = None,
        *,
        compact: bool = False,
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
                if compact:
                    graph.add_node(node_name)
                else:
                    graph.add_node(node_name, **node.attrs)

        # Add enabled links
        for link_id, link in self.links.items():
            if (
                link_id not in excluded_links
                and not link.disabled
                and link.source not in all_excluded_nodes
                and link.target not in all_excluded_nodes
            ):
                if compact:
                    # Forward edge with minimal attributes
                    graph.add_edge(
                        link.source,
                        link.target,
                        capacity=link.capacity,
                        cost=link.cost,
                    )
                    if add_reverse:
                        graph.add_edge(
                            link.target,
                            link.source,
                            capacity=link.capacity,
                            cost=link.cost,
                        )
                else:
                    # Preserve original link id as attribute; edge key is assigned by graph
                    graph.add_edge(
                        link.source,
                        link.target,
                        capacity=link.capacity,
                        cost=link.cost,
                        link_id=link_id,
                        **link.attrs,
                    )
                    if add_reverse:
                        graph.add_edge(
                            link.target,
                            link.source,
                            capacity=link.capacity,
                            cost=link.cost,
                            link_id=link_id,
                            **link.attrs,
                        )

        return graph

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[Node]]:
        r"""Select and group nodes by regex on name or by attribute directive.

        There are two selection modes:

        1) Regex on node.name (default): Uses re.match(), anchored at start.
           - With capturing groups: label is "|"-joined non-None captures.
           - Without captures: label is the original pattern string.

        2) Attribute directive: If ``path`` fully matches ``attr:<name>`` where
           ``<name>`` matches ``[A-Za-z_]\w*``, nodes are grouped by the value of
           ``node.attrs[<name>]``. Nodes missing the attribute are omitted. Group
           labels are ``str(value)`` for readability. If no nodes have the
           attribute, an empty mapping is returned and a debug log entry is made.

        Args:
            path: Regex for node name, or strict attribute directive ``attr:<name>``.

        Returns:
            Mapping from group label to list of nodes.
        """
        # Strict attribute directive detection: attr:<name>
        attr_match = re.fullmatch(r"attr:([A-Za-z_]\w*)", path)
        if attr_match:
            attr_name = attr_match.group(1)
            groups_by_attr: Dict[str, List[Node]] = {}
            for node in self.nodes.values():
                if attr_name in node.attrs:
                    value = node.attrs[attr_name]
                    label = str(value)
                    groups_by_attr.setdefault(label, []).append(node)
            if not groups_by_attr:
                LOGGER.debug(
                    "Attribute directive '%s' matched no nodes (attribute missing)",
                    path,
                )
            return groups_by_attr

        # Fallback: regex over node.name
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
        """Compute maximum flow between node groups in this network.

        Args:
            source_path: Regex for selecting source nodes or ``attr:<name>``.
            sink_path: Regex for selecting sink nodes or ``attr:<name>``.
            mode: ``"combine"`` to merge all matching sources and sinks into
                one group each; ``"pairwise"`` to compute per-group pairs.
            shortest_path: If True, restrict flows to shortest paths.
            flow_placement: Strategy for splitting flow among equal-cost paths.

        Returns:
            Mapping from ``(source_label, sink_label)`` to flow values.
        """
        return _solver_max_flow(
            self,
            source_path,
            sink_path,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
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
        """Identify saturated edges in max flow solutions.

        Args:
            source_path: Regex for selecting source nodes or ``attr:<name>``.
            sink_path: Regex for selecting sink nodes or ``attr:<name>``.
            mode: ``"combine"`` or ``"pairwise"``.
            tolerance: Threshold for considering an edge saturated.
            shortest_path: If True, restrict flows to shortest paths.
            flow_placement: Strategy for splitting among equal-cost paths.

        Returns:
            Mapping from ``(source_label, sink_label)`` to lists of saturated
            edge tuples ``(u, v, key)``.
        """
        return _solver_saturated_edges(
            self,
            source_path,
            sink_path,
            mode=mode,
            tolerance=tolerance,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
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
        """Perform sensitivity analysis for capacity changes.

        Args:
            source_path: Regex for selecting source nodes or ``attr:<name>``.
            sink_path: Regex for selecting sink nodes or ``attr:<name>``.
            mode: ``"combine"`` or ``"pairwise"``.
            change_amount: Capacity change applied during analysis.
            shortest_path: If True, restrict flows to shortest paths.
            flow_placement: Strategy for splitting among equal-cost paths.

        Returns:
            Mapping from ``(source_label, sink_label)`` to per-edge sensitivity
            values, keyed by edge ``(u, v, key)``.
        """
        return _solver_sensitivity_analysis(
            self,
            source_path,
            sink_path,
            mode=mode,
            change_amount=change_amount,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )

    def max_flow_with_summary(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Tuple[float, FlowSummary]]:
        """Compute maximum flow and return per-pair analytics summary.

        Args:
            source_path: Regex for selecting source nodes or ``attr:<name>``.
            sink_path: Regex for selecting sink nodes or ``attr:<name>``.
            mode: ``"combine"`` or ``"pairwise"``.
            shortest_path: If True, restrict flows to shortest paths.
            flow_placement: Strategy for splitting among equal-cost paths.

        Returns:
            Mapping from ``(source_label, sink_label)`` to
            ``(flow_value, summary)``.
        """
        return _solver_max_flow_with_summary(
            self,
            source_path,
            sink_path,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )

    def max_flow_with_graph(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]:
        """Compute maximum flow and return flow-assigned graphs.

        Args:
            source_path: Regex for selecting source nodes or ``attr:<name>``.
            sink_path: Regex for selecting sink nodes or ``attr:<name>``.
            mode: ``"combine"`` or ``"pairwise"``.
            shortest_path: If True, restrict flows to shortest paths.
            flow_placement: Strategy for splitting among equal-cost paths.

        Returns:
            Mapping from ``(source_label, sink_label)`` to ``(flow_value, graph)``.
        """
        return _solver_max_flow_with_graph(
            self,
            source_path,
            sink_path,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )

    def max_flow_detailed(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        shortest_path: bool = False,
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    ) -> Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]:
        """Compute maximum flow with both analytics summary and graph.

        Args:
            source_path: Regex for selecting source nodes or ``attr:<name>``.
            sink_path: Regex for selecting sink nodes or ``attr:<name>``.
            mode: ``"combine"`` or ``"pairwise"``.
            shortest_path: If True, restrict flows to shortest paths.
            flow_placement: Strategy for splitting among equal-cost paths.

        Returns:
            Mapping from ``(source_label, sink_label)`` to
            ``(flow_value, summary, graph)``.
        """
        return _solver_max_flow_detailed(
            self,
            source_path,
            sink_path,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )

    def shortest_path_costs(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
    ) -> Dict[Tuple[str, str], float]:
        """Return minimal path costs between node groups in this network.

        Args:
            source_path: Regex or ``attr:<name>`` for source selection.
            sink_path: Regex or ``attr:<name>`` for sink selection.
            mode: "combine" or "pairwise".

        Returns:
            Mapping from (source_label, sink_label) to minimal cost; ``inf`` if unreachable.
        """
        return _solver_shortest_path_costs(self, source_path, sink_path, mode=mode)

    def shortest_paths(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "combine",
        *,
        split_parallel_edges: bool = False,
    ) -> Dict[Tuple[str, str], List[_NGPath]]:
        """Return concrete shortest path(s) between selected node groups.

        Args:
            source_path: Regex or ``attr:<name>`` for source selection.
            sink_path: Regex or ``attr:<name>`` for sink selection.
            mode: "combine" or "pairwise".
            split_parallel_edges: Expand parallel edges into distinct paths when True.

        Returns:
            Mapping from (source_label, sink_label) to lists of Path.
        """
        return _solver_shortest_paths(
            self,
            source_path,
            sink_path,
            mode=mode,
            split_parallel_edges=split_parallel_edges,
        )

    def k_shortest_paths(
        self,
        source_path: str,
        sink_path: str,
        mode: str = "pairwise",
        *,
        max_k: int = 3,
        max_path_cost: float = float("inf"),
        max_path_cost_factor: Optional[float] = None,
        split_parallel_edges: bool = False,
    ) -> Dict[Tuple[str, str], List[_NGPath]]:
        """Return up to K shortest paths per group pair.

        Args:
            source_path: Regex or ``attr:<name>`` for source selection.
            sink_path: Regex or ``attr:<name>`` for sink selection.
            mode: "pairwise" (default) or "combine".
            max_k: Max number of paths per pair.
            max_path_cost: Absolute cost threshold.
            max_path_cost_factor: Relative threshold versus best path.
            split_parallel_edges: Expand parallel edges into distinct paths when True.

        Returns:
            Mapping from (source_label, sink_label) to lists of Path.
        """
        return _solver_k_shortest_paths(
            self,
            source_path,
            sink_path,
            mode=mode,
            max_k=max_k,
            max_path_cost=max_path_cost,
            max_path_cost_factor=max_path_cost_factor,
            split_parallel_edges=split_parallel_edges,
        )
