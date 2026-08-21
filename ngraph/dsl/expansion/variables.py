"""Variable expansion for templates.

Substitutes $var and ${var} placeholders in strings, recursing into nested
structures.
"""

from __future__ import annotations

import copy
import re
from itertools import product
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

if TYPE_CHECKING:
    from .schema import ExpansionSpec

__all__ = [
    "substitute_vars",
    "expand_block",
]

# Pattern to match $var or ${var} placeholders
_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)")

# Expansion limits
MAX_TEMPLATE_EXPANSIONS = 10_000


def _lookup_var(var_name: str, var_dict: Dict[str, Any]) -> Any:
    """Return the value bound to var_name, raising the standard KeyError."""
    if var_name not in var_dict:
        raise KeyError(f"Variable '${var_name}' not found in expand.vars")
    return var_dict[var_name]


def _substitute_string(template: str, var_dict: Dict[str, Any]) -> str:
    """Substitute $var and ${var} placeholders in a template string.

    Args:
        template: String containing $var or ${var} placeholders.
        var_dict: Mapping of variable names to values.

    Returns:
        Template with variables substituted.

    Raises:
        KeyError: If a referenced variable is not in var_dict.
    """

    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1) or match.group(2)
        return str(_lookup_var(var_name, var_dict))

    return _VAR_PATTERN.sub(replace, template)


def substitute_vars(obj: Any, var_dict: Dict[str, Any]) -> Any:
    """Recursively substitute ${var} in all strings within obj.

    A string consisting of exactly one placeholder (e.g. "${t}") is replaced
    by the variable's native value, preserving its type. This keeps match
    condition values comparable to non-string attributes (e.g. int tiers).
    Placeholders embedded in longer strings (e.g. "dc${dc}_internal") are
    interpolated as text, so the result is a string.

    Args:
        obj: Any value (string, dict, list, or primitive).
        var_dict: Mapping of variable names to values.

    Returns:
        Object with variables substituted: whole-placeholder strings replaced
        by the variable's native value, other strings interpolated as text.

    Raises:
        KeyError: If a placeholder names a variable absent from var_dict.
    """
    if isinstance(obj, str):
        whole = _VAR_PATTERN.fullmatch(obj)
        if whole:
            return _lookup_var(whole.group(1) or whole.group(2), var_dict)
        return _substitute_string(obj, var_dict)
    if isinstance(obj, dict):
        return {k: substitute_vars(v, var_dict) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_vars(item, var_dict) for item in obj]
    return obj


def _generate_combinations(
    vars_dict: Dict[str, List[Any]],
    mode: str,
) -> Iterator[Dict[str, Any]]:
    """Generate variable value combinations.

    Args:
        vars_dict: Mapping of variable names to value lists.
        mode: "cartesian" or "zip".

    Yields:
        Dict mapping variable names to values for each combination.
    """
    if not vars_dict:
        return

    var_names = sorted(vars_dict.keys())
    var_values = [vars_dict[k] for k in var_names]

    if mode == "zip":
        lengths = [len(v) for v in var_values]
        if len(set(lengths)) != 1:
            raise ValueError(
                f"zip expansion requires equal-length lists; got lengths {lengths}"
            )
        combos: Iterator[tuple[Any, ...]] = zip(*var_values, strict=True)
        expansion_size = lengths[0] if lengths else 0
    else:
        # Cartesian product
        expansion_size = 1
        for v in var_values:
            expansion_size *= len(v)
        combos = product(*var_values)

    if expansion_size > MAX_TEMPLATE_EXPANSIONS:
        raise ValueError(
            f"Template expansion would create {expansion_size} items "
            f"(limit: {MAX_TEMPLATE_EXPANSIONS}). "
            f"Consider using fewer variables or splitting into multiple entries."
        )

    for combo in combos:
        yield dict(zip(var_names, combo, strict=True))


def expand_block(
    block: Dict[str, Any],
    spec: Optional["ExpansionSpec"],
) -> Iterator[Dict[str, Any]]:
    """Expand a DSL block, yielding one dict per variable combination.

    If no expand spec is provided or it has no vars, yields the original block.
    Otherwise, yields a deep copy with all strings substituted for each
    variable combination; the 'expand' key itself is removed from each copy.

    Args:
        block: DSL block (dict) that may contain template strings.
        spec: Optional expansion specification.

    Yields:
        Dict with variable substitutions applied.
    """
    if spec is None or spec.is_empty():
        yield block
        return

    for var_dict in _generate_combinations(spec.vars, spec.mode):
        expanded = copy.deepcopy(block)
        expanded.pop("expand", None)
        yield substitute_vars(expanded, var_dict)
