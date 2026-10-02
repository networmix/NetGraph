#!/usr/bin/env python3
"""Topology generators for performance benchmarking.

Each generator builds a Network with known node and link counts.
``create_network`` rejects a network whose counts differ, so a benchmark size
always refers to the same graph. Subclasses implement ``_build()`` and set the
expected counts. Included: a 2-tier Clos fabric and a 2D grid or torus.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import product
from textwrap import dedent

from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario


class Topology(ABC):
    """Base class for benchmark topology generators.

    Every topology must define expected nodes/links counts and build a Network
    that matches those numbers exactly.
    """

    name: str
    expected_nodes: int
    expected_links: int

    @abstractmethod
    def _build(self, seed: int) -> Network:
        """Build the network without checking counts.

        Args:
            seed: Random seed for deterministic generation.

        Returns:
            The generated network.
        """
        ...

    def create_network(self, *, seed: int = 42) -> Network:
        """Build the network and check it against the expected counts.

        Args:
            seed: Random seed for network generation.

        Returns:
            Network instance matching expected node/link counts.

        Raises:
            ValueError: If generated network doesn't match expected counts.
        """
        net = self._build(seed)
        if (
            len(net.nodes) != self.expected_nodes
            or len(net.links) != self.expected_links
        ):
            raise ValueError(
                f"{self.name}: expected "
                f"{self.expected_nodes} nodes / {self.expected_links} links "
                f"but got {len(net.nodes)} / {len(net.links)}"
            )
        return net


@dataclass
class Clos2TierTopology(Topology):
    """2-tier Clos (leaf-spine) fabric topology.

    Every leaf connects to every spine.
    """

    leaf_count: int = 4
    spine_count: int = 4
    link_capacity: float = 100.0

    # Set by __post_init__ from the parameters above.
    name: str = ""
    expected_nodes: int = 0
    expected_links: int = 0

    def __post_init__(self) -> None:
        """Derive ``name`` and the expected node and link counts."""
        self.name = f"clos_{self.leaf_count}x{self.spine_count}"
        self.expected_nodes = self.leaf_count + self.spine_count
        self.expected_links = self.leaf_count * self.spine_count

    def _build(self, seed: int) -> Network:
        """Build the fabric from a generated scenario YAML.

        Args:
            seed: Random seed for deterministic generation.

        Returns:
            Network with leaf-spine topology and full mesh connectivity.
        """
        yaml = dedent(
            f"""
            seed: {seed}
            network:
              name: "{self.name}"
              nodes:
                leaf:
                  count: {self.leaf_count}
                  template: "leaf{{n:02d}}"
                  attrs: {{layer: leaf, site_type: core}}
                spine:
                  count: {self.spine_count}
                  template: "spine{{n:02d}}"
                  attrs: {{layer: spine, site_type: core}}
              links:
                - source: /leaf
                  target: /spine
                  pattern: mesh
                  capacity: {self.link_capacity}
                  cost: 1
            """
        ).strip()
        return Scenario.from_yaml(yaml).network


@dataclass
class Grid2DTopology(Topology):
    """m x n 2-D lattice with optional wrap-around (torus).

    Args:
        rows: Number of rows in the grid (>= 2).
        cols: Number of columns in the grid (>= 2).
        wrap: If True, connect borders to create torus topology.
        diag: If True, add diagonal connections (8-neighbor grid).
        link_capacity: Capacity for all links in the grid.
        link_cost: Cost for all links in the grid.
    """

    rows: int = 8
    cols: int = 8
    wrap: bool = False
    diag: bool = False
    link_capacity: float = 100.0
    link_cost: float = 1.0

    # Set by __post_init__ from the parameters above.
    name: str = ""
    expected_nodes: int = 0
    expected_links: int = 0

    def __post_init__(self) -> None:
        """Validate the grid size and derive ``name`` and expected counts.

        Raises:
            ValueError: If rows or cols are less than 2.
        """
        if self.rows < 2 or self.cols < 2:
            raise ValueError("rows and cols must both be >= 2")
        self.name = f"{'torus' if self.wrap else 'grid'}_{self.rows}x{self.cols}"
        self.expected_nodes = self.rows * self.cols

        # Replay _build()'s edge rules so wrap-around duplicates are dropped
        # the same way.
        expected_edges: set[tuple[str, str]] = set()

        for r, c in product(range(self.rows), range(self.cols)):
            # Right and down neighbors
            c_next = self._idx(c + 1, self.cols)
            r_next = self._idx(r + 1, self.rows)

            if c_next is not None:
                u = f"n{r:03d}_{c:03d}"
                v = f"n{r:03d}_{c_next:03d}"
                expected_edges.add((u, v))

            if r_next is not None:
                u = f"n{r:03d}_{c:03d}"
                v = f"n{r_next:03d}_{c:03d}"
                expected_edges.add((u, v))

            if self.diag:
                # Diagonal down-right
                if r_next is not None and c_next is not None:
                    u = f"n{r:03d}_{c:03d}"
                    v = f"n{r_next:03d}_{c_next:03d}"
                    expected_edges.add((u, v))

                # Diagonal up-right
                r_prev = self._idx(r - 1, self.rows)
                if r_prev is not None and c_next is not None:
                    u = f"n{r:03d}_{c:03d}"
                    v = f"n{r_prev:03d}_{c_next:03d}"
                    expected_edges.add((u, v))

        self.expected_links = len(expected_edges)

    def _idx(self, i: int, limit: int) -> int | None:
        """Convert grid coordinate with optional wrap-around.

        Args:
            i: Grid coordinate to convert.
            limit: Dimension size; valid coordinates are 0 to limit - 1.

        Returns:
            Wrapped coordinate if wrap is enabled, or None if out of bounds.
        """
        return (i + limit) % limit if self.wrap else (i if 0 <= i < limit else None)

    def _build(self, seed: int) -> Network:
        """Build 2D grid topology with optional torus and diagonal connections.

        Args:
            seed: Random seed (unused but required by interface).

        Returns:
            Network with 2D grid structure and specified connectivity.
        """
        net = Network()

        for r, c in product(range(self.rows), range(self.cols)):
            name = f"n{r:03d}_{c:03d}"
            net.add_node(Node(name, attrs={"row": r, "col": c}))

        # With wrap, diag, and rows == 2, both diagonals yield the same edge.
        added_edges: set[tuple[str, str]] = set()

        def add_edge(r1: int, c1: int, r2: int | None, c2: int | None) -> None:
            if r2 is None or c2 is None:
                return  # Skip out-of-bounds connections when wrap is disabled
            u = f"n{r1:03d}_{c1:03d}"
            v = f"n{r2:03d}_{c2:03d}"

            if (u, v) in added_edges:
                return
            added_edges.add((u, v))

            net.add_link(
                Link(
                    source=u,
                    target=v,
                    capacity=self.link_capacity,
                    cost=self.link_cost,
                )
            )

        for r, c in product(range(self.rows), range(self.cols)):
            # Right and down neighbors, then the two right-hand diagonals
            add_edge(r, c, r, self._idx(c + 1, self.cols))
            add_edge(r, c, self._idx(r + 1, self.rows), c)

            if self.diag:
                add_edge(r, c, self._idx(r + 1, self.rows), self._idx(c + 1, self.cols))
                add_edge(r, c, self._idx(r - 1, self.rows), self._idx(c + 1, self.cols))
        return net


# Topology classes listed by `perf show topology`
ALL_TOPOLOGIES = [
    Clos2TierTopology,
    Grid2DTopology,
]
