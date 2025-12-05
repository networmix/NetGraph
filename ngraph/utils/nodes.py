"""Node utility functions for filtering and selection.

Provides centralized helpers for filtering active (non-disabled) nodes,
used across analysis, workflows, and demand expansion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set

if TYPE_CHECKING:
    from ngraph.model.network import Node


def get_active_node_names(
    nodes: Iterable["Node"],
    excluded_nodes: Optional[Set[str]] = None,
) -> List[str]:
    """Extract names of active (non-disabled) nodes, optionally excluding some.

    Args:
        nodes: Iterable of Node objects to filter.
        excluded_nodes: Optional set of node names to exclude.

    Returns:
        List of node names that are not disabled and not in excluded_nodes.
    """
    if excluded_nodes:
        return [
            n.name for n in nodes if not n.disabled and n.name not in excluded_nodes
        ]
    return [n.name for n in nodes if not n.disabled]


def get_active_nodes(
    nodes: Iterable["Node"],
    excluded_nodes: Optional[Set[str]] = None,
) -> List["Node"]:
    """Extract active (non-disabled) nodes, optionally excluding some.

    Args:
        nodes: Iterable of Node objects to filter.
        excluded_nodes: Optional set of node names to exclude.

    Returns:
        List of Node objects that are not disabled and not in excluded_nodes.
    """
    if excluded_nodes:
        return [n for n in nodes if not n.disabled and n.name not in excluded_nodes]
    return [n for n in nodes if not n.disabled]


def collect_active_node_names_from_groups(
    groups: Dict[str, List["Node"]],
    excluded_nodes: Optional[Set[str]] = None,
) -> List[str]:
    """Extract active (non-disabled) node names from selection groups dict.

    Flattens all group values and filters to active nodes.

    Args:
        groups: Dictionary mapping group labels to lists of Node objects.
        excluded_nodes: Optional set of node names to exclude.

    Returns:
        List of node names from all groups that are active.
    """
    result: List[str] = []
    for nodes in groups.values():
        result.extend(get_active_node_names(nodes, excluded_nodes))
    return result


def collect_active_nodes_from_groups(
    groups: Dict[str, List["Node"]],
    excluded_nodes: Optional[Set[str]] = None,
) -> List["Node"]:
    """Extract active (non-disabled) nodes from selection groups dict.

    Flattens all group values and filters to active nodes.

    Args:
        groups: Dictionary mapping group labels to lists of Node objects.
        excluded_nodes: Optional set of node names to exclude.

    Returns:
        List of Node objects from all groups that are active.
    """
    result: List["Node"] = []
    for nodes in groups.values():
        result.extend(get_active_nodes(nodes, excluded_nodes))
    return result
