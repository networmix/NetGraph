"""Lightweight representation of a single routing path.

The ``Path`` dataclass stores a node-and-parallel-edges sequence and a numeric
cost. Cached properties expose derived sequences for nodes and edges, and
helpers provide equality, ordering by cost, and sub-path extraction with cost
recalculation.

Breaking change from v1.x: Edge references now use EdgeRef (link_id + direction)
instead of integer edge keys for stable scenario-level edge identification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, Iterator, Set, Tuple

from ngraph.types.base import Cost
from ngraph.types.dto import EdgeRef

if TYPE_CHECKING:
    from netgraph_core import StrictMultiDiGraph


@dataclass
class Path:
    """Represents a single path in the network.

    Breaking change from v1.x: path field now uses EdgeRef (link_id + direction)
    instead of integer edge keys for stable scenario-level edge identification.

    Attributes:
        path: Sequence of (node_name, (edge_refs...)) tuples representing the path.
              The final element typically has an empty tuple of edge refs.
        cost: Total numeric cost (e.g., distance or metric) of the path.
        edges: Set of all EdgeRefs encountered in the path.
        nodes: Set of all node names encountered in the path.
        edge_tuples: Set of all tuples of parallel EdgeRefs from each path element.
    """

    path: Tuple[Tuple[str, Tuple[EdgeRef, ...]], ...]
    cost: Cost
    edges: Set[EdgeRef] = field(init=False, default_factory=set, repr=False)
    nodes: Set[str] = field(init=False, default_factory=set, repr=False)
    edge_tuples: Set[Tuple[EdgeRef, ...]] = field(
        init=False, default_factory=set, repr=False
    )

    def __post_init__(self) -> None:
        """Populate `edges`, `nodes`, and `edge_tuples` from `path`."""
        for node, parallel_edges in self.path:
            self.nodes.add(node)
            self.edges.update(parallel_edges)
            self.edge_tuples.add(parallel_edges)

    def __getitem__(self, idx: int) -> Tuple[str, Tuple[EdgeRef, ...]]:
        """Return the (node, parallel_edges) tuple at the specified index.

        Args:
            idx: The index of the desired path element.

        Returns:
            A tuple containing the node name and its associated parallel edge refs.
        """
        return self.path[idx]

    def __iter__(self) -> Iterator[Tuple[str, Tuple[EdgeRef, ...]]]:
        """Iterate over each (node, parallel_edges) element in the path.

        Yields:
            Each element from `path` in order.
        """
        return iter(self.path)

    def __len__(self) -> int:
        """Return the number of elements in the path.

        Returns:
            The length of `path`.
        """
        return len(self.path)

    @property
    def src_node(self) -> str:
        """Return the first node in the path (the source node)."""
        return self.path[0][0]

    @property
    def dst_node(self) -> str:
        """Return the last node in the path (the destination node)."""
        return self.path[-1][0]

    def __lt__(self, other: Any) -> bool:
        """Compare two paths based on their cost.

        Args:
            other: Another Path instance.

        Returns:
            True if this path's cost is less than the other's cost; otherwise, False.
            Returns NotImplemented if `other` is not a Path.
        """
        if not isinstance(other, Path):
            return NotImplemented
        return self.cost < other.cost

    def __eq__(self, other: Any) -> bool:
        """Check equality by comparing path structure and cost.

        Args:
            other: Another Path instance.

        Returns:
            True if both the `path` and `cost` are equal; otherwise, False.
            Returns NotImplemented if `other` is not a Path.
        """
        if not isinstance(other, Path):
            return NotImplemented
        return (self.path == other.path) and (self.cost == other.cost)

    def __hash__(self) -> int:
        """Compute a hash based on the (path, cost) tuple.

        Returns:
            The hash value of this Path.
        """
        return hash((self.path, self.cost))

    def __repr__(self) -> str:
        """Return a string representation of the path including its tuple and cost.

        Returns:
            A debug-friendly string representation.
        """
        return f"Path({self.path}, cost={self.cost})"

    @cached_property
    def edges_seq(self) -> Tuple[Tuple[EdgeRef, ...], ...]:
        """Return a tuple containing the sequence of parallel-edge tuples for each path element except the last.

        Returns:
            A tuple of parallel-edge tuples; returns an empty tuple if the path has 1 or fewer elements.
        """
        if len(self.path) <= 1:
            return ()
        return tuple(parallel_edges for _, parallel_edges in self.path[:-1])

    @cached_property
    def nodes_seq(self) -> Tuple[str, ...]:
        """Return a tuple of node names in order along the path.

        Returns:
            A tuple containing the ordered sequence of nodes from source to destination.
        """
        return tuple(node for node, _ in self.path)

    def get_sub_path(
        self,
        dst_node: str,
        graph: StrictMultiDiGraph | None = None,
        cost_attr: str = "cost",
    ) -> Path:
        """Create a sub-path ending at the specified destination node.

        The sub-path is formed by truncating the original path at the first occurrence
        of `dst_node` and ensuring that the final element has an empty tuple of edges.

        Note: With EdgeRef-based paths, cost recalculation requires graph lookup.
        The graph parameter is reserved for future implementation. Currently, cost
        is set to infinity to explicitly indicate it needs recalculation. Check for
        `math.isinf(sub_path.cost)` if you need the actual cost.

        Args:
            dst_node: The node at which to truncate the path.
            graph: Reserved for future cost recalculation (currently unused).
            cost_attr: Reserved for future cost recalculation (currently unused).

        Returns:
            A new Path instance representing the sub-path from the original source
            to `dst_node`. Cost is set to infinity to indicate recalculation needed.

        Raises:
            ValueError: If `dst_node` is not found in the current path.
        """
        # Suppress unused parameter warnings - reserved for future cost recalculation
        _ = graph, cost_attr

        new_elements = []
        found = False

        for node, parallel_edges in self.path:
            if node == dst_node:
                found = True
                # Append the target node with an empty edge tuple.
                new_elements.append((node, ()))
                break

            new_elements.append((node, parallel_edges))

        if not found:
            raise ValueError(f"Node '{dst_node}' not found in path.")

        # Cost set to infinity to explicitly signal recalculation is needed.
        # EdgeRef-based cost calculation requires mapping back to graph edges.
        return Path(tuple(new_elements), float("inf"))
