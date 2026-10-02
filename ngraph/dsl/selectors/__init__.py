"""YAML-facing selector parsing for the NetGraph DSL.

`normalize_selector` turns a raw selector from a scenario (a path string or a
selector dict) into a `NodeSelector`. The schema types and the evaluation
engine (`select_nodes`, condition evaluation, attribute flattening) live in
`ngraph.model.selectors`.

Usage:
    from ngraph.dsl.selectors import normalize_selector
    from ngraph.model.selectors import select_nodes

    # From YAML config (string or dict)
    selector = normalize_selector(raw_config["source"], "demand")

    # Evaluate against network
    groups = select_nodes(network, selector, default_active_only=True)
"""

from .normalize import normalize_selector

__all__ = ["normalize_selector"]
