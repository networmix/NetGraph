"""Risk group membership rule resolution.

Provides functionality to resolve policy-based membership rules that
auto-assign entities (nodes, links, risk groups) to risk groups based
on attribute conditions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from ngraph.dsl.selectors import (
    EntityScope,
    MatchSpec,
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
    match_entity_ids,
    parse_match_spec,
)
from ngraph.logging import get_logger

if TYPE_CHECKING:
    from ngraph.model.network import Link, Network, Node, RiskGroup

_logger = get_logger(__name__)


@dataclass
class MembershipSpec:
    """Parsed membership rule specification.

    Attributes:
        scope: Type of entities to match ("node", "link", or "risk_group").
        path: Optional regex pattern to filter entities by name.
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
        This function modifies entities in place. It should be called after
        all risk groups are registered but before validation.
    """
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
            matched_rgs = _select_risk_groups(network, spec)
            for matched_rg in matched_rgs:
                # Don't add self-reference
                if matched_rg.name != rg_name:
                    # Avoid duplicates
                    if matched_rg not in rg.children:
                        rg.children.append(matched_rg)
                        matched_count += 1
        else:
            # Add rg_name to each matched entity's risk_groups
            matched_entities = _select_entities(network, spec)
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
        ValueError: If required fields are missing or invalid.
    """
    scope = raw.get("scope", "node")
    if scope not in ("node", "link", "risk_group"):
        raise ValueError(
            f"scope must be 'node', 'link', or 'risk_group', got '{scope}'"
        )

    path = raw.get("path")
    match_raw = raw.get("match")

    # At least one of path or match must be specified
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


def _select_entities(
    network: "Network", spec: MembershipSpec
) -> List[Union["Node", "Link"]]:
    """Select nodes or links based on path and/or match conditions.

    Uses the shared match_entity_ids() function from selectors.

    Args:
        network: Network to search.
        spec: Membership specification with scope, path, and match.

    Returns:
        List of matched Node or Link objects.
    """
    path_pattern = re.compile(spec.path) if spec.path else None

    if spec.scope == "node":
        # Build flattened attrs dict for all nodes
        entity_attrs = {
            node.name: flatten_node_attrs(node) for node in network.nodes.values()
        }
        # Start with all or path-filtered IDs
        if path_pattern:
            candidate_ids = {eid for eid in entity_attrs if path_pattern.match(eid)}
        else:
            candidate_ids = set(entity_attrs.keys())

        # Apply match conditions if specified
        if spec.match:
            filtered_attrs = {
                k: v for k, v in entity_attrs.items() if k in candidate_ids
            }
            matched_ids = match_entity_ids(
                filtered_attrs, spec.match.conditions, spec.match.logic
            )
        else:
            matched_ids = candidate_ids

        return [network.nodes[node_id] for node_id in matched_ids]

    elif spec.scope == "link":
        # Build flattened attrs dict for all links
        entity_attrs = {
            link_id: flatten_link_attrs(link, link_id)
            for link_id, link in network.links.items()
        }
        # Start with all or path-filtered IDs
        if path_pattern:
            candidate_ids = {eid for eid in entity_attrs if path_pattern.match(eid)}
        else:
            candidate_ids = set(entity_attrs.keys())

        # Apply match conditions if specified
        if spec.match:
            filtered_attrs = {
                k: v for k, v in entity_attrs.items() if k in candidate_ids
            }
            matched_ids = match_entity_ids(
                filtered_attrs, spec.match.conditions, spec.match.logic
            )
        else:
            matched_ids = candidate_ids

        return [network.links[link_id] for link_id in matched_ids]

    return []


def _select_risk_groups(network: "Network", spec: MembershipSpec) -> List["RiskGroup"]:
    """Select risk groups based on path and/or match conditions.

    Uses the shared match_entity_ids() function from selectors.

    Args:
        network: Network with risk_groups.
        spec: Membership specification with path and match.

    Returns:
        List of matched RiskGroup objects.
    """
    path_pattern = re.compile(spec.path) if spec.path else None

    # Build flattened attrs dict for all risk groups
    entity_attrs = {
        rg.name: flatten_risk_group_attrs(rg) for rg in network.risk_groups.values()
    }

    # Start with all or path-filtered IDs
    if path_pattern:
        candidate_ids = {eid for eid in entity_attrs if path_pattern.match(eid)}
    else:
        candidate_ids = set(entity_attrs.keys())

    # Apply match conditions if specified
    if spec.match:
        filtered_attrs = {k: v for k, v in entity_attrs.items() if k in candidate_ids}
        matched_ids = match_entity_ids(
            filtered_attrs, spec.match.conditions, spec.match.logic
        )
    else:
        matched_ids = candidate_ids

    return [network.risk_groups[rg_name] for rg_name in matched_ids]
