"""Risk group membership rule resolution.

Provides functionality to resolve policy-based membership rules that
auto-assign entities (nodes, links, risk groups) to risk groups based
on attribute conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Union

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
        entity_scope: Type of entities to match ("node", "link", or "risk_group").
        match: Match specification with conditions.
    """

    entity_scope: EntityScope
    match: MatchSpec


def resolve_membership_rules(network: "Network") -> None:
    """Apply membership rules to populate entity risk_groups sets.

    For each risk group with a `_membership_raw` specification:
    - If entity_scope is "node" or "link": adds the risk group name to each
      matched entity's risk_groups set.
    - If entity_scope is "risk_group": adds matched risk groups as children
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
        if spec.entity_scope == "risk_group":
            # Hierarchical: add matched groups as children
            matched_rgs = _select_risk_groups(network, spec.match)
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
            spec.entity_scope,
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
    entity_scope = raw.get("entity_scope", "node")
    if entity_scope not in ("node", "link", "risk_group"):
        raise ValueError(
            f"entity_scope must be 'node', 'link', or 'risk_group', got '{entity_scope}'"
        )

    match_raw = raw.get("match")
    if match_raw is None:
        raise ValueError("membership requires a 'match' block")

    # Use unified parser with membership-specific defaults
    match_spec = parse_match_spec(
        match_raw,
        default_logic="and",
        require_conditions=True,
        context="membership rule",
    )

    return MembershipSpec(entity_scope=entity_scope, match=match_spec)


def _select_entities(
    network: "Network", spec: MembershipSpec
) -> List[Union["Node", "Link"]]:
    """Select nodes or links based on match conditions.

    Uses the shared match_entity_ids() function from selectors.

    Args:
        network: Network to search.
        spec: Membership specification with entity_scope and match.

    Returns:
        List of matched Node or Link objects.
    """
    if spec.entity_scope == "node":
        # Build flattened attrs dict for all nodes
        entity_attrs = {
            node.name: flatten_node_attrs(node) for node in network.nodes.values()
        }
        matched_ids = match_entity_ids(
            entity_attrs, spec.match.conditions, spec.match.logic
        )
        return [network.nodes[node_id] for node_id in matched_ids]

    elif spec.entity_scope == "link":
        # Build flattened attrs dict for all links
        entity_attrs = {
            link_id: flatten_link_attrs(link, link_id)
            for link_id, link in network.links.items()
        }
        matched_ids = match_entity_ids(
            entity_attrs, spec.match.conditions, spec.match.logic
        )
        return [network.links[link_id] for link_id in matched_ids]

    return []


def _select_risk_groups(network: "Network", match: MatchSpec) -> List["RiskGroup"]:
    """Select risk groups based on match conditions.

    Uses the shared match_entity_ids() function from selectors.

    Args:
        network: Network with risk_groups.
        match: Match specification with conditions.

    Returns:
        List of matched RiskGroup objects.
    """
    # Build flattened attrs dict for all risk groups
    entity_attrs = {
        rg.name: flatten_risk_group_attrs(rg) for rg in network.risk_groups.values()
    }
    matched_ids = match_entity_ids(entity_attrs, match.conditions, match.logic)
    return [network.risk_groups[rg_name] for rg_name in matched_ids]
