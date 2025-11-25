"""Parsing helpers for the network DSL.

This module factors out pure parsing/validation helpers from the expansion
module so they can be tested independently and reused.
"""

from __future__ import annotations

import re
from itertools import product
from typing import Any, Dict, List


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


_RANGE_REGEX = re.compile(r"\[([^\]]+)\]")


def expand_name_patterns(name: str) -> List[str]:
    """Expand bracket expressions in a group name.

    Examples:
        - "fa[1-3]" -> ["fa1", "fa2", "fa3"]
        - "dc[1,3,5-6]" -> ["dc1", "dc3", "dc5", "dc6"]
        - "fa[1-2]_plane[5-6]" -> ["fa1_plane5", "fa1_plane6", "fa2_plane5", "fa2_plane6"]
    """
    matches = list(_RANGE_REGEX.finditer(name))
    if not matches:
        return [name]

    expansions_list = []
    for match in matches:
        range_expr = match.group(1)
        expansions_list.append(_parse_range_expr(range_expr))

    expanded_names = []
    for combo in product(*expansions_list):
        result_str = ""
        last_end = 0
        for m_idx, match in enumerate(matches):
            start, end = match.span()
            result_str += name[last_end:start]
            result_str += combo[m_idx]
            last_end = end
        result_str += name[last_end:]
        expanded_names.append(result_str)

    return expanded_names


def _parse_range_expr(expr: str) -> List[str]:
    values: List[str] = []
    parts = [x.strip() for x in expr.split(",")]
    for part in parts:
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            for val in range(start, end + 1):
                values.append(str(val))
        else:
            values.append(part)
    return values


def join_paths(parent_path: str, rel_path: str) -> str:
    """Join two path segments according to the DSL conventions."""
    # Attribute directive paths are global selectors and must not be prefixed
    # by any parent blueprint path.
    if rel_path.startswith("attr:"):
        return rel_path
    if rel_path.startswith("/"):
        rel_path = rel_path[1:]
        if parent_path:
            return f"{parent_path}/{rel_path}"
        return rel_path

    if parent_path:
        return f"{parent_path}/{rel_path}"
    return rel_path
