"""Unified node selection for NetGraph DSL.

Selector parsing for YAML configs: the single abstraction for node selection
used across adjacency, demands, overrides, and workflow steps. The schema
types and the runtime evaluation engine live in `ngraph.model.selectors`;
they are re-exported here for backward compatibility.

Usage:
    from ngraph.dsl.selectors import normalize_selector, select_nodes, NodeSelector

    # From YAML config (string or dict)
    selector = normalize_selector(raw_config["source"], "demand")

    # Evaluate against network
    groups = select_nodes(network, selector, default_active_only=True)
"""

from ngraph.model.selectors import (
    VALID_OPERATORS,
    Condition,
    EntityScope,
    MatchSpec,
    NodeSelector,
    evaluate_condition,
    evaluate_conditions,
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
    link_path_key,
    match_entity_ids,
    resolve_attr_path,
    select_nodes,
)

from .normalize import normalize_selector, parse_match_spec

__all__ = [
    # Schema (re-exported from ngraph.model.selectors)
    "Condition",
    "EntityScope",
    "MatchSpec",
    "NodeSelector",
    "VALID_OPERATORS",
    # Parsing
    "normalize_selector",
    "parse_match_spec",
    # Evaluation (re-exported from ngraph.model.selectors)
    "select_nodes",
    "evaluate_condition",
    "evaluate_conditions",
    "resolve_attr_path",
    # Attribute flattening (re-exported from ngraph.model.selectors)
    "flatten_node_attrs",
    "flatten_link_attrs",
    "flatten_risk_group_attrs",
    "link_path_key",
    # Entity matching (re-exported from ngraph.model.selectors)
    "match_entity_ids",
]
