"""Parsing helpers for the network DSL.

Pure parsing/validation helpers, kept separate from the expansion module so
they can be tested independently and reused.
"""

from __future__ import annotations

from typing import Any, Dict

from ngraph.utils.yaml_utils import check_no_extra_keys

__all__ = [
    "check_link_keys",
    "join_paths",
]


def check_link_keys(link_def: Dict[str, Any], context: str) -> None:
    """Reject unrecognized link keys and require 'source' and 'target'."""
    check_no_extra_keys(
        link_def,
        allowed={
            "source",
            "target",
            "pattern",
            "count",
            "expand",
            "capacity",
            "cost",
            "disabled",
            "risk_groups",
            "attrs",
        },
        context=context,
    )
    if "source" not in link_def or "target" not in link_def:
        raise ValueError(f"Link in {context} must have 'source' and 'target'.")


def join_paths(parent_path: str, rel_path: str) -> str:
    """Join two path segments according to DSL conventions.

    The DSL has no absolute paths. All paths are relative to the current
    context (parent_path). A leading "/" on rel_path is stripped and has no
    functional effect; it only marks that the path starts from the current
    scope's root.

    Examples:
        join_paths("", "/leaf") -> "leaf"
        join_paths("pod1", "/leaf") -> "pod1/leaf"
        join_paths("pod1", "leaf") -> "pod1/leaf"  (same result)

    Args:
        parent_path: Parent path prefix (e.g., "pod1" when expanding a blueprint).
        rel_path: Path to join. Leading "/" is stripped if present.

    Returns:
        "{parent_path}/{rel_path}", or rel_path alone when parent_path is empty.
    """
    rel_path = rel_path.removeprefix("/")
    return f"{parent_path}/{rel_path}" if parent_path else rel_path
