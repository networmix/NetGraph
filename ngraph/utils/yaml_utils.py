"""Utilities for handling YAML parsing quirks and common operations."""

from typing import Any, Dict, TypeVar

V = TypeVar("V")


def normalize_yaml_dict_keys(data: Dict[Any, V]) -> Dict[str, V]:
    """Normalize dictionary keys from YAML parsing to ensure consistent string keys.

    YAML 1.1 parses true/false/yes/no/on/off keys as Python booleans. Those
    become "True"/"False"; every other key is coerced with str().

    Args:
        data: Dictionary that may contain boolean or other non-string keys from YAML parsing

    Returns:
        Dictionary with all keys converted to strings, boolean keys converted to "True"/"False"

    Examples:
        >>> normalize_yaml_dict_keys({True: "value1", False: "value2", "normal": "value3"})
        {"True": "value1", "False": "value2", "normal": "value3"}

        >>> # In YAML: true:, yes:, on: all become Python True
        >>> # In YAML: false:, no:, off: all become Python False
    """
    normalized = {}
    for key, value in data.items():
        # YAML 1.1 turns true/false/yes/no/on/off keys into Python bools;
        # normalize those to "True"/"False".
        if isinstance(key, bool):
            key = str(key)
        key = str(key)
        normalized[key] = value
    return normalized
