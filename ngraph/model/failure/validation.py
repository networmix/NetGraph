"""Risk group reference validation.

Validates that all risk group references in nodes and links resolve to
defined risk groups, catching typos and missing definitions early, and
detects cycles in risk group hierarchies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from ngraph.model.network import Network


def validate_risk_group_references(network: "Network") -> None:
    """Check that every risk group named by a node or link is defined.

    Names are checked against network.risk_groups; typos and missing
    definitions would otherwise cause silent failures in simulations.

    Args:
        network: Network with nodes, links, and risk_groups populated.

    Raises:
        ValueError: If any node or link references an undefined risk group.
            The error message lists up to 10 violations with entity names
            and the undefined group names.
    """
    defined: Set[str] = set(network.risk_groups.keys())
    errors: List[str] = []

    for node in network.nodes.values():
        undefined = node.risk_groups - defined
        if undefined:
            errors.append(f"Node '{node.name}': {sorted(undefined)}")

    for link in network.links.values():
        undefined = link.risk_groups - defined
        if undefined:
            errors.append(f"Link '{link.source}->{link.target}': {sorted(undefined)}")

    if errors:
        error_list = "\n  - ".join(errors[:10])
        suffix = f"\n  ... and {len(errors) - 10} more" if len(errors) > 10 else ""

        raise ValueError(
            f"Found {len(errors)} undefined risk group reference(s):\n"
            f"  - {error_list}{suffix}\n\n"
            f"Define these groups in the 'risk_groups' section or remove the references."
        )


def validate_risk_group_hierarchy(network: "Network") -> None:
    """Detect circular references in risk group parent-child relationships.

    Cycles arise when membership rules with scope='risk_group' create mutual
    parent-child relationships. Detection is a DFS over the children hierarchy.

    Args:
        network: Network with risk_groups populated (after membership resolution).

    Raises:
        ValueError: If a cycle is detected, with details about the cycle path.
    """
    children_map: Dict[str, List[str]] = {}
    for rg_name, rg in network.risk_groups.items():
        children_map[rg_name] = [child.name for child in rg.children]

    # DFS cycle detection using coloring:
    # WHITE (0) = unvisited, GRAY (1) = in current path, BLACK (2) = fully processed
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {name: WHITE for name in children_map}
    parent: Dict[str, str] = {}  # Track path for error message

    def dfs(node: str) -> List[str]:
        """Return cycle path if found, empty list otherwise."""
        color[node] = GRAY
        for child in children_map.get(node, []):
            if child not in color:
                # Nested groups are not registered top-level; nothing to visit
                continue
            if color[child] == GRAY:
                # A GRAY child is a back edge; walk parents to rebuild the cycle.
                cycle = [child, node]
                current = node
                while parent.get(current) and parent[current] != child:
                    current = parent[current]
                    cycle.append(current)
                cycle.reverse()
                return cycle
            if color[child] == WHITE:
                parent[child] = node
                result = dfs(child)
                if result:
                    return result
        color[node] = BLACK
        return []

    # Check all nodes (handles disconnected components)
    for rg_name in children_map:
        if color[rg_name] == WHITE:
            cycle = dfs(rg_name)
            if cycle:
                cycle_str = " -> ".join(cycle) + f" -> {cycle[0]}"
                raise ValueError(
                    f"Circular reference in risk group hierarchy: {cycle_str}. "
                    "Check the children lists and any membership rules with "
                    "scope 'risk_group' that add these groups to each other."
                )
