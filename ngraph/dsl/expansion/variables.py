"""Variable expansion for templates.

Provides expand_templates() function for substituting $var and ${var}
placeholders in template strings.
"""

from __future__ import annotations

import re
from itertools import product
from typing import TYPE_CHECKING, Any, Dict, Iterator

if TYPE_CHECKING:
    from .schema import ExpansionSpec

__all__ = [
    "expand_templates",
    "substitute_vars",
]

# Pattern to match $var or ${var} placeholders
_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}|\$([a-zA-Z_][a-zA-Z0-9_]*)")

# Expansion limits
MAX_TEMPLATE_EXPANSIONS = 10_000


def substitute_vars(template: str, var_dict: Dict[str, Any]) -> str:
    """Substitute $var and ${var} placeholders in a template string.

    Uses $ prefix to avoid collision with regex {m,n} quantifiers.

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
            raise KeyError(f"Variable '${var_name}' not found in expand_vars")
        return str(var_dict[var_name])

    return _VAR_PATTERN.sub(replace, template)


def expand_templates(
    templates: Dict[str, str],
    spec: "ExpansionSpec",
) -> Iterator[Dict[str, str]]:
    """Expand template strings with variable substitution.

    Uses $var or ${var} syntax only.

    Args:
        templates: Dict of template strings, e.g. {"source": "dc${dc}/...", "sink": "..."}.
        spec: Expansion specification with variables and mode.

    Yields:
        Dicts with same keys as templates, values substituted.

    Raises:
        ValueError: If zip mode has mismatched list lengths or expansion exceeds limit.
        KeyError: If a template references an undefined variable.

    Example:
        >>> spec = ExpansionSpec(expand_vars={"dc": [1, 2]})
        >>> list(expand_templates({"src": "dc${dc}"}, spec))
        [{"src": "dc1"}, {"src": "dc2"}]
    """
    if spec.is_empty():
        yield templates
        return

    var_names = sorted(spec.expand_vars.keys())
    var_values = [spec.expand_vars[k] for k in var_names]

    if spec.expansion_mode == "zip":
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
        var_dict = dict(zip(var_names, combo, strict=True))
        yield {k: substitute_vars(v, var_dict) for k, v in templates.items()}
