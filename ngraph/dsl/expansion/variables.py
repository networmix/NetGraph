"""Variable expansion for templates.

Provides substitution of $var and ${var} placeholders in strings,
with recursive substitution in nested structures.
"""

from __future__ import annotations

import copy
import re
from itertools import product
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

if TYPE_CHECKING:
    from .schema import ExpansionSpec

__all__ = [
    "expand_templates",
    "substitute_vars",
    "expand_block",
]

# Pattern to match $var or ${var} placeholders
_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)")

# Expansion limits
MAX_TEMPLATE_EXPANSIONS = 10_000


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
        if var_name not in var_dict:
            raise KeyError(f"Variable '${var_name}' not found in expand.vars")
        return str(var_dict[var_name])

    return _VAR_PATTERN.sub(replace, template)


def substitute_vars(obj: Any, var_dict: Dict[str, Any]) -> Any:
    """Recursively substitute ${var} in all strings within obj.

    Args:
        obj: Any value (string, dict, list, or primitive).
        var_dict: Mapping of variable names to values.

    Returns:
        Object with all string values having variables substituted.
    """
    if isinstance(obj, str):
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
    variable combination.

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
        # Remove the expand block from the result
        expanded.pop("expand", None)
        yield substitute_vars(expanded, var_dict)


def expand_templates(
    templates: Dict[str, str],
    spec: "ExpansionSpec",
) -> Iterator[Dict[str, str]]:
    """Expand template strings with variable substitution.

    Uses $var or ${var} syntax only.

    Args:
        templates: Dict of template strings.
        spec: Expansion specification with variables and mode.

    Yields:
        Dicts with same keys as templates, values substituted.

    Raises:
        ValueError: If zip mode has mismatched list lengths or expansion exceeds limit.
        KeyError: If a template references an undefined variable.
    """
    if spec.is_empty():
        yield templates
        return

    for var_dict in _generate_combinations(spec.vars, spec.mode):
        yield {k: _substitute_string(v, var_dict) for k, v in templates.items()}
