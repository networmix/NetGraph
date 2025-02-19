from __future__ import annotations
from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterator, Set, Tuple

from ngraph.lib.algorithms.base import Cost, PathTuple
from ngraph.lib.graph import EdgeID, StrictMultiDiGraph, NodeID


@dataclass
class Path:
    """
    Represents a single path in the network.

    Attributes:
        path_tuple (PathTuple):
            A sequence of path elements. Each element is (node_id, (edge_id_1, edge_id_2, ...)),
            where the last element typically has an empty tuple of edges.
        cost (Cost):
            The total numeric cost (e.g., distance, metric) of this path.
        edges (Set[EdgeID]):
            A set of all edge IDs encountered in `path_tuple`.
        nodes (Set[NodeID]):
            A set of all node IDs encountered in `path_tuple`.
        edge_tuples (Set[Tuple[EdgeID, ...]]):
            A set of the edge tuples (parallel edges) from each path element.
            Includes the empty tuple for the final element.

    Example:
        >>> from ngraph.lib.graph import StrictMultiDiGraph
        >>> graph = StrictMultiDiGraph()
        >>> for n in ("A","B","C"):
        ...     graph.add_node(n)
        >>> eAB = graph.add_edge("A", "B", metric=5)
        >>> eBC = graph.add_edge("B", "C", metric=7)
        >>> p = Path(
        ...     path_tuple=(
        ...         ("A", (eAB,)),
        ...         ("B", (eBC,)),
        ...         ("C", ()),
        ...     ),
        ...     cost=12
        ... )
        >>> p.src_node
        'A'
        >>> p.dst_node
        'C'
        >>> p.edges
        {<edge_id_for_AB>, <edge_id_for_BC>}
        >>> p.nodes
        {'A', 'B', 'C'}
        >>> subp = p.get_sub_path("B", graph)
        >>> subp.cost
        5
    """

    path_tuple: PathTuple
    cost: Cost
    edges: Set[EdgeID] = field(init=False, default_factory=set, repr=False)
    nodes: Set[NodeID] = field(init=False, default_factory=set, repr=False)
    edge_tuples: Set[Tuple[EdgeID, ...]] = field(
        init=False, default_factory=set, repr=False
    )

    def __post_init__(self) -> None:
        """Populate `edges`, `nodes`, and `edge_tuples` from `path_tuple`."""
        for node, parallel_edges in self.path_tuple:
            self.nodes.add(node)
            self.edges.update(parallel_edges)
            self.edge_tuples.add(parallel_edges)

    def __getitem__(self, idx: int) -> Tuple[NodeID, Tuple[EdgeID, ...]]:
        """Return the (node, parallel_edges) tuple at the given index.

        Args:
            idx: The index of the path element.

        Returns:
            The (node, parallel_edges) element at the given index.
        """
        return self.path_tuple[idx]

    def __iter__(self) -> Iterator[Tuple[NodeID, Tuple[EdgeID, ...]]]:
        """Iterate over each (node, parallel_edges) element in the path.

        Yields:
            Elements of `path_tuple`.
        """
        return iter(self.path_tuple)

    def __len__(self) -> int:
        """Return the number of elements in this path.

        Returns:
            The length of `path_tuple`.
        """
        return len(self.path_tuple)

    @property
    def src_node(self) -> NodeID:
        """Return the first node in the path (source)."""
        return self.path_tuple[0][0]

    @property
    def dst_node(self) -> NodeID:
        """Return the last node in the path (destination)."""
        return self.path_tuple[-1][0]

    def __lt__(self, other: Path) -> bool:
        """Compare two paths by their cost.

        Args:
            other: Another Path instance.

        Returns:
            True if `self.cost < other.cost`, else False.
        """
        return self.cost < other.cost

    def __eq__(self, other: Path) -> bool:
        """Check equality by path structure and cost.

        Args:
            other: Another Path instance.

        Returns:
            True if both `path_tuple` and `cost` match.
        """
        return (self.path_tuple == other.path_tuple) and (self.cost == other.cost)

    def __hash__(self) -> int:
        """Compute a hash based on `(path_tuple, cost)` for sets/dicts.

        Returns:
            The hash value of the path.
        """
        return hash((self.path_tuple, self.cost))

    def __repr__(self) -> str:
        """Return a string representation of this Path.

        Returns:
            Debug representation, including path_tuple and cost.
        """
        return f"Path({self.path_tuple}, cost={self.cost})"

    @cached_property
    def edges_seq(self) -> Tuple[Tuple[EdgeID, ...], ...]:
        """Return a tuple of parallel-edge sets for each path element except the last.

        The final path element typically has no outgoing edges (empty tuple).

        Returns:
            Parallel-edge sets from the path elements excluding the last one.
        """
        if len(self.path_tuple) <= 1:
            return ()
        return tuple(parallel_edges for _, parallel_edges in self.path_tuple[:-1])

    @cached_property
    def nodes_seq(self) -> Tuple[NodeID, ...]:
        """Return a tuple of all node IDs in order along this path.

        Returns:
            The ordered node IDs from source to destination.
        """
        return tuple(node for node, _ in self.path_tuple)

    def get_sub_path(
        self,
        dst_node: NodeID,
        graph: StrictMultiDiGraph,
        cost_attr: str = "metric",
    ) -> Path:
        """Create a sub-path ending at `dst_node`, recalculating cost.

        Truncates the path upon encountering `dst_node`, ensuring the final
        element has an empty tuple of edges. If `dst_node` is not found in
        `path_tuple`, raises a ValueError.

        Args:
            dst_node: The node at which the path is truncated.
            graph: The graph containing edge attributes.
            cost_attr: The attribute name for edge cost (default "metric").

        Returns:
            A new `Path` from the original source up to (and including) `dst_node`.

        Raises:
            ValueError: If `dst_node` does not occur in this path.
        """
        edges_map = graph.get_edges()
        new_elements = []
        new_cost = 0.0
        found = False

        for node, parallel_edges in self.path_tuple:
            if node == dst_node:
                # We have reached our target node: store it with an empty edge set
                found = True
                new_elements.append((node, ()))
                break

            # Otherwise, keep the existing edges and accumulate cost
            new_elements.append((node, parallel_edges))
            if parallel_edges:
                new_cost += min(
                    edges_map[e_id][3][cost_attr] for e_id in parallel_edges
                )

        if not found:
            raise ValueError(f"Node '{dst_node}' not found in path.")

        return Path(tuple(new_elements), new_cost)
