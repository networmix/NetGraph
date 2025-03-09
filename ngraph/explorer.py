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


@dataclass
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

        # 2) Compute subtree sets
        instance._compute_subtree_sets(instance.root_node)

        # 3) Build node and path maps
        instance._build_node_map(instance.root_node)
        instance._build_path_map(instance.root_node)

        # 4) Aggregate statistics (nodes, links, cost, power)
        instance._aggregate_stats(instance.root_node)

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

    def _aggregate_stats(self, node: TreeNode) -> None:
        """
        Summarize node count, link stats, and cost/power usage for this subtree,
        then recurse to children.

        Args:
            node (TreeNode): The current tree node to process.
        """
        # 1) Node count
        node.stats.node_count = len(node.subtree_nodes)

        # 2) Accumulate node-level cost/power
        for node_name in node.subtree_nodes:
            nd = self.network.nodes[node_name]
            hw_component = nd.attrs.get("hw_component")
            if hw_component:
                comp = self.components_library.get(hw_component)
                if comp:
                    node.stats.total_cost += comp.total_cost()
                    node.stats.total_power += comp.total_power()
                else:
                    logger.warning(
                        "Node '%s' references unknown hw_component '%s'.",
                        node_name,
                        hw_component,
                    )

        # Minor early-out: if this node is a leaf and has <= 1 raw node,
        # no links are possible within or external to it.
        # (If it has multiple raw_nodes, we do need the link checks.)
        if node.is_leaf() and len(node.raw_nodes) <= 1:
            return

        # 3) Evaluate link-level stats
        for link in self.network.links.values():
            src_in = link.source in node.subtree_nodes
            dst_in = link.target in node.subtree_nodes

            if src_in and dst_in:
                # Internal link
                node.stats.internal_link_count += 1
                node.stats.internal_link_capacity += link.capacity

                # If there's an hw_component on the link, add cost/power
                hw_comp = link.attrs.get("hw_component")
                if hw_comp:
                    comp = self.components_library.get(hw_comp)
                    if comp:
                        node.stats.total_cost += comp.total_cost()
                        node.stats.total_power += comp.total_power()
                    else:
                        logger.warning(
                            "Link '%s->%s' references unknown hw_component '%s'.",
                            link.source,
                            link.target,
                            hw_comp,
                        )
            elif src_in ^ dst_in:
                # External link
                node.stats.external_link_count += 1
                node.stats.external_link_capacity += link.capacity

                other_side = link.target if src_in else link.source
                other_node = self._node_map.get(other_side)
                if other_node:
                    other_path = self._compute_full_path(other_node)
                    bd = node.stats.external_link_details.setdefault(
                        other_path, ExternalLinkBreakdown()
                    )
                    bd.link_count += 1
                    bd.link_capacity += link.capacity

                # Possibly add link optic/hw cost/power
                hw_comp = link.attrs.get("hw_component")
                if hw_comp:
                    comp = self.components_library.get(hw_comp)
                    if comp:
                        node.stats.total_cost += comp.total_cost()
                        node.stats.total_power += comp.total_power()
                    else:
                        logger.warning(
                            "Link '%s->%s' references unknown hw_component '%s'.",
                            link.source,
                            link.target,
                            hw_comp,
                        )

        # 4) Recurse to children
        for child in node.children.values():
            self._aggregate_stats(child)

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
