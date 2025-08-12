"""NetworkExplorer class for analyzing network hierarchy and structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from ngraph.components import (
    ComponentsLibrary,
    resolve_link_end_components,
    resolve_node_hardware,
    totals_with_multiplier,
)
from ngraph.logging import get_logger
from ngraph.model.network import Network, Node

logger = get_logger(__name__)


@dataclass
class ExternalLinkBreakdown:
    """Holds stats for external links to a particular other subtree.

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
        total_capex (float): Cumulative capex (nodes + links).
        total_power (float): Cumulative power (nodes + links).
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
    # Hardware BOM aggregation
    bom: Dict[str, float] = field(default_factory=dict)
    active_bom: Dict[str, float] = field(default_factory=dict)


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
        disabled: True if the node itself is disabled.
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
    disabled: bool


@dataclass
class LinkCapacityIssue:
    """Represents a link capacity constraint violation in active topology.

    Attributes:
        source: Source node name.
        target: Target node name.
        capacity: Configured link capacity.
        limit: Effective capacity limit from per-end hardware (min of ends).
        reason: Brief reason tag.
    """

    source: str
    target: str
    capacity: float
    limit: float
    reason: str


@dataclass(eq=False)
class TreeNode:
    """Represents a node in the hierarchical tree.

    Attributes:
        name (str): Name/label of this node.
        parent (Optional[TreeNode]): Pointer to the parent tree node.
        children (Dict[str, TreeNode]): Mapping of child name -> child TreeNode.
        subtree_nodes (Set[str]): Node names in the subtree (all nodes, ignoring disabled).
        active_subtree_nodes (Set[str]): Node names in the subtree (only enabled).
        stats (TreeStats): Aggregated stats for "all" view.
        active_stats (TreeStats): Aggregated stats for "active" (only enabled) view.
        raw_nodes (List[Node]): Direct Node objects at this hierarchy level.
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
        """Ensure a child node named 'child_name' exists and return it."""
        if child_name not in self.children:
            child_node = TreeNode(name=child_name, parent=self)
            self.children[child_name] = child_node
        return self.children[child_name]

    def is_leaf(self) -> bool:
        """Return True if this node has no children."""
        return len(self.children) == 0


class NetworkExplorer:
    """Provides hierarchical exploration of a Network, computing statistics in two modes:
    'all' (ignores disabled) and 'active' (only enabled).
    """

    def __init__(
        self,
        network: Network,
        components_library: Optional[ComponentsLibrary] = None,
        strict_validation: bool = True,
    ) -> None:
        self.network = network
        self.components_library = components_library or ComponentsLibrary()
        self.strict_validation = strict_validation

        self.root_node: Optional[TreeNode] = None

        # For quick lookups:
        self._node_map: Dict[str, TreeNode] = {}  # node_name -> deepest TreeNode
        self._path_map: Dict[str, TreeNode] = {}  # path -> TreeNode

        # Cache for ancestor sets:
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
        """Build a NetworkExplorer, constructing a tree plus 'all' and 'active' stats.

        The Explorer also constructs hardware Bills-of-Materials (BOM):
        - stats.bom: total counts by component for all nodes/links (ignores disabled)
        - active_stats.bom: counts by component for enabled topology only
        Counts include fractional usage for sharable optics; exclusive endpoints
        are rounded up in per-link aggregation.

        Args:
            network: Network model instance.
            components_library: Components definition library.
            strict_validation: When True, raise on capacity/ports violations; when False,
                record issues and continue (useful for inspection flows).
        """
        instance = cls(network, components_library, strict_validation=strict_validation)

        # 1) Build hierarchy
        instance.root_node = instance._build_hierarchy_tree()

        # 2) Compute subtree sets for "all" (ignoring disabled state)
        instance._compute_subtree_sets_all(instance.root_node)

        # 3) Compute subtree sets for "active" (excluding disabled)
        instance._compute_subtree_sets_active(instance.root_node)

        # 4) Build node & path maps
        instance._build_node_map(instance.root_node)
        instance._build_path_map(instance.root_node)

        # 5) Aggregate statistics (both 'all' and 'active')
        instance._compute_statistics()

        return instance

    def _build_hierarchy_tree(self) -> TreeNode:
        """Build a multi-level tree by splitting node names on '/'.
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
        """Recursively collect all node names (regardless of disabled) into subtree_nodes."""
        collected = set()
        for child in node.children.values():
            collected |= self._compute_subtree_sets_all(child)
        for nd in node.raw_nodes:
            collected.add(nd.name)
        node.subtree_nodes = collected
        return collected

    def _compute_subtree_sets_active(self, node: TreeNode) -> Set[str]:
        """Recursively collect enabled node names into active_subtree_nodes.
        A node is considered enabled if nd.attrs.get("disabled") is not truthy.
        """
        collected = set()
        for child in node.children.values():
            collected |= self._compute_subtree_sets_active(child)
        for nd in node.raw_nodes:
            if not nd.attrs.get("disabled"):
                collected.add(nd.name)
        node.active_subtree_nodes = collected
        return collected

    def _build_node_map(self, node: TreeNode) -> None:
        """Assign each node's name to the *deepest* TreeNode that actually holds it.
        We do a parent-first approach so children override if needed.
        """
        # Map the raw_nodes at this level
        for nd in node.raw_nodes:
            self._node_map[nd.name] = node

        # Then recurse, letting children override deeper nodes
        for child in node.children.values():
            self._build_node_map(child)

    def _build_path_map(self, node: TreeNode) -> None:
        """Build a path->TreeNode map for easy lookups. Skips "root" in path strings."""
        path_str = self._compute_full_path(node)
        self._path_map[path_str] = node
        for child in node.children.values():
            self._build_path_map(child)

    def _compute_full_path(self, node: TreeNode) -> str:
        """Return a '/'-joined path, omitting "root"."""
        parts = []
        current = node
        while current and current.name != "root":
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
        """Populates two stats sets for each TreeNode:
        - node.stats (all, ignoring disabled)
        - node.active_stats (only enabled nodes/links)
        """

        # First, zero them out
        def reset_stats(n: TreeNode):
            n.stats = TreeStats()
            n.active_stats = TreeStats()
            for c in n.children.values():
                reset_stats(c)

        if self.root_node:
            reset_stats(self.root_node)

        # 1) Node counts from subtree sets
        def set_node_counts(n: TreeNode):
            n.stats.node_count = len(n.subtree_nodes)
            n.active_stats.node_count = len(n.active_subtree_nodes)
            for c in n.children.values():
                set_node_counts(c)

        if self.root_node:
            set_node_counts(self.root_node)

        # 2) Accumulate node capex/power and validate hardware capacity vs attached links
        #    Also validate that sum of endpoint optics usage does not exceed node port count
        #    Track which nodes actually have chassis/hardware assigned; optics at a link
        #    endpoint should contribute cost/power only when the endpoint node has
        #    hardware. Without node hardware, optics cannot be installed and should be
        #    ignored in aggregation and capacity validation.
        node_has_hw: Dict[str, bool] = {}
        for nd in self.network.nodes.values():
            comp, hw_count = resolve_node_hardware(nd.attrs, self.components_library)
            node_has_hw[nd.name] = comp is not None
            if nd.attrs.get("hardware") and comp is None:
                logger.warning(
                    "Node '%s' references unknown node hardware component '%s'.",
                    nd.name,
                    (nd.attrs.get("hardware") or {}).get("component"),
                )

            # Totals with external multiplier
            if comp is not None:
                cost_val, power_val, node_comp_capacity = totals_with_multiplier(
                    comp, hw_count
                )
            else:
                cost_val = 0.0
                power_val = 0.0
                node_comp_capacity = 0.0

            tree_node = self._node_map[nd.name]
            # "All" includes disabled
            for an in self._get_ancestors(tree_node):
                an.stats.total_capex += cost_val
                an.stats.total_power += power_val
                if comp is not None:
                    an.stats.bom[comp.name] = an.stats.bom.get(comp.name, 0.0) + float(
                        hw_count
                    )

            # "Active" excludes disabled
            if not nd.attrs.get("disabled"):
                for an in self._get_ancestors(tree_node):
                    an.active_stats.total_capex += cost_val
                    an.active_stats.total_power += power_val
                    if comp is not None:
                        an.active_stats.bom[comp.name] = an.active_stats.bom.get(
                            comp.name, 0.0
                        ) + float(hw_count)

            # Validation only if component has a positive capacity and node is enabled
            if (
                comp is not None
                and node_comp_capacity > 0.0
                and not nd.attrs.get("disabled")
            ):
                # Sum capacities of all enabled links attached to this node
                attached_capacity = 0.0
                # Track optics usage in "equivalent optics" and ports tally
                used_optics_equiv = 0.0
                used_ports = 0.0
                for lk in self.network.links.values():
                    if lk.attrs.get("disabled"):
                        continue
                    if lk.source == nd.name or lk.target == nd.name:
                        # If the opposite endpoint is disabled, skip in active view
                        other = lk.target if lk.source == nd.name else lk.source
                        if self.network.nodes.get(other, Node(name=other)).attrs.get(
                            "disabled"
                        ):
                            continue
                        attached_capacity += float(lk.capacity)

                        # Compute optics usage for this endpoint if per-end hardware is set
                        (src_end, dst_end, per_end) = resolve_link_end_components(
                            lk.attrs, self.components_library
                        )
                        if per_end:
                            end = src_end if lk.source == nd.name else dst_end
                            end_comp, end_cnt, end_excl = end
                            if end_comp is not None:
                                # Count optics-equivalents by component count
                                used_optics_equiv += end_cnt
                                # Ports used equals count * ports per optic (fractional allowed)
                                ports_per_optic = float(
                                    getattr(end_comp, "ports", 0) or 0
                                )
                                if ports_per_optic > 0:
                                    used_ports += end_cnt * ports_per_optic

                # Compute ports availability and violations
                total_ports_available = float(getattr(comp, "ports", 0) or 0) * float(
                    hw_count
                )
                capacity_violation = attached_capacity > node_comp_capacity
                ports_violation = False
                if getattr(comp, "ports", 0) and comp.ports > 0:
                    ports_violation = used_ports > total_ports_available + 1e-9

                # Record per-node utilization snapshot for active topology
                capacity_utilization = (
                    (attached_capacity / node_comp_capacity)
                    if node_comp_capacity > 0.0
                    else 0.0
                )
                ports_utilization = (
                    (used_ports / total_ports_available)
                    if total_ports_available > 0.0
                    else 0.0
                )
                self._node_utilization[nd.name] = NodeUtilization(
                    node_name=nd.name,
                    component_name=comp.name,
                    hw_count=float(hw_count),
                    capacity_supported=float(node_comp_capacity),
                    attached_capacity_active=float(attached_capacity),
                    capacity_utilization=float(capacity_utilization),
                    ports_available=float(total_ports_available),
                    ports_used=float(used_ports),
                    ports_utilization=float(ports_utilization),
                    capacity_violation=bool(capacity_violation),
                    ports_violation=bool(ports_violation),
                    disabled=bool(nd.attrs.get("disabled")),
                )

                # Enforce strict behavior after recording
                if capacity_violation and self.strict_validation:
                    raise ValueError(
                        (
                            "Node '%s' total attached capacity %.6g exceeds hardware "
                            "capacity %.6g from component '%s' (hw_count=%.6g)."
                        )
                        % (
                            nd.name,
                            attached_capacity,
                            node_comp_capacity,
                            comp.name,
                            hw_count,
                        )
                    )
                if ports_violation and self.strict_validation:
                    raise ValueError(
                        (
                            "Node '%s' requires %.6g ports for link optics but only %.6g ports "
                            "are available on '%s' (count=%.6g)."
                        )
                        % (
                            nd.name,
                            used_ports,
                            total_ports_available,
                            comp.name,
                            hw_count,
                        )
                    )

        # 3) Accumulate link stats (internal/external + capex/power) and validate
        for link in self.network.links.values():
            src = link.source
            dst = link.target

            # Resolve per-end link hardware (no legacy support)
            (src_end, dst_end, per_end) = resolve_link_end_components(
                link.attrs, self.components_library
            )

            # Inspect provided names for warnings
            link_comp_capacity = 0.0

            # Initialize defaults for cost/power even when no per-end hardware
            src_cost = 0.0
            src_power = 0.0
            dst_cost = 0.0
            dst_power = 0.0

            if per_end:
                src_comp, src_cnt, src_exclusive = src_end
                dst_comp, dst_cnt, dst_exclusive = dst_end

                # Unknown component warnings with names
                hw_struct = link.attrs.get("hardware")
                src_name = None
                dst_name = None
                if isinstance(hw_struct, dict):
                    src_map = hw_struct.get("source", {})
                    dst_map = hw_struct.get("target", {})
                    src_name = src_map.get("component")
                    dst_name = dst_map.get("component")

                if src_comp is None and src_name:
                    logger.warning(
                        "Link '%s->%s' unknown src hardware component '%s'.",
                        src,
                        dst,
                        src_name,
                    )
                if dst_comp is None and dst_name:
                    logger.warning(
                        "Link '%s->%s' unknown dst hardware component '%s'.",
                        src,
                        dst,
                        dst_name,
                    )

                # Optics contribute only if the endpoint node has hardware
                src_endpoint_has_hw = node_has_hw.get(src, False)
                if src_comp is not None and src_endpoint_has_hw:
                    # For BOM, apply ceiling for exclusive use
                    src_cnt_bom = float(int(src_cnt) if src_exclusive else src_cnt)
                    src_cost, src_power, src_cap = totals_with_multiplier(
                        src_comp, src_cnt
                    )
                else:
                    src_cost, src_power, src_cap = 0.0, 0.0, 0.0
                    src_cnt_bom = 0.0
                    # Prevent BOM accumulation below
                    if not src_endpoint_has_hw:
                        src_comp = None

                dst_endpoint_has_hw = node_has_hw.get(dst, False)
                if dst_comp is not None and dst_endpoint_has_hw:
                    dst_cnt_bom = float(int(dst_cnt) if dst_exclusive else dst_cnt)
                    dst_cost, dst_power, dst_cap = totals_with_multiplier(
                        dst_comp, dst_cnt
                    )
                else:
                    dst_cost, dst_power, dst_cap = 0.0, 0.0, 0.0
                    dst_cnt_bom = 0.0
                    if not dst_endpoint_has_hw:
                        dst_comp = None

                # Capacity limit: only enforce if both ends specify positive capacity
                if src_cap > 0.0 and dst_cap > 0.0:
                    link_comp_capacity = min(src_cap, dst_cap)
            cap = link.capacity

            src_node = self._node_map[src]
            dst_node = self._node_map[dst]
            A_src = self._get_ancestors(src_node)
            A_dst = self._get_ancestors(dst_node)

            inter_anc = A_src & A_dst  # sees link as "internal"
            xor_anc = A_src ^ A_dst  # sees link as "external"

            # Initialize defaults for BOM variables if per_end is False
            # Establish defaults to satisfy type checker; will be overwritten when per_end
            src_comp = None
            dst_comp = None
            src_cnt_bom = 0.0
            dst_cnt_bom = 0.0

            # ----- "ALL" stats -----
            for an in inter_anc:
                an.stats.internal_link_count += 1
                an.stats.internal_link_capacity += cap
            for an in xor_anc:
                an.stats.external_link_count += 1
                an.stats.external_link_capacity += cap
                if an in A_src:
                    other_path = self._compute_full_path(dst_node)
                else:
                    other_path = self._compute_full_path(src_node)
                bd = an.stats.external_link_details.setdefault(
                    other_path, ExternalLinkBreakdown()
                )
                bd.link_count += 1
                bd.link_capacity += cap

            # Attribute per-end hardware cost/power/BOM only to that endpoint's ancestors
            for an in A_src:
                an.stats.total_capex += src_cost
                an.stats.total_power += src_power
                if per_end and src_comp is not None:
                    an.stats.bom[src_comp.name] = (
                        an.stats.bom.get(src_comp.name, 0.0) + src_cnt_bom
                    )
            for an in A_dst:
                an.stats.total_capex += dst_cost
                an.stats.total_power += dst_power
                if per_end and dst_comp is not None:
                    an.stats.bom[dst_comp.name] = (
                        an.stats.bom.get(dst_comp.name, 0.0) + dst_cnt_bom
                    )

            # ----- "ACTIVE" stats and validations -----
            # If link or either endpoint is disabled, skip
            if link.attrs.get("disabled"):
                continue
            if self.network.nodes[src].attrs.get("disabled"):
                continue
            if self.network.nodes[dst].attrs.get("disabled"):
                continue

            # Validation: if both ends provide capacity, enforce min-end capacity
            if link_comp_capacity > 0.0:
                if float(cap) > link_comp_capacity:
                    if self.strict_validation:
                        raise ValueError(
                            (
                                "Link '%s->%s' capacity %.6g exceeds per-end hardware "
                                "capacity limit %.6g (min of src/dst ends)."
                            )
                            % (
                                src,
                                dst,
                                float(cap),
                                link_comp_capacity,
                            )
                        )
                    else:
                        self._link_issues.append(
                            LinkCapacityIssue(
                                source=src,
                                target=dst,
                                capacity=float(cap),
                                limit=float(link_comp_capacity),
                                reason="link_capacity_exceeds_end_hw",
                            )
                        )

            for an in inter_anc:
                an.active_stats.internal_link_count += 1
                an.active_stats.internal_link_capacity += cap
            for an in xor_anc:
                an.active_stats.external_link_count += 1
                an.active_stats.external_link_capacity += cap
                if an in A_src:
                    other_path = self._compute_full_path(dst_node)
                else:
                    other_path = self._compute_full_path(src_node)
                bd = an.active_stats.external_link_details.setdefault(
                    other_path, ExternalLinkBreakdown()
                )
                bd.link_count += 1
                bd.link_capacity += cap

            # Attribute active per-end cost/power/BOM only to the endpoint's ancestors
            for an in A_src:
                an.active_stats.total_capex += src_cost
                an.active_stats.total_power += src_power
                if per_end and src_comp is not None:
                    an.active_stats.bom[src_comp.name] = (
                        an.active_stats.bom.get(src_comp.name, 0.0) + src_cnt_bom
                    )
            for an in A_dst:
                an.active_stats.total_capex += dst_cost
                an.active_stats.total_power += dst_power
                if per_end and dst_comp is not None:
                    an.active_stats.bom[dst_comp.name] = (
                        an.active_stats.bom.get(dst_comp.name, 0.0) + dst_cnt_bom
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
            node (TreeNode): subtree to print, or root if None
            indent (int): indentation level
            max_depth (int): if set, limit display depth
            skip_leaves (bool): if True, skip leaf subtrees
            detailed (bool): if True, print link capacity breakdowns
            include_disabled (bool): If False, show stats only for enabled nodes/links.
                                     Subtrees with zero active nodes are omitted.
        """
        if node is None:
            node = self.root_node
            if node is None:
                print(f"{line_prefix}No hierarchy built yet.")
                return

        if max_depth is not None and indent > max_depth:
            return

        # Pick which stats to display
        stats = node.stats if include_disabled else node.active_stats

        # If 'active' mode and this node has 0 nodes, omit it (unless it's the root)
        if not include_disabled and stats.node_count == 0 and node.parent is not None:
            return

        # Possibly skip leaves
        if skip_leaves and node.is_leaf() and node.parent is not None:
            return

        total_links = stats.internal_link_count + stats.external_link_count
        # Format numbers with separators; keep one decimal for capacities
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

        # If detailed, show external link breakdown
        if detailed and stats.external_link_details:
            rolled_map: Dict[str, ExternalLinkBreakdown] = {}
            for other_path, info in stats.external_link_details.items():
                rolled_path = other_path
                if skip_leaves:
                    # If that path is a leaf, roll up
                    rolled_path = self._roll_up_if_leaf(rolled_path)
                accum = rolled_map.setdefault(rolled_path, ExternalLinkBreakdown())
                accum.link_count += info.link_count
                accum.link_capacity += info.link_capacity

            # Sort by descending capacity, then path
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

        # Recurse on children
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
        """If 'path' is a leaf node's path, climb up until a non-leaf or root is found."""
        node = self._path_map.get(path)
        if not node:
            return path
        while node.parent and node.parent.name != "root" and node.is_leaf():
            node = node.parent
        return self._compute_full_path(node)

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

    def get_bom_by_path(
        self, path: str, include_disabled: bool = True
    ) -> Dict[str, float]:
        """Return the hardware BOM for a specific hierarchy path.

        Args:
            path: Hierarchy path (e.g., "dc1/plane1"). Empty string returns the root BOM.
            include_disabled: If True, include disabled nodes/links.

        Returns:
            Mapping component_name -> count for the subtree.
        """
        if path == "":
            return self.get_bom(include_disabled=include_disabled)
        node = self._path_map.get(path)
        if node is None:
            return {}
        stats = node.stats if include_disabled else node.active_stats
        return dict(stats.bom)

    def get_bom_map(
        self,
        include_disabled: bool = True,
        include_root: bool = True,
        root_label: str = "",
    ) -> Dict[str, Dict[str, float]]:
        """Return a mapping from hierarchy path to BOM for each subtree.

        Args:
            include_disabled: Include disabled nodes/links in BOMs.
            include_root: Include the root entry under ``root_label``.
            root_label: Label for the root entry (default: "").

        Returns:
            Dict mapping path -> {component_name -> count}.
        """
        result: Dict[str, Dict[str, float]] = {}
        if include_root:
            result[root_label] = self.get_bom(include_disabled=include_disabled)
        for path, node in self._path_map.items():
            stats = node.stats if include_disabled else node.active_stats
            result[path] = dict(stats.bom)
        return result

    # ---------------------- Validation/utilization accessors ----------------------
    def get_node_utilization(
        self, include_disabled: bool = True
    ) -> List[NodeUtilization]:
        """Return hardware utilization per node based on active topology.

        Args:
            include_disabled: Include nodes marked disabled in the result.

        Returns:
            List of NodeUtilization entries for nodes with declared hardware.
        """
        items = list(self._node_utilization.values())
        if include_disabled:
            return list(items)
        return [u for u in items if not u.disabled]

    def get_link_issues(self) -> List[LinkCapacityIssue]:
        """Return recorded link capacity issues discovered in non-strict mode."""
        return list(self._link_issues)
