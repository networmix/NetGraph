"""Node selection and evaluation.

`select_nodes()` combines regex matching, attribute filtering, active-only
filtering, and grouping; the flatten helpers build the attribute dicts that
condition evaluation runs against.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Set

from .conditions import evaluate_conditions
from .schema import Condition, MatchSpec, NodeSelector

if TYPE_CHECKING:
    from ngraph.model.network import Link, Network, Node, RiskGroup

__all__ = [
    "select_nodes",
    "flatten_node_attrs",
    "flatten_link_attrs",
    "flatten_risk_group_attrs",
    "link_path_key",
    "match_entity_ids",
]


def select_nodes(
    network: "Network",
    selector: NodeSelector,
    default_active_only: bool,
) -> Dict[str, List["Node"]]:
    """Unified entry point for node selection.

    Evaluation order:
    1. Select nodes matching `path` regex (or all nodes if path is None)
    2. Filter by `match` conditions
    3. Filter by `active_only` flag
    4. Group by `group_by` attribute (overrides regex capture grouping)

    Args:
        network: Network whose nodes are searched.
        selector: Node selection specification.
        default_active_only: Used when the selector leaves `active_only`
            unset. Required rather than defaulted so callers cannot silently
            inherit the wrong policy.

    Returns:
        Dict mapping group labels to lists of nodes. Groups that filter down
        to nothing are dropped.
    """
    # Resolve effective active_only flag
    active_only = (
        selector.active_only
        if selector.active_only is not None
        else default_active_only
    )

    # Step 1: Select by path regex (or all nodes). Regex selection delegates
    # to Network.select_node_groups_by_path() which provides caching.
    if selector.path is not None:
        candidates = network.select_node_groups_by_path(selector.path)
    else:
        candidates = {"_all_": list(network.nodes.values())}

    # Step 2: Apply match conditions
    if selector.match is not None:
        candidates = _filter_by_match(candidates, selector.match)

    # Step 3: Filter active only
    if active_only:
        candidates = _filter_active(candidates)

    # Step 4: Apply grouping (overrides regex capture grouping)
    if selector.group_by is not None:
        return _group_by_attribute(candidates, selector.group_by)

    return candidates


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
        # Sorted for deterministic group_by labels and ==/in comparisons.
        "risk_groups": sorted(node.risk_groups),
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
        # Sorted for deterministic group_by labels and ==/in comparisons.
        "risk_groups": sorted(link.risk_groups),
    }
    attrs.update({k: v for k, v in link.attrs.items() if k not in attrs})
    return attrs


def link_path_key(attrs: Dict[str, Any]) -> str:
    """Return the "source|target" key used when path-matching links.

    Links have no name of their own, so path regexes match against this
    canonical endpoint-pair form of the flattened link attributes.
    """
    return f"{attrs['source']}|{attrs['target']}"


def flatten_risk_group_attrs(rg: "RiskGroup") -> Dict[str, Any]:
    """Build flat attribute dict for condition evaluation on risk groups.

    Merges risk group's top-level fields (name, disabled, children) with
    rg.attrs. Top-level fields take precedence on key conflicts.

    Args:
        rg: RiskGroup object.

    Returns:
        Flat dict suitable for condition evaluation.
    """
    attrs: Dict[str, Any] = {
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


def _filter_active(
    groups: Dict[str, List["Node"]],
) -> Dict[str, List["Node"]]:
    """Remove disabled nodes, dropping groups that become empty."""
    result: Dict[str, List["Node"]] = {}
    for label, nodes in groups.items():
        filtered = [n for n in nodes if not n.disabled]
        if filtered:
            result[label] = filtered
    return result


_MISSING = object()


def _node_attr_value(node: "Node", attr_name: str) -> Any:
    """Resolve a single node attribute without building the full flat dict.

    Mirrors flatten_node_attrs semantics: top-level fields (name, disabled,
    risk_groups) take precedence over node.attrs. Returns _MISSING when the
    attribute is absent.
    """
    if attr_name == "name":
        return node.name
    if attr_name == "disabled":
        return node.disabled
    if attr_name == "risk_groups":
        # Sorted for deterministic group_by labels.
        return sorted(node.risk_groups)
    return node.attrs.get(attr_name, _MISSING)


def _group_by_attribute(
    groups: Dict[str, List["Node"]],
    attr_name: str,
) -> Dict[str, List["Node"]]:
    """Re-group nodes by attribute value.

    Supports both top-level fields (name, disabled, risk_groups) and custom
    attrs, consistent with match condition evaluation. Nodes lacking the
    attribute are dropped.

    Note: This discards any existing grouping (including regex captures).
    """
    result: Dict[str, List["Node"]] = {}
    for nodes in groups.values():
        for node in nodes:
            value = _node_attr_value(node, attr_name)
            if value is not _MISSING:
                result.setdefault(str(value), []).append(node)
    return result
