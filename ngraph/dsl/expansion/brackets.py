"""Bracket expansion for name patterns.

Provides expand_name_patterns() for expanding bracket expressions
like "fa[1-3]" into ["fa1", "fa2", "fa3"].
"""

from __future__ import annotations

import re
from itertools import product
from typing import Iterable, List, Set

__all__ = [
    "expand_name_patterns",
    "expand_risk_group_refs",
]

_RANGE_REGEX = re.compile(r"\[([^\]]+)\]")


def expand_name_patterns(name: str) -> List[str]:
    """Expand bracket expressions in a group name.

    Supports:
    - Ranges: [1-3] -> 1, 2, 3
    - Lists: [a,b,c] -> a, b, c
    - Mixed: [1,3,5-7] -> 1, 3, 5, 6, 7
    - Multiple brackets: Cartesian product

    Args:
        name: Name pattern with optional bracket expressions.

    Returns:
        List of expanded names.

    Examples:
        >>> expand_name_patterns("fa[1-3]")
        ["fa1", "fa2", "fa3"]
        >>> expand_name_patterns("dc[1,3,5-6]")
        ["dc1", "dc3", "dc5", "dc6"]
        >>> expand_name_patterns("fa[1-2]_plane[5-6]")
        ["fa1_plane5", "fa1_plane6", "fa2_plane5", "fa2_plane6"]
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


def expand_risk_group_refs(rg_list: Iterable[str]) -> Set[str]:
    """Expand bracket patterns in a list of risk group references.

    Takes an iterable of risk group names (possibly containing bracket
    expressions) and returns a set of all expanded names.

    Args:
        rg_list: Iterable of risk group name patterns.

    Returns:
        Set of expanded risk group names.

    Examples:
        >>> expand_risk_group_refs(["RG1"])
        {"RG1"}
        >>> expand_risk_group_refs(["RG[1-3]"])
        {"RG1", "RG2", "RG3"}
        >>> expand_risk_group_refs(["A[1-2]", "B[a,b]"])
        {"A1", "A2", "Ba", "Bb"}
    """
    result: Set[str] = set()
    for rg in rg_list:
        result.update(expand_name_patterns(rg))
    return result


def _parse_range_expr(expr: str) -> List[str]:
    """Parse a bracket range expression like '1-3' or 'a,b,1-2'."""
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
