"""Node selection and evaluation.

Provides the unified select_nodes() function that handles regex matching,
attribute filtering, active-only filtering, and grouping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

from .conditions import evaluate_conditions
from .schema import Condition, MatchSpec, NodeSelector

if TYPE_CHECKING:
    from ngraph.model.network import Link, Network, Node, RiskGroup

__all__ = [
    "select_nodes",
    "flatten_node_attrs",
    "flatten_link_attrs",
    "flatten_risk_group_attrs",
    "match_entity_ids",
]


def select_nodes(
    network: "Network",
    selector: NodeSelector,
    default_active_only: bool,
    excluded_nodes: Optional[Set[str]] = None,
) -> Dict[str, List["Node"]]:
    """Unified entry point for node selection.

    Evaluation order:
    1. Select nodes matching `path` regex (or all nodes if path is None)
    2. Filter by `match` conditions
    3. Filter by `active_only` flag and excluded_nodes
    4. Group by `group_by` attribute (overrides regex capture grouping)

    Args:
        network: The network graph.
        selector: Node selection specification.
        default_active_only: Context-aware default for active_only flag.
            Required parameter to prevent silent bugs.
        excluded_nodes: Additional node names to exclude.

    Returns:
        Dict mapping group labels to lists of nodes.
    """
    excluded = excluded_nodes or set()

    # Resolve effective active_only flag
    active_only = (
        selector.active_only
        if selector.active_only is not None
        else default_active_only
    )

    # Step 1: Select by path regex (or all nodes)
    if selector.path is not None:
        candidates = _select_by_regex(network, selector.path)
    else:
        candidates = {"_all_": list(network.nodes.values())}

    # Step 2: Apply match conditions
    if selector.match is not None:
        candidates = _filter_by_match(candidates, selector.match)

    # Step 3: Filter active only + excluded
    if active_only or excluded:
        candidates = _filter_active_and_excluded(candidates, active_only, excluded)

    # Step 4: Apply grouping (overrides regex capture grouping)
    if selector.group_by is not None:
        return _group_by_attribute(candidates, selector.group_by)

    return candidates


def _select_by_regex(network: "Network", pattern: str) -> Dict[str, List["Node"]]:
    """Select nodes by regex pattern with capture group handling.

    Delegates to Network.select_node_groups_by_path() which provides caching.
    """
    return network.select_node_groups_by_path(pattern)


def _filter_by_match(
    groups: Dict[str, List["Node"]],
    match: MatchSpec,
) -> Dict[str, List["Node"]]:
    """Filter nodes in each group by match conditions."""
    result: Dict[str, List["Node"]] = {}
    for label, nodes in groups.items():
        filtered = [n for n in nodes if _node_matches(n, match)]
        if filtered:
            result[label] = filtered
    return result


def _node_matches(node: "Node", match: MatchSpec) -> bool:
    """Check if a node matches the match specification."""
    attrs = flatten_node_attrs(node)
    return evaluate_conditions(attrs, match.conditions, match.logic)


def flatten_node_attrs(node: "Node") -> Dict[str, Any]:
    """Build flat attribute dict for condition evaluation.

    Merges node's top-level fields (name, disabled, risk_groups) with
    node.attrs. Top-level fields take precedence on key conflicts.

    Args:
        node: Node object to flatten.

    Returns:
        Flat dict suitable for condition evaluation.
    """
    attrs: Dict[str, Any] = {
        "name": node.name,
        "disabled": node.disabled,
        "risk_groups": list(node.risk_groups),
    }
    # Add user attrs, but don't overwrite top-level fields
    attrs.update({k: v for k, v in node.attrs.items() if k not in attrs})
    return attrs


def flatten_link_attrs(link: "Link", link_id: str) -> Dict[str, Any]:
    """Build flat attribute dict for condition evaluation on links.

    Merges link's top-level fields with link.attrs. Top-level fields
    take precedence on key conflicts.

    Args:
        link: Link object to flatten.
        link_id: The link's ID in the network.

    Returns:
        Flat dict suitable for condition evaluation.
    """
    attrs: Dict[str, Any] = {
        "id": link_id,
        "source": link.source,
        "target": link.target,
        "capacity": link.capacity,
        "cost": link.cost,
        "disabled": link.disabled,
        "risk_groups": list(link.risk_groups),
    }
    attrs.update({k: v for k, v in link.attrs.items() if k not in attrs})
    return attrs


def flatten_risk_group_attrs(
    rg: Union["RiskGroup", Dict[str, Any]],
) -> Dict[str, Any]:
    """Build flat attribute dict for condition evaluation on risk groups.

    Merges risk group's top-level fields (name, disabled, children) with
    rg.attrs. Top-level fields take precedence on key conflicts.

    Supports both RiskGroup objects and dict representations (for flexibility
    in failure policy matching).

    Args:
        rg: RiskGroup object or dict representation.

    Returns:
        Flat dict suitable for condition evaluation.
    """
    if isinstance(rg, dict):
        # Dict representation
        children_raw = rg.get("children", [])
        child_names = [
            c.get("name") if isinstance(c, dict) else c.name for c in children_raw
        ]
        attrs: Dict[str, Any] = {
            "name": rg.get("name", ""),
            "disabled": rg.get("disabled", False),
            "children": child_names,
        }
        attrs.update({k: v for k, v in rg.get("attrs", {}).items() if k not in attrs})
    else:
        # RiskGroup object
        attrs = {
            "name": rg.name,
            "disabled": rg.disabled,
            "children": [c.name for c in rg.children],
        }
        attrs.update({k: v for k, v in rg.attrs.items() if k not in attrs})

    return attrs


def match_entity_ids(
    entity_attrs: Dict[str, Dict[str, Any]],
    conditions: List[Condition],
    logic: str = "or",
) -> Set[str]:
    """Match entity IDs by attribute conditions.

    General primitive for condition-based entity selection. Works with
    any entity type as long as attributes are pre-flattened.

    Args:
        entity_attrs: Mapping of {entity_id: flattened_attrs_dict}
        conditions: List of conditions to evaluate
        logic: "and" (all must match) or "or" (any must match)

    Returns:
        Set of matching entity IDs. Returns all IDs if conditions is empty.
    """
    if not conditions:
        return set(entity_attrs.keys())

    return {
        entity_id
        for entity_id, attrs in entity_attrs.items()
        if evaluate_conditions(attrs, conditions, logic)
    }


def _filter_active_and_excluded(
    groups: Dict[str, List["Node"]],
    active_only: bool,
    excluded: Set[str],
) -> Dict[str, List["Node"]]:
    """Remove disabled and/or explicitly excluded nodes."""
    result: Dict[str, List["Node"]] = {}
    for label, nodes in groups.items():
        filtered = []
        for n in nodes:
            if n.name in excluded:
                continue
            if active_only and n.disabled:
                continue
            filtered.append(n)
        if filtered:
            result[label] = filtered
    return result


def _group_by_attribute(
    groups: Dict[str, List["Node"]],
    attr_name: str,
) -> Dict[str, List["Node"]]:
    """Re-group nodes by attribute value.

    Uses flatten_node_attrs to support both top-level fields (name, disabled,
    risk_groups) and custom attrs, consistent with match condition evaluation.

    Note: This discards any existing grouping (including regex captures).
    """
    result: Dict[str, List["Node"]] = {}
    for nodes in groups.values():
        for node in nodes:
            flat_attrs = flatten_node_attrs(node)
            if attr_name in flat_attrs:
                key = str(flat_attrs[attr_name])
                result.setdefault(key, []).append(node)
    return result
