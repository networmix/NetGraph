"""Bracket expansion for name patterns.

`expand_name_patterns()` turns bracket expressions like "fa[1-3]" into
["fa1", "fa2", "fa3"].
"""

from __future__ import annotations

import re
from itertools import product
from typing import List, Set, Tuple, Union

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
        ['fa1', 'fa2', 'fa3']
        >>> expand_name_patterns("dc[1,3,5-6]")
        ['dc1', 'dc3', 'dc5', 'dc6']
        >>> expand_name_patterns("fa[1-2]_plane[5-6]")
        ['fa1_plane5', 'fa1_plane6', 'fa2_plane5', 'fa2_plane6']
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


def expand_risk_group_refs(
    rg_list: Union[List[str], Set[str], Tuple[str, ...]],
) -> Set[str]:
    """Expand bracket patterns in a list of risk group references.

    Takes a list, set, or tuple of risk group names (possibly containing
    bracket expressions) and returns a set of all expanded names.

    Args:
        rg_list: List, set, or tuple of risk group name patterns. Other
            iterables (including bare strings and generators) are rejected.

    Returns:
        Set of expanded risk group names.

    Raises:
        ValueError: If the container is not a list/set/tuple (a bare string
            would silently expand per character), or if an entry is not a
            string (e.g. a variable expansion substituted a non-string value).

    Examples:
        >>> sorted(expand_risk_group_refs(["RG1"]))
        ['RG1']
        >>> sorted(expand_risk_group_refs(["RG[1-3]"]))
        ['RG1', 'RG2', 'RG3']
        >>> sorted(expand_risk_group_refs(["A[1-2]", "B[a,b]"]))
        ['A1', 'A2', 'Ba', 'Bb']
    """
    if isinstance(rg_list, str) or not isinstance(rg_list, (list, set, tuple)):
        raise ValueError(
            "'risk_groups' must be a list or set of names, "
            f"got {type(rg_list).__name__}: {rg_list!r}"
        )
    result: Set[str] = set()
    for rg in rg_list:
        if not isinstance(rg, str):
            raise ValueError(
                f"Risk group reference must be a string, got {type(rg).__name__}: {rg!r}"
            )
        result.update(expand_name_patterns(rg))
    return result


def _parse_range_expr(expr: str) -> List[str]:
    """Parse a bracket range expression like '1-3' or 'a,b,1-2'.

    Supports:
    - Numeric ranges: 1-3 expands to 1, 2, 3
    - Literal lists: a,b,c expands to a, b, c
    - Mixed: 1,3,5-7 expands to 1, 3, 5, 6, 7

    Args:
        expr: The content inside brackets (without the brackets).

    Returns:
        List of expanded string values.

    Raises:
        ValueError: If a range uses non-numeric values or is inverted (start > end).
    """
    values: List[str] = []
    parts = [x.strip() for x in expr.split(",")]
    for part in parts:
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            # Validate that both endpoints are numeric
            try:
                start = int(start_str)
            except ValueError:
                raise ValueError(
                    f"Invalid range '{part}': start value '{start_str}' is not numeric. "
                    f"Ranges only support integers (e.g., [1-3]). "
                    f"For alphabetic values, use comma-separated lists (e.g., [a,b,c])."
                ) from None
            try:
                end = int(end_str)
            except ValueError:
                raise ValueError(
                    f"Invalid range '{part}': end value '{end_str}' is not numeric. "
                    f"Ranges only support integers (e.g., [1-3]). "
                    f"For alphabetic values, use comma-separated lists (e.g., [a,b,c])."
                ) from None
            # Validate that range is not inverted
            if start > end:
                raise ValueError(
                    f"Invalid range '{part}': start ({start}) is greater than end ({end}). "
                    f"Ranges must be ascending (e.g., [1-3], not [3-1])."
                )
            for val in range(start, end + 1):
                values.append(str(val))
        else:
            values.append(part)
    return values
