"""Hierarchical exploration of a Network.

Builds a tree of the node-name hierarchy and aggregates per-subtree
statistics in two modes (all nodes, and enabled nodes only): node and link
counts, capacity, capex/power, and hardware bills of materials (BOM).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from ngraph.hardware import HardwareUse, hardware_inventory, link_active
from ngraph.logging import get_logger
from ngraph.model.components import ComponentsLibrary
from ngraph.model.network import Network, Node
from ngraph.utils.values import flag

logger = get_logger(__name__)


@dataclass
class ExternalLinkBreakdown:
    """Stats for external links to one other subtree.

    Attributes:
        link_count (int): Number of links to that other subtree.
        link_capacity (float): Sum of capacities for those links.
    """

    link_count: int = 0
    link_capacity: float = 0.0


@dataclass
class TreeStats:
    """Aggregated statistics for a single tree node (subtree).

    Attributes:
        node_count (int): Total number of nodes in this subtree.
        internal_link_count (int): Number of internal links in this subtree.
        internal_link_capacity (float): Sum of capacities for those internal links.
        external_link_count (int): Number of external links from this subtree to another.
        external_link_capacity (float): Sum of capacities for those external links.
        external_link_details (Dict[str, ExternalLinkBreakdown]): Breakdown by other subtree path.
        total_capex (float): Total capex (nodes + links).
        total_power (float): Total power (nodes + links).
        bom (Dict[str, float]): Hardware count per component name. Shared
            optics can add fractional counts.
    """

    node_count: int = 0

    internal_link_count: int = 0
    internal_link_capacity: float = 0.0

    external_link_count: int = 0
    external_link_capacity: float = 0.0

    external_link_details: Dict[str, ExternalLinkBreakdown] = field(
        default_factory=dict
    )

    total_capex: float = 0.0
    total_power: float = 0.0
    bom: Dict[str, float] = field(default_factory=dict)


@dataclass
class NodeUtilization:
    """Per-node hardware utilization snapshot based on active topology.

    Attributes:
        node_name: Fully qualified node name.
        component_name: Hardware component name if present.
        hw_count: Hardware multiplicity used for capacity/power scaling.
        capacity_supported: Total capacity supported by node hardware.
        attached_capacity_active: Sum of capacities of enabled adjacent links where the
            opposite endpoint is also enabled.
        capacity_utilization: Ratio of attached to supported capacity (0.0 when N/A).
        ports_available: Total port equivalents available on the node (0.0 when N/A).
        ports_used: Sum of port equivalents used by per-end link optics attached to this
            node on active links.
        ports_utilization: Ratio of used to available ports (0.0 when N/A).
        capacity_violation: True if attached capacity exceeds supported capacity.
        ports_violation: True if used ports exceed available ports.
    """

    node_name: str
    component_name: Optional[str]
    hw_count: float
    capacity_supported: float
    attached_capacity_active: float
    capacity_utilization: float
    ports_available: float
    ports_used: float
    ports_utilization: float
    capacity_violation: bool
    ports_violation: bool


@dataclass
class LinkCapacityIssue:
    """A link capacity constraint violation in active topology.

    Attributes:
        source: Source node name.
        target: Target node name.
        capacity: Configured link capacity.
        limit: Effective capacity limit from per-end hardware (min of ends).
        reason: Machine-readable tag, e.g. ``link_capacity_exceeds_end_hw``.
    """

    source: str
    target: str
    capacity: float
    limit: float
    reason: str


@dataclass(eq=False)
class TreeNode:
    """A node in the hierarchical tree.

    Attributes:
        name (str): Hierarchy segment, e.g. "plane1" in "dc1/plane1/ssw".
        parent (Optional[TreeNode]): Parent tree node; None for the root.
        children (Dict[str, TreeNode]): Mapping of child name -> child TreeNode.
        subtree_nodes (Set[str]): Node names in the subtree, disabled included.
        active_subtree_nodes (Set[str]): Node names in the subtree (only enabled).
        stats (TreeStats): Aggregated stats for "all" view.
        active_stats (TreeStats): Aggregated stats for "active" (only enabled) view.
        raw_nodes (List[Node]): Network nodes whose full name ends at this tree node.
    """

    name: str
    parent: Optional[TreeNode] = None

    children: Dict[str, TreeNode] = field(default_factory=dict)

    # "All" includes disabled nodes; "Active" excludes them.
    subtree_nodes: Set[str] = field(default_factory=set)
    active_subtree_nodes: Set[str] = field(default_factory=set)

    stats: TreeStats = field(default_factory=TreeStats)
    active_stats: TreeStats = field(default_factory=TreeStats)

    raw_nodes: List[Node] = field(default_factory=list)

    def __hash__(self) -> int:
        # Keep identity-based hashing so each node is unique in sets/dicts.
        return id(self)

    def add_child(self, child_name: str) -> TreeNode:
        """Return the child named ``child_name``, creating it if missing."""
        if child_name not in self.children:
            child_node = TreeNode(name=child_name, parent=self)
            self.children[child_name] = child_node
        return self.children[child_name]

    def is_leaf(self) -> bool:
        """Return True if this node has no children."""
        return len(self.children) == 0


class NetworkExplorer:
    """Hierarchical view of a Network with per-subtree statistics.

    Statistics are computed in two modes: 'all' (disabled nodes and links
    included) and 'active' (enabled only).
    """

    def __init__(
        self,
        network: Network,
        components_library: Optional[ComponentsLibrary] = None,
        strict_validation: bool = True,
    ) -> None:
        if not isinstance(network, Network):
            raise TypeError(
                f"NetworkExplorer.network: expected Network, got {network!r}"
            )
        if components_library is not None and not isinstance(
            components_library, ComponentsLibrary
        ):
            raise TypeError(
                "NetworkExplorer.components_library: expected ComponentsLibrary or None, "
                f"got {components_library!r}"
            )
        self.network = network
        self.components_library = (
            ComponentsLibrary() if components_library is None else components_library
        )
        self.strict_validation = flag(
            strict_validation, "NetworkExplorer.strict_validation"
        )

        self.root_node: Optional[TreeNode] = None

        self._node_map: Dict[str, TreeNode] = {}  # node_name -> deepest TreeNode
        self._path_map: Dict[str, TreeNode] = {}  # path -> TreeNode
        self._node_path_map: Dict[TreeNode, str] = {}  # TreeNode -> path

        self._ancestors_cache: Dict[TreeNode, Set[TreeNode]] = {}

        # Validation/utilization artifacts (filled during statistics computation)
        self._node_utilization: Dict[str, NodeUtilization] = {}
        self._link_issues: List[LinkCapacityIssue] = []

    @classmethod
    def explore_network(
        cls,
        network: Network,
        components_library: Optional[ComponentsLibrary] = None,
        strict_validation: bool = True,
    ) -> NetworkExplorer:
        """Build the hierarchy tree and compute 'all' and 'active' statistics.

        Statistics include hardware bills of materials (BOM):

        - stats.bom: counts by component for all nodes and links, disabled included
        - active_stats.bom: counts by component for the enabled topology only

        Shared optics add fractional counts; exclusive link ends are rounded up
        per link. Counts are float sums in inventory order: integer counts are
        exact while a total stays at most 2^53.

        Args:
            network: Network to explore.
            components_library: Component definitions for hardware lookups.
                None uses an empty library.
            strict_validation: When True, raise on capacity/ports violations; when False,
                record issues and continue (used by ``ngraph inspect``).

        Returns:
            The populated explorer.

        Raises:
            ValueError: On a node capacity, port, or link capacity violation
                when ``strict_validation`` is True.
        """
        instance = cls(network, components_library, strict_validation=strict_validation)

        instance.root_node = instance._build_hierarchy_tree()
        instance._compute_subtree_sets_all(instance.root_node)
        instance._compute_subtree_sets_active(instance.root_node)
        # Statistics read the subtree sets and these maps, so they run last.
        instance._build_node_map(instance.root_node)
        instance._build_path_map(instance.root_node)
        instance._compute_statistics()

        return instance

    def _build_hierarchy_tree(self) -> TreeNode:
        """Build the tree by splitting node names on '/'.

        Example: "dc1/plane1/ssw/ssw-1" => root/dc1/plane1/ssw/ssw-1
        """
        root = TreeNode(name="root")
        for nd in self.network.nodes.values():
            path_parts = nd.name.split("/")
            current = root
            for part in path_parts:
                current = current.add_child(part)
            current.raw_nodes.append(nd)
        return root

    def _compute_subtree_sets_all(self, node: TreeNode) -> Set[str]:
        """Fill ``subtree_nodes`` bottom-up with every node name, disabled included."""
        collected = set()
        for child in node.children.values():
            collected |= self._compute_subtree_sets_all(child)
        for nd in node.raw_nodes:
            collected.add(nd.name)
        node.subtree_nodes = collected
        return collected

    def _compute_subtree_sets_active(self, node: TreeNode) -> Set[str]:
        """Fill ``active_subtree_nodes`` bottom-up with enabled node names."""
        collected = set()
        for child in node.children.values():
            collected |= self._compute_subtree_sets_active(child)
        for nd in node.raw_nodes:
            if not nd.disabled:
                collected.add(nd.name)
        node.active_subtree_nodes = collected
        return collected

    def _build_node_map(self, node: TreeNode) -> None:
        """Assign each node's name to the *deepest* TreeNode that holds it.

        Walks parents before children so a child TreeNode overrides its
        parent's claim on a name.
        """
        for nd in node.raw_nodes:
            self._node_map[nd.name] = node

        for child in node.children.values():
            self._build_node_map(child)

    def _build_path_map(self, node: TreeNode) -> None:
        """Build path<->TreeNode maps, omitting the synthetic root from paths."""
        path_str = self._compute_full_path(node)
        self._path_map[path_str] = node
        self._node_path_map[node] = path_str
        for child in node.children.values():
            self._build_path_map(child)

    def _compute_full_path(self, node: TreeNode) -> str:
        """Return a '/'-joined path, omitting the synthetic root node.

        The walk stops at the tree root by parent identity, so hierarchy
        segments that happen to be named "root" are preserved in paths.
        """
        parts = []
        current = node
        while current is not None and current.parent is not None:
            parts.append(current.name)
            current = current.parent
        return "/".join(reversed(parts))

    def _get_ancestors(self, node: TreeNode) -> Set[TreeNode]:
        """Return a cached set of this node's ancestors (including itself)."""
        if node in self._ancestors_cache:
            return self._ancestors_cache[node]

        ancestors = set()
        current = node
        while current is not None:
            ancestors.add(current)
            current = current.parent
        self._ancestors_cache[node] = ancestors
        return ancestors

    def _compute_statistics(self) -> None:
        """Fill ``stats`` and ``active_stats`` on every tree node.

        ``stats`` includes disabled nodes and links; ``active_stats`` covers
        only the enabled topology. Hardware comes from one inventory, which
        refuses invalid hardware before any capacity or port check.
        """
        self._reset_all_stats()
        self._compute_node_counts()
        inventory = hardware_inventory(self.network, self.components_library)
        for owner, end, name in inventory.unknown:
            if end is None:
                logger.warning(
                    "Node '%s' references unknown node hardware component '%s'.",
                    owner,
                    name,
                )
            else:
                link = self.network.links[owner]
                logger.warning(
                    "Link '%s->%s' unknown %s hardware component '%s'.",
                    link.source,
                    link.target,
                    "src" if end == "source" else "dst",
                    name,
                )
        for use in inventory.uses:
            for an in self._get_ancestors(self._node_map[use.node]):
                _add_hardware(an.stats, use)
                if use.active:
                    _add_hardware(an.active_stats, use)
        self._compute_link_stats()
        self._validate_hardware(inventory.uses)

    def _reset_all_stats(self) -> None:
        """Zero out stats on all tree nodes."""

        def reset_stats(n: TreeNode) -> None:
            n.stats = TreeStats()
            n.active_stats = TreeStats()
            for c in n.children.values():
                reset_stats(c)

        if self.root_node:
            reset_stats(self.root_node)

    def _compute_node_counts(self) -> None:
        """Set node counts from subtree sets."""

        def set_node_counts(n: TreeNode) -> None:
            n.stats.node_count = len(n.subtree_nodes)
            n.active_stats.node_count = len(n.active_subtree_nodes)
            for c in n.children.values():
                set_node_counts(c)

        if self.root_node:
            set_node_counts(self.root_node)

    def _compute_link_stats(self) -> None:
        """Accumulate internal and external link counts and capacities.

        A link is internal to the common ancestors of its endpoints and
        external to the others; the enabled view counts active links only.
        """
        for link in self.network.links.values():
            src_node = self._node_map[link.source]
            dst_node = self._node_map[link.target]
            src_path = self._node_path_map[src_node]
            dst_path = self._node_path_map[dst_node]
            a_src = self._get_ancestors(src_node)
            a_dst = self._get_ancestors(dst_node)
            active = link_active(self.network, link)
            for an in a_src & a_dst:
                for stats in (an.stats, an.active_stats) if active else (an.stats,):
                    stats.internal_link_count += 1
                    stats.internal_link_capacity += link.capacity
            for an in a_src ^ a_dst:
                other_path = dst_path if an in a_src else src_path
                for stats in (an.stats, an.active_stats) if active else (an.stats,):
                    stats.external_link_count += 1
                    stats.external_link_capacity += link.capacity
                    bd = stats.external_link_details.setdefault(
                        other_path, ExternalLinkBreakdown()
                    )
                    bd.link_count += 1
                    bd.link_capacity += link.capacity

    def _validate_hardware(self, uses: tuple[HardwareUse, ...]) -> None:
        """Record node utilization and link issues; raise on violations if strict.

        Nodes are checked in node order (capacity before ports), then links in
        link order. Attached capacity counts each active link once, a self-loop
        included; ports count each active optic end at the node.

        Raises:
            ValueError: On a node capacity, port, or link capacity violation
                when ``strict_validation`` is True.
        """
        attached: Dict[str, float] = {}
        for link in self.network.links.values():
            if link_active(self.network, link):
                for endpoint in dict.fromkeys((link.source, link.target)):
                    attached[endpoint] = attached.get(endpoint, 0.0) + float(
                        link.capacity
                    )
        optics: Dict[str, List[HardwareUse]] = {}
        end_capacity: Dict[str, Dict[Optional[str], float]] = {}
        for use in uses:
            if use.link is not None:
                optics.setdefault(use.node, []).append(use)
                end_capacity.setdefault(use.link, {})[use.end] = use.capacity
        for use in uses:
            if use.link is None and use.active and use.capacity > 0.0:
                self._validate_node_utilization(
                    use, attached.get(use.node, 0.0), optics.get(use.node, [])
                )
        for key, link in self.network.links.items():
            capacities = end_capacity.get(key, {})
            if len(capacities) < 2 or not link_active(self.network, link):
                continue
            limit = min(capacities.values())
            if limit <= 0.0 or float(link.capacity) <= limit:
                continue
            if self.strict_validation:
                raise ValueError(
                    (
                        "Link '%s->%s' capacity %.6g exceeds per-end hardware "
                        "capacity limit %.6g (min of src/dst ends)."
                    )
                    % (link.source, link.target, float(link.capacity), limit)
                )
            self._link_issues.append(
                LinkCapacityIssue(
                    source=link.source,
                    target=link.target,
                    capacity=float(link.capacity),
                    limit=float(limit),
                    reason="link_capacity_exceeds_end_hw",
                )
            )

    def _validate_node_utilization(
        self, platform: HardwareUse, attached_capacity: float, optics: List[HardwareUse]
    ) -> None:
        """Record a node's hardware utilization and check it against limits.

        Compares attached link capacity with the platform capacity, and ports
        used by the node's active link-end optics (declared count times ports)
        with the ports available; a violation needs more than 1e-9 extra
        ports. The NodeUtilization snapshot is recorded before any error.

        Raises:
            ValueError: On a capacity or port violation when
                ``strict_validation`` is True.
        """
        comp = platform.component
        used_ports = 0.0
        for use in optics:
            if use.active and use.component.ports > 0:
                used_ports += use.count * float(use.component.ports)
        total_ports_available = float(comp.ports) * float(platform.count)
        capacity_violation = attached_capacity > platform.capacity
        ports_violation = comp.ports > 0 and used_ports > total_ports_available + 1e-9
        ports_utilization = (
            (used_ports / total_ports_available) if total_ports_available > 0.0 else 0.0
        )
        self._node_utilization[platform.node] = NodeUtilization(
            node_name=platform.node,
            component_name=comp.name,
            hw_count=float(platform.count),
            capacity_supported=float(platform.capacity),
            attached_capacity_active=float(attached_capacity),
            capacity_utilization=float(attached_capacity / platform.capacity),
            ports_available=float(total_ports_available),
            ports_used=float(used_ports),
            ports_utilization=float(ports_utilization),
            capacity_violation=bool(capacity_violation),
            ports_violation=bool(ports_violation),
        )
        if capacity_violation and self.strict_validation:
            raise ValueError(
                (
                    "Node '%s' total attached capacity %.6g exceeds hardware "
                    "capacity %.6g from component '%s' (hw_count=%.6g)."
                )
                % (
                    platform.node,
                    attached_capacity,
                    platform.capacity,
                    comp.name,
                    platform.count,
                )
            )
        if ports_violation and self.strict_validation:
            raise ValueError(
                (
                    "Node '%s' requires %.6g ports for link optics but only %.6g ports "
                    "are available on '%s' (count=%.6g)."
                )
                % (
                    platform.node,
                    used_ports,
                    total_ports_available,
                    comp.name,
                    platform.count,
                )
            )

    def print_tree(
        self,
        node: Optional[TreeNode] = None,
        indent: int = 0,
        max_depth: Optional[int] = None,
        skip_leaves: bool = False,
        detailed: bool = False,
        include_disabled: bool = True,
        max_external_lines: Optional[int] = None,
        line_prefix: str = "",
    ) -> None:
        """Print the hierarchy from 'node' down (default: root).

        Args:
            node: Subtree to print; the root when None.
            indent: Depth of ``node``, used for indentation and the
                ``max_depth`` check.
            max_depth: Deepest level to print; None prints all levels.
            skip_leaves: Hide leaf subtrees and roll external-link targets
                that are leaves up to their parent.
            detailed: Add internal/external capacity and one line per
                external destination.
            include_disabled: If False, show stats only for enabled nodes/links.
                Subtrees with zero active nodes are omitted.
            max_external_lines: Cap on external destination lines per tree
                node; None prints all.
            line_prefix: String prepended to every printed line.
        """
        if node is None:
            node = self.root_node
            if node is None:
                print(f"{line_prefix}No hierarchy built yet.")
                return

        if max_depth is not None and indent > max_depth:
            return

        stats = node.stats if include_disabled else node.active_stats

        if not include_disabled and stats.node_count == 0 and node.parent is not None:
            return

        if skip_leaves and node.is_leaf() and node.parent is not None:
            return

        total_links = stats.internal_link_count + stats.external_link_count
        line = (
            f"{'  ' * indent}- {node.name or 'root'} | "
            f"Nodes={stats.node_count:,}, Links={total_links:,}, "
            f"CapEx={stats.total_capex:,.0f}, Power={stats.total_power:,.0f}"
        )
        if detailed:
            line += (
                f" | IntLinkCap={stats.internal_link_capacity:,.1f}, "
                f"ExtLinkCap={stats.external_link_capacity:,.1f}"
            )

        print(f"{line_prefix}{line}")

        if detailed and stats.external_link_details:
            rolled_map: Dict[str, ExternalLinkBreakdown] = {}
            for other_path, info in stats.external_link_details.items():
                rolled_path = other_path
                if skip_leaves:
                    rolled_path = self._roll_up_if_leaf(rolled_path)
                accum = rolled_map.setdefault(rolled_path, ExternalLinkBreakdown())
                accum.link_count += info.link_count
                accum.link_capacity += info.link_capacity

            items = sorted(
                rolled_map.items(),
                key=lambda kv: (-kv[1].link_capacity, kv[0]),
            )
            displayed = 0
            for path_str, ext_info in items:
                if path_str == "":
                    path_str = "[root]"
                print(
                    f"{line_prefix}{'  ' * indent}   -> External to [{path_str}]: "
                    f"{ext_info.link_count:,} links, cap={ext_info.link_capacity:,.1f}"
                )
                displayed += 1
                if max_external_lines is not None and displayed >= max_external_lines:
                    remaining = len(items) - displayed
                    if remaining > 0:
                        print(
                            f"{line_prefix}{'  ' * indent}     ... and {remaining} more"
                        )
                    break

        for child in node.children.values():
            self.print_tree(
                node=child,
                indent=indent + 1,
                max_depth=max_depth,
                skip_leaves=skip_leaves,
                detailed=detailed,
                include_disabled=include_disabled,
                max_external_lines=max_external_lines,
                line_prefix=line_prefix,
            )

    def _roll_up_if_leaf(self, path: str) -> str:
        """Map a leaf's path to its parent's path.

        Non-leaf paths, top-level leaves, and unknown paths are returned unchanged.
        """
        node = self._path_map.get(path)
        if not node:
            return path
        while node.parent and node.parent.parent is not None and node.is_leaf():
            node = node.parent
        return self._node_path_map[node]

    # ----------------------------- BOM accessors -----------------------------
    def get_bom(self, include_disabled: bool = True) -> Dict[str, float]:
        """Return aggregated hardware BOM for the whole network.

        Args:
            include_disabled: If True, include disabled nodes/links. If False,
                aggregate only enabled topology.

        Returns:
            Mapping component_name -> count.
        """
        if self.root_node is None:
            return {}
        stats = (
            self.root_node.stats if include_disabled else self.root_node.active_stats
        )
        return dict(stats.bom)

    # ---------------------- Validation/utilization accessors ----------------------
    def get_node_utilization(self) -> List[NodeUtilization]:
        """Return hardware utilization per node based on active topology.

        Snapshots are recorded only for enabled nodes whose hardware component
        resolves with a positive capacity.

        Returns:
            List of NodeUtilization entries.
        """
        return list(self._node_utilization.values())

    def get_link_issues(self) -> List[LinkCapacityIssue]:
        """Return link capacity violations recorded in non-strict mode."""
        return list(self._link_issues)


def _add_hardware(stats: TreeStats, use: HardwareUse) -> None:
    """Add one hardware use to a subtree's capex, power and BOM."""
    stats.total_capex += use.capex
    stats.total_power += use.power_watts
    name = use.component.name
    stats.bom[name] = stats.bom.get(name, 0.0) + use.bom_count
