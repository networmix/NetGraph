"""Risk group reference validation.

Validates that all risk group references in nodes and links resolve to
defined risk groups. Catches typos and missing definitions early.

Also provides cycle detection for risk group hierarchies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from ngraph.model.network import Network


def validate_risk_group_references(network: "Network") -> None:
    """Ensure all risk group references resolve to defined groups.

    Checks that every risk group name referenced by nodes and links
    exists in network.risk_groups. This catches typos and missing
    definitions that would otherwise cause silent failures in simulations.

    Args:
        network: Network with nodes, links, and risk_groups populated.

    Raises:
        ValueError: If any node or link references an undefined risk group.
            The error message lists up to 10 violations with entity names
            and the undefined group names.
    """
    defined: Set[str] = set(network.risk_groups.keys())
    errors: List[str] = []

    # Check nodes
    for node in network.nodes.values():
        undefined = node.risk_groups - defined
        if undefined:
            errors.append(f"Node '{node.name}': {sorted(undefined)}")

    # Check links
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

    Uses DFS-based cycle detection to find any risk group that is part of
    a cycle in the children hierarchy. This can happen when membership rules
    with entity_scope='risk_group' create mutual parent-child relationships.

    Args:
        network: Network with risk_groups populated (after membership resolution).

    Raises:
        ValueError: If a cycle is detected, with details about the cycle path.
    """
    # Build adjacency from parent -> children names
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
                # Child not in risk_groups (shouldn't happen after validation)
                continue
            if color[child] == GRAY:
                # Found cycle - reconstruct path
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
                    f"Circular reference detected in risk group hierarchy:\n"
                    f"  {cycle_str}\n\n"
                    f"Risk groups cannot form cycles in their parent-child relationships. "
                    f"This may be caused by membership rules with entity_scope='risk_group' "
                    f"that create mutual parent-child relationships. Review the membership "
                    f"rules for these groups and adjust conditions to break the cycle."
                )
