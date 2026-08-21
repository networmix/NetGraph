"""Risk group membership rule resolution.

Resolves policy-based membership rules that auto-assign entities (nodes,
links, risk groups) to risk groups based on attribute conditions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Union

from ngraph.logging import get_logger
from ngraph.model.selectors import (
    EntityScope,
    MatchSpec,
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
    link_path_key,
    match_entity_ids,
    parse_match_spec,
)

if TYPE_CHECKING:
    from ngraph.model.network import Link, Network, Node, RiskGroup

_logger = get_logger(__name__)


@dataclass
class MembershipSpec:
    """Parsed membership rule specification.

    Attributes:
        scope: Type of entities to match ("node", "link", or "risk_group").
        path: Optional regex pattern. For node and risk_group scope it is
            matched against the entity ID; for link scope it is matched
            against the "source|target" key, not the link ID.
        match: Match specification with conditions.
    """

    scope: EntityScope
    path: Optional[str] = None
    match: Optional[MatchSpec] = None


def resolve_membership_rules(network: "Network") -> None:
    """Apply membership rules to populate entity risk_groups sets.

    For each risk group with a `_membership_raw` specification:
    - If scope is "node" or "link": adds the risk group name to each
      matched entity's risk_groups set.
    - If scope is "risk_group": adds matched risk groups as children
      of this risk group (hierarchical membership).

    Args:
        network: Network with risk_groups, nodes, and links populated.

    Note:
        Modifies entities in place. Call after all risk groups are registered
        but before validation.
    """
    # Flattened attribute maps are shared by all membership rules; build each
    # lazily once instead of re-flattening every entity per rule.
    flat_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _flat(scope: str) -> Dict[str, Dict[str, Any]]:
        cached = flat_maps.get(scope)
        if cached is not None:
            return cached
        if scope == "node":
            built = {
                node.name: flatten_node_attrs(node) for node in network.nodes.values()
            }
        elif scope == "link":
            built = {
                link_id: flatten_link_attrs(link, link_id)
                for link_id, link in network.links.items()
            }
        else:
            built = {
                rg.name: flatten_risk_group_attrs(rg)
                for rg in network.risk_groups.values()
            }
        flat_maps[scope] = built
        return built

    for rg_name, rg in network.risk_groups.items():
        if rg._membership_raw is None:
            continue

        try:
            spec = _parse_membership_spec(rg._membership_raw)
        except ValueError as e:
            raise ValueError(
                f"Invalid membership rule for risk group '{rg_name}': {e}"
            ) from e

        matched_count = 0
        if spec.scope == "risk_group":
            # Hierarchical: add matched groups as children
            matched_rgs = _select_risk_groups(network, spec, _flat("risk_group"))
            for matched_rg in matched_rgs:
                # Don't add self-reference
                if matched_rg.name != rg_name:
                    # Avoid duplicates
                    if matched_rg not in rg.children:
                        rg.children.append(matched_rg)
                        matched_count += 1
        else:
            # Add rg_name to each matched entity's risk_groups
            matched_entities = _select_entities(network, spec, _flat(spec.scope))
            matched_count = len(matched_entities)
            for entity in matched_entities:
                entity.risk_groups.add(rg_name)

        _logger.debug(
            "Resolved membership for '%s': scope=%s, matched=%d",
            rg_name,
            spec.scope,
            matched_count,
        )


def _parse_membership_spec(raw: Dict[str, Any]) -> MembershipSpec:
    """Parse raw membership dict into a MembershipSpec.

    Args:
        raw: Raw membership dict from YAML.

    Returns:
        Parsed MembershipSpec.

    Raises:
        ValueError: If 'scope' is missing or is not one of node/link/
            risk_group, or if neither 'path' nor 'match' is given.
    """
    scope = raw.get("scope")
    if not scope:
        raise ValueError(
            "membership requires 'scope' field (node, link, or risk_group)"
        )
    if scope not in ("node", "link", "risk_group"):
        raise ValueError(
            f"scope must be 'node', 'link', or 'risk_group', got '{scope}'"
        )

    path = raw.get("path")
    match_raw = raw.get("match")

    if path is None and match_raw is None:
        raise ValueError("membership requires at least 'path' or 'match'")

    match_spec = None
    if match_raw is not None:
        # Use unified parser with membership-specific defaults
        match_spec = parse_match_spec(
            match_raw,
            default_logic="and",
            require_conditions=True,
            context="membership rule",
        )

    return MembershipSpec(scope=scope, path=path, match=match_spec)


def _match_spec_ids(
    entity_attrs: Dict[str, Dict[str, Any]],
    spec: MembershipSpec,
    path_key: Callable[[str, Dict[str, Any]], str],
) -> Set[str]:
    """Return entity IDs passing the spec's path filter and match conditions.

    Args:
        entity_attrs: Mapping of entity_id -> flattened attribute dict.
        spec: Membership specification with path and match.
        path_key: Maps (entity_id, attrs) to the string the path regex
            matches against (the ID for nodes/risk groups, the
            "source|target" form for links).

    Returns:
        Set of matching entity IDs.
    """
    if spec.path:
        path_pattern = re.compile(spec.path)
        candidate_ids = {
            eid
            for eid, attrs in entity_attrs.items()
            if path_pattern.match(path_key(eid, attrs))
        }
    else:
        candidate_ids = set(entity_attrs.keys())

    if spec.match:
        filtered_attrs = {k: v for k, v in entity_attrs.items() if k in candidate_ids}
        return match_entity_ids(filtered_attrs, spec.match.conditions, spec.match.logic)
    return candidate_ids


def _select_entities(
    network: "Network",
    spec: MembershipSpec,
    entity_attrs: Dict[str, Dict[str, Any]],
) -> List[Union["Node", "Link"]]:
    """Select nodes or links based on path and/or match conditions.

    Args:
        network: Network to search.
        spec: Membership specification with scope ("node" or "link"),
            path, and match.
        entity_attrs: Pre-flattened attribute map for the spec's scope.

    Returns:
        List of matched Node or Link objects.
    """
    if spec.scope == "node":
        matched_ids = _match_spec_ids(entity_attrs, spec, lambda eid, attrs: eid)
        return [network.nodes[node_id] for node_id in matched_ids]

    matched_ids = _match_spec_ids(
        entity_attrs, spec, lambda eid, attrs: link_path_key(attrs)
    )
    return [network.links[link_id] for link_id in matched_ids]


def _select_risk_groups(
    network: "Network",
    spec: MembershipSpec,
    entity_attrs: Dict[str, Dict[str, Any]],
) -> List["RiskGroup"]:
    """Select risk groups based on path and/or match conditions.

    Args:
        network: Network with risk_groups.
        spec: Membership specification with path and match.
        entity_attrs: Pre-flattened risk-group attribute map.

    Returns:
        List of matched RiskGroup objects.
    """
    matched_ids = _match_spec_ids(entity_attrs, spec, lambda eid, attrs: eid)
    return [network.risk_groups[rg_name] for rg_name in matched_ids]
