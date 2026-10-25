"""Helpers for YAML parsing quirks and configuration key checks."""

from typing import AbstractSet, Any, Callable, Dict, Mapping, TypeVar

V = TypeVar("V")
T = TypeVar("T")


def normalize_yaml_dict_keys(data: Mapping[Any, V]) -> Dict[str, V]:
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


def _declaration_error(where: str, message: str) -> ValueError:
    error = ValueError(message)
    # Constructor labels such as "workflow step mf" are still relative;
    # only actual YAML declaration roots stop an enclosing relabelling.
    root = where.split(".", 1)[0].split("[", 1)[0]
    if root in {
        "network",
        "blueprints",
        "components",
        "risk_groups",
        "workflow",
        "demands",
        "failures",
        "units",
        "routes",
        "supports",
        "weights",
        "routing",
        "wcmp_controller",
        "forwarding_groups",
    }:
        error.__dict__["_declaration_path"] = where
    return error


def declared(where: str, build: Callable[[], T], record: str = "") -> T:
    """Build one record from YAML; a refusal also names where it is declared.

    A refusal labelled with the record's own name (``record``, as in
    "group_child.share: ...") is relabelled with the declaration's path.
    """
    try:
        return build()
    except (ValueError, TypeError, KeyError) as exc:
        if getattr(exc, "_declaration_path", None) is not None:
            raise
        message = str(exc)
        if record and message.startswith(record):
            suffix = message[len(record) :]
            if suffix.startswith(" "):
                suffix = "." + suffix[1:]
            raise _declaration_error(where, where + suffix) from exc
        if message.startswith(where + ".") or message.startswith(where + ":"):
            raise _declaration_error(where, message) from exc
        raise _declaration_error(where, f"{where}: {message}") from exc
