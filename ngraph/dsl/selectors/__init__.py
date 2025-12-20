"""Unified node selection for NetGraph DSL.

This module provides a single abstraction for node selection used across
adjacency, demands, overrides, and workflow steps.

Usage:
    from ngraph.dsl.selectors import normalize_selector, select_nodes, NodeSelector

    # From YAML config (string or dict)
    selector = normalize_selector(raw_config["source"], "demand")

    # Evaluate against network
    groups = select_nodes(network, selector, default_active_only=True)
"""

from .conditions import evaluate_condition, evaluate_conditions
from .normalize import normalize_selector
from .schema import Condition, MatchSpec, NodeSelector
from .select import flatten_link_attrs, flatten_node_attrs, select_nodes

__all__ = [
    # Schema
    "Condition",
    "MatchSpec",
    "NodeSelector",
    # Parsing
    "normalize_selector",
    # Evaluation
    "select_nodes",
    "evaluate_condition",
    "evaluate_conditions",
    # Attribute flattening
    "flatten_node_attrs",
    "flatten_link_attrs",
]
