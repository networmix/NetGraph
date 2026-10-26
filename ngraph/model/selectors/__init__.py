"""Runtime selector engine for the network model.

Schema types and the evaluation engine for node, link, and risk-group
selection over `Network` objects. It lives in the model layer so that failure
policies and analysis code can evaluate selectors without depending on the DSL
package.

YAML-facing selector normalization and match parsing live here, alongside the
schema types they construct. DSL callers construct these typed values once.

Usage:
    >>> from ngraph import Network, Node
    >>> from ngraph.model.selectors import Selector, select_nodes
    >>> network = Network()
    >>> network.add_node(Node("dc1/leaf1"))
    >>> selector = Selector(path="^dc1/.*")
    >>> groups = select_nodes(network, selector, default_active_only=True)
    >>> assert [node.name for node in groups["^dc1/.*"]] == ["dc1/leaf1"]
"""

from .conditions import evaluate_condition, evaluate_conditions, resolve_attr_path
from .parse import normalize_selector, parse_match_spec
from .schema import VALID_OPERATORS, Condition, EntityScope, MatchSpec, Selector
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
    "Selector",
    "VALID_OPERATORS",
    # Parsing
    "normalize_selector",
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
