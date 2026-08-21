"""Runtime selector engine for the network model.

Schema types and the evaluation engine for node, link, and risk-group
selection over `Network` objects. It lives in the model layer so that failure
policies and analysis code can evaluate selectors without depending on the DSL
package.

YAML-facing selector parsing (`normalize_selector`) lives in
`ngraph.dsl.selectors`, which builds the schema types defined here
(dsl -> model direction only). `parse_match_spec` lives here because it
builds model types from plain dicts and is used by model-layer parsers.

Usage:
    from ngraph.model.selectors import NodeSelector, select_nodes

    selector = NodeSelector(path="^dc1/.*")
    groups = select_nodes(network, selector, default_active_only=True)
"""

from .conditions import evaluate_condition, evaluate_conditions, resolve_attr_path
from .parse import parse_match_spec
from .schema import VALID_OPERATORS, Condition, EntityScope, MatchSpec, NodeSelector
from .select import (
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
    link_path_key,
    match_entity_ids,
    select_nodes,
)

__all__ = [
    # Schema
    "Condition",
    "EntityScope",
    "MatchSpec",
    "NodeSelector",
    "VALID_OPERATORS",
    # Parsing
    "parse_match_spec",
    # Evaluation
    "select_nodes",
    "evaluate_condition",
    "evaluate_conditions",
    "resolve_attr_path",
    # Attribute flattening
    "flatten_node_attrs",
    "flatten_link_attrs",
    "flatten_risk_group_attrs",
    "link_path_key",
    # Entity matching
    "match_entity_ids",
]
