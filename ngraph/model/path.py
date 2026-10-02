"""Representation of a single routing path.

``Path`` stores a sequence of (node, parallel edges) elements plus a numeric
cost. Paths sort by cost, compare by structure and cost, and support sub-path
extraction, which leaves the cost for the caller to recompute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Iterator, Set, Tuple

from ngraph.types.base import Cost
from ngraph.types.dto import EdgeRef


@dataclass
class Path:
    """Routing path as a sequence of nodes and the parallel edges leaving each.

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
            idx: Element index; negative values count from the end.

        Returns:
            The node name and the parallel edge refs leaving it.
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
            Count of (node, parallel_edges) elements, i.e. hop count plus one.
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
        """Hash the (path, cost) tuple, consistent with ``__eq__``."""
        return hash((self.path, self.cost))

    def __repr__(self) -> str:
        """Return ``Path(<elements>, cost=<cost>)``."""
        return f"Path({self.path}, cost={self.cost})"

    @cached_property
    def edges_seq(self) -> Tuple[Tuple[EdgeRef, ...], ...]:
        """Return the parallel-edge tuples of every path element except the last.

        Returns:
            A tuple of parallel-edge tuples; empty if the path has 1 or fewer
            elements.
        """
        if len(self.path) <= 1:
            return ()
        return tuple(parallel_edges for _, parallel_edges in self.path[:-1])

    @cached_property
    def nodes_seq(self) -> Tuple[str, ...]:
        """Return a tuple of node names in order along the path.

        Returns:
            Node names from source to destination, repeats included.
        """
        return tuple(node for node, _ in self.path)

    def get_sub_path(self, dst_node: str) -> Path:
        """Create a sub-path ending at the specified destination node.

        The original path is truncated at the first occurrence of `dst_node`,
        and the final element gets an empty edge tuple.

        Args:
            dst_node: The node at which to truncate the path.

        Returns:
            A new Path from the original source to `dst_node`. Its cost is
            infinity, signalling that the caller must recompute it.

        Raises:
            ValueError: If `dst_node` is not found in the current path.
        """
        new_elements = []
        found = False

        for node, parallel_edges in self.path:
            if node == dst_node:
                found = True
                new_elements.append((node, ()))
                break

            new_elements.append((node, parallel_edges))

        if not found:
            raise ValueError(f"Node '{dst_node}' not found in path.")

        # Infinite cost signals that recalculation is needed: computing cost
        # from EdgeRefs requires mapping back to graph edges.
        return Path(tuple(new_elements), float("inf"))
