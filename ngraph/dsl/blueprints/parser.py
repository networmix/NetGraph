"""Parsing helpers for the network DSL.

This module factors out pure parsing/validation helpers from the expansion
module so they can be tested independently and reused.
"""

from __future__ import annotations

from typing import Any, Dict

# Re-export expand_name_patterns from its canonical location
from ngraph.dsl.expansion import expand_name_patterns

__all__ = [
    "check_no_extra_keys",
    "check_adjacency_keys",
    "check_link_params",
    "expand_name_patterns",
    "join_paths",
]


def check_no_extra_keys(
    data_dict: Dict[str, Any], allowed: set[str], context: str
) -> None:
    """Raise if ``data_dict`` contains keys outside ``allowed``.

    Args:
        data_dict: The dict to check.
        allowed: Set of recognized keys.
        context: Short description used in error messages.
    """
    extra_keys = set(data_dict.keys()) - allowed
    if extra_keys:
        raise ValueError(
            f"Unrecognized key(s) in {context}: {', '.join(sorted(extra_keys))}. "
            f"Allowed keys are: {sorted(allowed)}"
        )


def check_adjacency_keys(adj_def: Dict[str, Any], context: str) -> None:
    """Ensure adjacency definitions only contain recognized keys."""
    check_no_extra_keys(
        adj_def,
        allowed={
            "source",
            "target",
            "pattern",
            "link_count",
            "link_params",
            "expand_vars",
            "expansion_mode",
        },
        context=context,
    )
    if "source" not in adj_def or "target" not in adj_def:
        raise ValueError(f"Adjacency in {context} must have 'source' and 'target'.")


def check_link_params(link_params: Dict[str, Any], context: str) -> None:
    """Ensure link_params contain only recognized keys.

    Link attributes may include "hardware" per-end mapping when set under
    link_params.attrs. This function only validates top-level link_params keys.
    """
    recognized = {"capacity", "cost", "disabled", "risk_groups", "attrs"}
    extra = set(link_params.keys()) - recognized
    if extra:
        raise ValueError(
            f"Unrecognized link_params key(s) in {context}: {', '.join(sorted(extra))}. "
            f"Allowed: {sorted(recognized)}"
        )


def join_paths(parent_path: str, rel_path: str) -> str:
    """Join two path segments according to DSL conventions.

    The DSL has no concept of absolute paths. All paths are relative to the
    current context (parent_path). A leading "/" on rel_path is stripped and
    has no functional effect - it serves only as a visual indicator that the
    path starts from the current scope's root.

    Behavior:
    - Leading "/" on rel_path is stripped (not treated as filesystem root)
    - Result is always: "{parent_path}/{stripped_rel_path}" if parent_path is non-empty
    - Examples:
        join_paths("", "/leaf") -> "leaf"
        join_paths("pod1", "/leaf") -> "pod1/leaf"
        join_paths("pod1", "leaf") -> "pod1/leaf"  (same result)

    Args:
        parent_path: Parent path prefix (e.g., "pod1" when expanding a blueprint).
        rel_path: Path to join. Leading "/" is stripped if present.

    Returns:
        Combined path string.
    """
    if rel_path.startswith("/"):
        rel_path = rel_path[1:]
        if parent_path:
            return f"{parent_path}/{rel_path}"
        return rel_path

    if parent_path:
        return f"{parent_path}/{rel_path}"
    return rel_path
