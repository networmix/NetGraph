from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional

from ngraph.network import Network, Node, Link
from ngraph.components import ComponentsLibrary

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class ExternalLinkBreakdown:
    """
    Holds stats for external links to a particular other subtree.

    Attributes:
        link_count (int): Number of links to that other subtree.
        link_capacity (float): Sum of capacities for those links.
    """

    link_count: int = 0
    link_capacity: float = 0.0


@dataclass
class TreeStats:
    """
    Aggregated statistics for a single tree node (subtree).

    Attributes:
        node_count (int): Total number of nodes in this subtree.
        internal_link_count (int): Number of internal links in this subtree.
        internal_link_capacity (float): Sum of capacities for those internal links.
        external_link_count (int): Number of external links from this subtree to another.
        external_link_capacity (float): Sum of capacities for those external links.
        external_link_details (Dict[str, ExternalLinkBreakdown]): Breakdown of external
            links by the other subtree's path.
        total_cost (float): Cumulative cost from node 'hw_component' plus link 'hw_component'.
        total_power (float): Cumulative power from node 'hw_component' plus link 'hw_component'.
    """

    node_count: int = 0

    internal_link_count: int = 0
    internal_link_capacity: float = 0.0

    external_link_count: int = 0
    external_link_capacity: float = 0.0

    external_link_details: Dict[str, ExternalLinkBreakdown] = field(
        default_factory=dict
    )

    total_cost: float = 0.0
    total_power: float = 0.0


@dataclass(eq=False)
class TreeNode:
    """
    Represents a node in the hierarchical tree.

    Attributes:
        name (str): Name/label of this node (e.g., "dc1", "plane1", etc.).
        parent (Optional[TreeNode]): Pointer to the parent tree node.
        children (Dict[str, TreeNode]): Mapping of child name -> child TreeNode.
        subtree_nodes (Set[str]): The set of all node names in this subtree.
        stats (TreeStats): Computed statistics for this subtree.
        raw_nodes (List[Node]): Direct Node objects at this hierarchical level.
    """

    name: str
    parent: Optional[TreeNode] = None

    children: Dict[str, TreeNode] = field(default_factory=dict)
    subtree_nodes: Set[str] = field(default_factory=set)
    stats: TreeStats = field(default_factory=TreeStats)
    raw_nodes: List[Node] = field(default_factory=list)

    def __hash__(self) -> int:
        """
        Make the node hashable based on object identity.
        This preserves uniqueness in sets/dicts without
        forcing equality by fields.
        """
        return id(self)

    def add_child(self, child_name: str) -> TreeNode:
        """
        Ensure a child node named 'child_name' exists and return it.

        Args:
            child_name (str): The name of the child node to add/find.

        Returns:
            TreeNode: The new or existing child TreeNode.
        """
        if child_name not in self.children:
            child_node = TreeNode(name=child_name, parent=self)
            self.children[child_name] = child_node
        return self.children[child_name]

    def is_leaf(self) -> bool:
        """
        Return True if this node has no children.

        Returns:
            bool: True if there are no children, False otherwise.
        """
        return len(self.children) == 0


class NetworkExplorer:
    """
    Provides hierarchical exploration of a Network, computing internal/external
    link counts, node counts, and cost/power usage. Also records external link
    breakdowns by subtree path, with optional roll-up of leaf nodes in display.
    """

    def __init__(
        self,
        network: Network,
        components_library: Optional[ComponentsLibrary] = None,
    ) -> None:
        """
        Initialize a NetworkExplorer. Generally, use 'explore_network' to build
        and populate stats automatically.

        Args:
            network (Network): The network to explore.
            components_library (Optional[ComponentsLibrary]): Library of
                hardware/optic components to calculate cost/power. If None,
                an empty library is used and cost/power will be 0.
        """
        self.network = network
        self.components_library = components_library or ComponentsLibrary()

        self.root_node: Optional[TreeNode] = None

        # For quick lookups:
        self._node_map: Dict[str, TreeNode] = {}  # node_name -> deepest TreeNode
        self._path_map: Dict[str, TreeNode] = {}  # path -> TreeNode

        # Cache for storing each node's ancestor set:
        self._ancestors_cache: Dict[TreeNode, Set[TreeNode]] = {}

    @classmethod
    def explore_network(
        cls,
        network: Network,
        components_library: Optional[ComponentsLibrary] = None,
    ) -> NetworkExplorer:
        """
        Creates a NetworkExplorer, builds a hierarchy tree, and computes stats.

        NOTE: If you do not pass a non-empty components_library, any hardware
        references for cost/power data will not be found.

        Args:
            network (Network): The network to explore.
            components_library (Optional[ComponentsLibrary]): Components library
                to use for cost/power lookups.

        Returns:
            NetworkExplorer: A fully populated explorer instance with stats.
        """
        instance = cls(network, components_library)

        # 1) Build the hierarchical structure
        instance.root_node = instance._build_hierarchy_tree()

        # 2) Compute subtree sets (subtree_nodes)
        instance._compute_subtree_sets(instance.root_node)

        # 3) Build node and path maps
        instance._build_node_map(instance.root_node)
        instance._build_path_map(instance.root_node)

        # 4) Aggregate statistics (node counts, link stats, cost, power)
        instance._compute_statistics()

        return instance

    def _build_hierarchy_tree(self) -> TreeNode:
        """
        Build a multi-level tree by splitting node names on '/'.
        Example: "dc1/plane1/ssw/ssw-1" => root/dc1/plane1/ssw/ssw-1

        Returns:
            TreeNode: The root of the newly constructed tree.
        """
        root = TreeNode(name="root")
        for nd in self.network.nodes.values():
            path_parts = nd.name.split("/")
            current = root
            for part in path_parts:
                current = current.add_child(part)
            current.raw_nodes.append(nd)
        return root

    def _compute_subtree_sets(self, node: TreeNode) -> Set[str]:
        """
        Recursively compute the set of node names in each subtree.

        Args:
            node (TreeNode): The current tree node.

        Returns:
            Set[str]: A set of node names belonging to the subtree under 'node'.
        """
        collected = set()
        for child in node.children.values():
            collected |= self._compute_subtree_sets(child)
        for nd in node.raw_nodes:
            collected.add(nd.name)
        node.subtree_nodes = collected
        return collected

    def _build_node_map(self, node: TreeNode) -> None:
        """
        Post-order traversal to populate _node_map.

        Each node_name in 'node.subtree_nodes' maps to 'node' if not already
        assigned. The "deepest" node (lowest in the hierarchy) takes precedence.

        Args:
            node (TreeNode): The current tree node.
        """
        for child in node.children.values():
            self._build_node_map(child)
        for node_name in node.subtree_nodes:
            if node_name not in self._node_map:
                self._node_map[node_name] = node

    def _build_path_map(self, node: TreeNode) -> None:
        """
        Build a path->TreeNode map for easy lookups. Skips "root" in paths.

        Args:
            node (TreeNode): The current tree node.
        """
        path_str = self._compute_full_path(node)
        self._path_map[path_str] = node
        for child in node.children.values():
            self._build_path_map(child)

    def _compute_full_path(self, node: TreeNode) -> str:
        """
        Return a '/'-joined path, omitting "root".

        Args:
            node (TreeNode): The tree node to compute a path for.

        Returns:
            str: E.g., "dc1/plane1/ssw".
        """
        parts = []
        current = node
        while current and current.name != "root":
            parts.append(current.name)
            current = current.parent
        return "/".join(reversed(parts))

    def _roll_up_if_leaf(self, path: str) -> str:
        """
        If 'path' corresponds to a leaf node, climb up until a non-leaf or root
        is found. Return the resulting path.

        Args:
            path (str): A '/'-joined path.

        Returns:
            str: Possibly re-mapped path if a leaf was rolled up.
        """
        node = self._path_map.get(path)
        if not node:
            return path
        while node.parent and node.parent.name != "root" and node.is_leaf():
            node = node.parent
        return self._compute_full_path(node)

    def _get_ancestors(self, node: TreeNode) -> Set[TreeNode]:
        """
        Return a cached set of this node's ancestors (including itself),
        up to the root.
        """
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
        """
        Computes all subtree statistics in a more efficient manner:

        - node_count is set from each node's 'subtree_nodes' (already stored).
        - For each network node, cost/power is added to all ancestors in the
          hierarchy.
        - For each link, we figure out which subtrees see it as internal or
          external, and update stats accordingly.
        """

        # 1) node_count: use subtree sets
        #    (each node gets the size of subtree_nodes)
        #    stats are zeroed initially in the constructor.
        def set_node_counts(node: TreeNode) -> None:
            node.stats.node_count = len(node.subtree_nodes)
            for child in node.children.values():
                set_node_counts(child)

        set_node_counts(self.root_node)

        # 2) Accumulate node cost/power into all ancestor stats
        for nd in self.network.nodes.values():
            hw_component = nd.attrs.get("hw_component")
            comp = None
            if hw_component:
                comp = self.components_library.get(hw_component)
                if comp is None:
                    logger.warning(
                        "Node '%s' references unknown hw_component '%s'.",
                        nd.name,
                        hw_component,
                    )

            # Walk up from the deepest node
            node_for_name = self._node_map[nd.name]
            ancestors = self._get_ancestors(node_for_name)
            if comp:
                cval = comp.total_cost()
                pval = comp.total_power()
                for an in ancestors:
                    an.stats.total_cost += cval
                    an.stats.total_power += pval

        # 3) Single pass to accumulate link stats
        #    For each link, determine for which subtrees it's internal vs external,
        #    and update stats accordingly. Also add link hw cost/power if applicable.
        for link in self.network.links.values():
            src = link.source
            dst = link.target

            # Check link's hw_component
            hw_comp = link.attrs.get("hw_component")
            link_comp = None
            if hw_comp:
                link_comp = self.components_library.get(hw_comp)
                if link_comp is None:
                    logger.warning(
                        "Link '%s->%s' references unknown hw_component '%s'.",
                        src,
                        dst,
                        hw_comp,
                    )

            src_node = self._node_map[src]
            dst_node = self._node_map[dst]
            A_src = self._get_ancestors(src_node)
            A_dst = self._get_ancestors(dst_node)

            # Intersection => internal
            # XOR => external
            inter = A_src & A_dst
            xor = A_src ^ A_dst

            # Capacity
            cap = link.capacity

            # For cost/power from link, we add to any node
            # that sees it either internal or external.
            link_cost = link_comp.total_cost() if link_comp else 0.0
            link_power = link_comp.total_power() if link_comp else 0.0

            # Internal link updates
            for an in inter:
                an.stats.internal_link_count += 1
                an.stats.internal_link_capacity += cap
                an.stats.total_cost += link_cost
                an.stats.total_power += link_power

            # External link updates
            for an in xor:
                an.stats.external_link_count += 1
                an.stats.external_link_capacity += cap
                an.stats.total_cost += link_cost
                an.stats.total_power += link_power

                # Update external_link_details
                if an in A_src:
                    # 'an' sees the other side as 'dst'
                    other_path = self._compute_full_path(dst_node)
                else:
                    # 'an' sees the other side as 'src'
                    other_path = self._compute_full_path(src_node)
                bd = an.stats.external_link_details.setdefault(
                    other_path, ExternalLinkBreakdown()
                )
                bd.link_count += 1
                bd.link_capacity += cap

    def print_tree(
        self,
        node: Optional[TreeNode] = None,
        indent: int = 0,
        max_depth: Optional[int] = None,
        skip_leaves: bool = False,
        detailed: bool = False,
    ) -> None:
        """
        Print the hierarchy from the given node (default: root).
        If detailed=True, show link capacities and external link breakdown.
        If skip_leaves=True, leaf nodes are omitted from printing (rolled up).

        Args:
            node (Optional[TreeNode]): The node to start printing from; defaults to root.
            indent (int): Indentation level for the output.
            max_depth (Optional[int]): If set, stop printing deeper levels when exceeded.
            skip_leaves (bool): If True, leaf nodes are not individually printed.
            detailed (bool): If True, print more detailed link/capacity breakdowns.
        """
        if node is None:
            node = self.root_node
            if node is None:
                print("No hierarchy built yet.")
                return

        if max_depth is not None and indent > max_depth:
            return

        if skip_leaves and node.is_leaf() and node.parent is not None:
            return

        stats = node.stats
        total_links = stats.internal_link_count + stats.external_link_count
        line = (
            f"{'  ' * indent}- {node.name or 'root'} | "
            f"Nodes={stats.node_count}, Links={total_links}, "
            f"Cost={stats.total_cost}, Power={stats.total_power}"
        )
        if detailed:
            line += (
                f" | IntLinkCap={stats.internal_link_capacity}, "
                f"ExtLinkCap={stats.external_link_capacity}"
            )

        print(line)

        # If detailed, show external link breakdown
        if detailed and stats.external_link_details:
            rolled_map: Dict[str, ExternalLinkBreakdown] = {}
            for other_path, info in stats.external_link_details.items():
                rolled_path = other_path
                if skip_leaves:
                    rolled_path = self._roll_up_if_leaf(rolled_path)
                accum = rolled_map.setdefault(rolled_path, ExternalLinkBreakdown())
                accum.link_count += info.link_count
                accum.link_capacity += info.link_capacity

            for path_str in sorted(rolled_map.keys()):
                ext_info = rolled_map[path_str]
                if path_str == "":
                    path_str = "[root]"
                print(
                    f"{'  ' * indent}   -> External to [{path_str}]: "
                    f"{ext_info.link_count} links, cap={ext_info.link_capacity}"
                )

        # Recurse children
        for child in node.children.values():
            self.print_tree(
                node=child,
                indent=indent + 1,
                max_depth=max_depth,
                skip_leaves=skip_leaves,
                detailed=detailed,
            )
