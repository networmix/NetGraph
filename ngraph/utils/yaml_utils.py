"""Helpers for YAML parsing quirks and configuration key checks."""

from typing import AbstractSet, Any, Dict, Mapping, TypeVar

V = TypeVar("V")


def normalize_yaml_dict_keys(data: Dict[Any, V]) -> Dict[str, V]:
    """Convert YAML-parsed dictionary keys to strings.

    YAML 1.1 parses true/false/yes/no/on/off keys as Python booleans. Those
    become "True"/"False"; every other key is coerced with str().

    Args:
        data: Dictionary that may contain boolean or other non-string keys from YAML parsing

    Returns:
        New dictionary with str() keys.

    Examples:
        >>> normalize_yaml_dict_keys({True: "value1", False: "value2", "normal": "value3"})
        {"True": "value1", "False": "value2", "normal": "value3"}

        >>> # In YAML: true:, yes:, on: all become Python True
        >>> # In YAML: false:, no:, off: all become Python False
    """
    return {str(key): value for key, value in data.items()}


def check_no_extra_keys(
    data: Mapping[Any, Any], allowed: AbstractSet[str], context: str
) -> None:
    """Raise if ``data`` has keys outside ``allowed``; they would be ignored.

    Args:
        data: Mapping parsed from configuration.
        allowed: Recognized keys.
        context: Short description of ``data`` used in the error message.

    Raises:
        ValueError: If ``data`` contains any key not in ``allowed``.
    """
    extra = sorted(str(k) for k in data if k not in allowed)
    if extra:
        raise ValueError(
            f"Unrecognized key(s) in {context}: {', '.join(extra)}. "
            f"Allowed keys are: {sorted(allowed)}"
        )
