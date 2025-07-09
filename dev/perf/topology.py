#!/usr/bin/env python3
"""Topology generators for performance benchmarking.

This module provides topology generators that create Network instances with
predefined structures and known node/link counts. Each topology validates
that the generated network matches expected dimensions to ensure benchmark
consistency across runs.

The base Topology class defines the interface for all generators, requiring
subclasses to implement _build() and declare expected node/link counts.
Concrete implementations include Clos fabrics and 2D grid topologies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import product
from textwrap import dedent

from ngraph.network import Link, Network, Node
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
        """Build network topology.

        Args:
            seed: Random seed for deterministic generation.

        Returns:
            Network instance with topology-specific structure.
        """
        ...

    def create_network(self, *, seed: int = 42) -> Network:
        """Create network from topology configuration.

        This method builds the network and validates that it matches the
        expected node and link counts to ensure benchmark consistency.

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

    Creates a standard leaf-spine network with full mesh connectivity
    between leaf and spine tiers.
    """

    leaf_count: int = 4
    spine_count: int = 4
    link_capacity: float = 100.0

    # Computed fields set during initialization to avoid repeated calculations
    name: str = ""
    expected_nodes: int = 0
    expected_links: int = 0

    def __post_init__(self) -> None:
        """Calculate topology dimensions and naming.

        Sets name, expected_nodes, and expected_links based on leaf/spine
        counts to enable validation during network creation.
        """
        self.name = f"clos_{self.leaf_count}x{self.spine_count}"
        self.expected_nodes = self.leaf_count + self.spine_count
        self.expected_links = self.leaf_count * self.spine_count

    def _build(self, seed: int) -> Network:
        """Build Clos fabric using scenario YAML generation.

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
              groups:
                leaf:
                  node_count: {self.leaf_count}
                  name_template: "leaf/leaf{{node_num:02d}}"
                  attrs: {{layer: leaf, site_type: core}}
                spine:
                  node_count: {self.spine_count}
                  name_template: "spine/spine{{node_num:02d}}"
                  attrs: {{layer: spine, site_type: core}}
              adjacency:
                - source: /leaf
                  target: /spine
                  pattern: mesh
                  link_params: {{capacity: {self.link_capacity}, cost: 1}}
            """
        ).strip()
        return Scenario.from_yaml(yaml).network


@dataclass
class Grid2DTopology(Topology):
    """m x n 2-D lattice with optional wrap-around (torus).

    Args:
        rows: Number of rows in the grid (≥ 2).
        cols: Number of columns in the grid (≥ 2).
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

    # Computed fields set during initialization to avoid repeated calculations
    name: str = ""
    expected_nodes: int = 0
    expected_links: int = 0

    def __post_init__(self) -> None:
        """Calculate grid dimensions and link counts.

        Validates grid parameters and computes expected node/link counts
        based on grid dimensions and connectivity options.

        Raises:
            ValueError: If rows or cols are less than 2.
        """
        if self.rows < 2 or self.cols < 2:
            raise ValueError("rows and cols must both be ≥ 2")
        self.name = f"{'torus' if self.wrap else 'grid'}_{self.rows}x{self.cols}"
        self.expected_nodes = self.rows * self.cols

        # Calculate expected links by simulating the generation logic
        # This ensures the count matches what _build() actually creates
        expected_edges: set[tuple[str, str]] = set()

        for r, c in product(range(self.rows), range(self.cols)):
            # Add orthogonal connections (right and down)
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

            # Add diagonal connections if enabled
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
            limit: Maximum coordinate value.

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

        # Create nodes with grid coordinates as attributes
        for r, c in product(range(self.rows), range(self.cols)):
            name = f"n{r:03d}_{c:03d}"
            net.add_node(Node(name, attrs={"row": r, "col": c}))

        # Track added edges to prevent duplicates
        added_edges: set[tuple[str, str]] = set()

        # Helper to add bidirectional links with bounds checking
        def add_edge(r1: int, c1: int, r2: int | None, c2: int | None) -> None:
            if r2 is None or c2 is None:
                return  # Skip out-of-bounds connections when wrap is disabled
            u = f"n{r1:03d}_{c1:03d}"
            v = f"n{r2:03d}_{c2:03d}"

            # Prevent duplicate edges
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
            # Add orthogonal connections (right and down)
            add_edge(r, c, r, self._idx(c + 1, self.cols))
            add_edge(r, c, self._idx(r + 1, self.rows), c)

            # Add diagonal connections if enabled
            if self.diag:
                add_edge(r, c, self._idx(r + 1, self.rows), self._idx(c + 1, self.cols))
                add_edge(r, c, self._idx(r - 1, self.rows), self._idx(c + 1, self.cols))
        return net


# Export all available topology classes
ALL_TOPOLOGIES = [
    Clos2TierTopology,
    Grid2DTopology,
]
