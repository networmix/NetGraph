"""Validation of domain input values and their immutable JSON form."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from fractions import Fraction
from numbers import Integral, Real
from typing import Any, NoReturn, TypeAlias, cast

import numpy as np

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)
"""JSON data: null, a boolean, a number, a string, or lists and string-keyed mappings
of these.
"""

_READ_ONLY = (
    "read-only: records are immutable; edit through Network methods or "
    "dataclasses.replace, then prepare again"
)


def _refuse(*args: object, **kwargs: object) -> NoReturn:
    raise TypeError(_READ_ONLY)


class _FrozenDict(dict):
    """A dict whose contents cannot change; it compares and encodes as a dict."""

    __slots__ = ()

    __init__ = __setitem__ = __delitem__ = clear = pop = popitem = setdefault = (
        update
    ) = __ior__ = _refuse

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        return frozen_dict, (dict(self),)


class _FrozenList(list):
    """A list whose contents cannot change; it compares and encodes as a list."""

    __slots__ = ()

    __init__ = __setitem__ = __delitem__ = append = clear = extend = insert = pop = (
        remove
    ) = reverse = sort = __iadd__ = __imul__ = _refuse

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        return _frozen_list, (list(self),)


def shared_copy(self, memo=None):
    """Copies of an immutable record share it, with the native values it holds."""
    return self


def frozen_dict(items: Mapping[Any, Any] = {}) -> dict:
    """Return a read-only dict holding the given references."""
    result = dict.__new__(_FrozenDict)
    dict.update(result, items)
    return result


def owned_dict(items: Mapping[Any, Any], label: str) -> dict:
    """Return a read-only dict of the given references under plain built-in keys."""
    return frozen_dict(
        {
            key if type(key) is str else _plain(key, label): value
            for key, value in items.items()
        }
    )


def _frozen_list(items: list) -> list:
    result = list.__new__(_FrozenList)
    list.extend(result, items)
    return result


# One rule per kind of input field, shared by every constructor and the YAML loader:
# a field accepts its built-in type or the NumPy scalar of the same kind, stored as
# the built-in value; integers also accept exactly integral floats; booleans are
# never numbers. Each refusal names the field and the value.


def _bounded(text: str, limit: int = 220) -> str:
    plain = str.__str__(text)
    return plain if len(plain) <= limit else plain[: limit - 3] + "..."


def _shown(value: object) -> str:
    """Render an input without letting its representation replace a refusal."""
    try:
        rendered = repr(value)
    except Exception:
        try:
            rendered = _safe_repr(value)
        except Exception:
            rendered = f"<unprintable {type(value).__name__}>"
    return rendered if len(rendered) <= 60 else rendered[:57] + "..."


def _safe_repr(value, seen=None):
    try:
        return repr(value)
    except Exception:
        pass
    if isinstance(value, int):
        number = abs(int.__int__(value))
        digits = max(1, (number.bit_length() - 1) * 1233 // 4096 + 1)
        while number >= 10**digits:
            digits += 1
        while digits > 1 and number < 10 ** (digits - 1):
            digits -= 1
        return f"an integer of {digits} digits"
    seen = set() if seen is None else seen
    if id(value) in seen:
        return "..."
    seen.add(id(value))
    try:
        if isinstance(value, dict):
            return (
                "{"
                + ", ".join(
                    f"{_safe_repr(k, seen)}: {_safe_repr(v, seen)}"
                    for k, v in value.items()
                )
                + "}"
            )
        if isinstance(value, (list, tuple)):
            left, right = ("[", "]") if isinstance(value, list) else ("(", ")")
            return left + ", ".join(_safe_repr(v, seen) for v in value) + right
        try:
            return repr(value)
        except Exception:
            return f"<unprintable {type(value).__name__}>"
    finally:
        seen.remove(id(value))


class _DiagnosticInteger(int):
    def __repr__(self):
        return _safe_repr(int.__int__(self))


def _diagnostic_value(value):
    """A schema-only view when its own diagnostic cannot print a supplied int.

    The original parsed values are returned to callers. This fallback is used
    only after jsonschema's error rendering fails, preserving its constraints,
    selected field path and ValidationError cause.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            repr(value)
        except ValueError:
            return _DiagnosticInteger(value)
        return value
    if isinstance(value, dict):
        return {k: _diagnostic_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_diagnostic_value(v) for v in value]
    return value


def _is_flag(value: object) -> bool:
    return isinstance(value, (bool, np.bool_))


def _located_error(error, label, value, *, field=None, reason=None):
    """Carry diagnostic field/value context without reading the rendered message."""
    error.__dict__["_input_label"] = label
    error.__dict__["_input_value"] = value
    message = str(error)
    error.__dict__["_input_reason"] = (
        reason
        if reason is not None
        else message[len(label) + 2 :]
        if message.startswith(label + ": ")
        else message
    )
    if field is not None:
        error.__dict__["_workflow_field"] = field
    return error


def _input_error(label: str, detail: str, *, value=None) -> ValueError:
    """A refusal with a field-relative path, independent of its readable label."""
    error = _located_error(ValueError(f"{label}: {detail}"), label, value)
    error.__dict__["_input_path"] = ()
    error.__dict__["_input_detail"] = detail
    return error


def text(value: object, label: str, *, empty: bool = False) -> str:
    """A text field: a str (a subclass such as numpy.str_ is stored as str).

    A name is nonempty; whitespace is part of a name, as in every other text.
    """
    if not isinstance(value, str):
        raise _input_error(label, f"expected text, got {_shown(value)}", value=value)
    plain = str.__str__(value)
    if not plain and not empty:
        raise _input_error(label, "expected a nonempty name, got ''", value=value)
    return plain


def optional_text(value: object, label: str, *, empty: bool = False) -> str | None:
    """A text field that may be None."""
    return None if value is None else text(value, label, empty=empty)


def pattern(value: object, label: str, *, empty: bool = False) -> str:
    """A regular-expression field: text that compiles."""
    plain = text(value, label, empty=empty)
    try:
        re.compile(plain)
    except re.error as exc:
        raise _located_error(
            ValueError(f"{label}: invalid pattern {_shown(plain)}: {exc}"), label, value
        ) from exc
    return plain


def optional_pattern(value: object, label: str, *, empty: bool = False) -> str | None:
    """A regular-expression field that may be None."""
    return None if value is None else pattern(value, label, empty=empty)


def flag(value: object, label: str) -> bool:
    """A boolean field: a bool or a NumPy boolean, stored as bool."""
    if not _is_flag(value):
        raise _input_error(label, f"expected bool, got {_shown(value)}", value=value)
    return bool(value)


def optional_flag(value: object, label: str) -> bool | None:
    """A boolean field that may be None."""
    return None if value is None else flag(value, label)


def physical(value: object, label: str, *, positive: bool = False) -> float:
    """Promote a finite nonnegative real input (an amount or a ratio) to binary64."""
    if _is_flag(value) or not isinstance(value, Real):
        raise _located_error(
            ValueError(f"{label}: expected a finite real number, got {_shown(value)}"),
            label,
            value,
        )
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise _located_error(
            ValueError(
                f"{label}: physical value is outside binary64 range, got {_shown(value)}"
            ),
            label,
            value,
        ) from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise _located_error(
            ValueError(
                f"{label}: expected a finite {'positive' if positive else 'nonnegative'} "
                f"amount, got {_shown(value)}"
            ),
            label,
            value,
        )
    return number


def integer(
    value: object, label: str, *, minimum: int | None = 0, maximum: int | None = None
) -> int:
    """An integer field: an int, a NumPy integer or an exactly integral float.

    Booleans and fractions are refused; the value is stored as int.
    """
    if _is_flag(value):
        raise _input_error(
            label, f"expected an integer, got {_shown(value)}", value=value
        )
    # A subclass of int or float is read as its stored value, not its conversions.
    if isinstance(value, int):
        number = int.__int__(value)
    elif isinstance(value, Integral):
        number = int(value)
    elif isinstance(value, float) and float.__float__(value).is_integer():
        number = int(float.__float__(value))
    elif isinstance(value, np.floating) and float(value).is_integer():
        number = int(float(value))
    else:
        raise _input_error(
            label, f"expected an integer, got {_shown(value)}", value=value
        )
    if (minimum is not None and number < minimum) or (
        maximum is not None and number >= maximum
    ):
        raise _input_error(
            label,
            f"integer outside [{_bound(minimum)}, {_bound(maximum)}), "
            f"got {_shown(value)}",
            value=value,
        )
    return number


def _bound(n: int | None) -> str:
    """A range bound as written in the docs: large powers of two as 2^k, none as inf."""
    if n is None:
        return "inf"
    if n >= 1 << 20 and n & (n - 1) == 0:
        return f"2^{n.bit_length() - 1}"
    return str(n)


def optional_integer(
    value: object, label: str, *, minimum: int | None = 0, maximum: int | None = None
) -> int | None:
    """An integer field that may be None."""
    if value is None:
        return None
    return integer(value, label, minimum=minimum, maximum=maximum)


def collection(value, label: str) -> tuple:
    """Own an iterable collection, refusing scalars with its field and raw value."""
    if isinstance(value, (str, bytes, Mapping)):
        raise _located_error(
            TypeError(f"{label}: expected a collection, got {_shown(value)}"),
            label,
            value,
        )
    try:
        return tuple(value)
    except TypeError as exc:
        raise _located_error(
            TypeError(f"{label}: expected a collection, got {_shown(value)}"),
            label,
            value,
        ) from exc


def own(record: object, **values: object) -> None:
    """Store checked field values on a frozen record during its construction."""
    for name, value in values.items():
        if getattr(record, name) is not value:
            object.__setattr__(record, name, value)


def exact_fraction(value: object, label: str) -> Fraction:
    """An exact ratio from an integer, a ``p/q`` or decimal string, or a Fraction.

    Floats and booleans are refused: a binary64 value is not the exact ratio
    the declaration means. NumPy integers and strings count as their kind.
    """
    if _is_flag(value) or not isinstance(value, (Integral, str, Fraction)):
        raise _located_error(
            ValueError(
                f"{label}: expected exact integer or fraction string, got {_shown(value)}"
            ),
            label,
            value,
        )
    try:
        return Fraction(value if isinstance(value, Fraction) else _exact(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise _located_error(
            ValueError(f"{label}: invalid exact fraction, got {_shown(value)}"),
            label,
            value,
        ) from exc


def _exact(value: Integral | str) -> int | str:
    return str.__str__(value) if isinstance(value, str) else int(value)


def _type_name(value: object) -> str:
    kind = type(value)
    return (
        kind.__name__
        if kind.__module__ == "builtins"
        else f"{kind.__module__}.{kind.__name__}"
    )


def _plain(value, label):
    """Return the stored built-in value of a str, int or float subclass."""
    try:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, str):
            return str.__str__(value)
        if isinstance(value, int):
            return int.__int__(value)
        if isinstance(value, float):
            return float.__float__(value)
    except MemoryError:
        raise
    except Exception as exc:
        raise _input_error(
            label, f"cannot normalize scalar {_type_name(value)}", value=value
        ) from exc
    return value


def frozen_json(
    value: object, label: str = "attrs", *, strict_objects: bool = False
) -> JSONValue:
    """Validate finite JSON data and return it in read-only form.

    Accepted scalar subclasses become their plain built-in values and mapping
    keys become plain strings. Mappings (only dicts with ``strict_objects``)
    become read-only dicts and lists become read-only lists. A read-only
    container is checked like any other, since record collections share its
    type, and is shared when its contents are already in that form.
    """
    if value is None:
        return value
    if isinstance(value, (bool, str, int)) and type(value) in (bool, str, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, (bool, str, int, float, np.bool_, np.integer, np.floating)):
        try:
            plain = _plain(value, label)
        except ValueError as exc:
            raise _input_error(
                label,
                f"expected finite JSON data, got {_type_name(value)}",
                value=value,
            ) from exc
        if not isinstance(plain, float) or math.isfinite(plain):
            return plain
    elif isinstance(value, list):
        items = [
            _json_child(item, f"{label}[{i}]", i, strict_objects)
            for i, item in enumerate(value)
        ]
        if type(value) is _FrozenList and all(
            new is old for new, old in zip(items, value, strict=True)
        ):
            return value
        return _frozen_list(items)
    elif isinstance(value, Mapping):
        if strict_objects and not isinstance(value, dict):
            raise _input_error(
                label,
                f"JSON objects must be dict values, got {_shown(value)}",
                value=value,
            )
        result, same = {}, type(value) is _FrozenDict
        for key, item in value.items():
            if not isinstance(key, str):
                raise _input_error(
                    label,
                    f"JSON object keys must be strings, got {_shown(key)}",
                    value=value,
                )
            plain = _plain(key, label)
            result[plain] = _json_child(item, f"{label}.{plain}", plain, strict_objects)
            same = same and plain is key and result[plain] is item
        return cast(dict, value) if same else frozen_dict(result)
    raise _input_error(
        label,
        f"expected finite JSON data, got {_type_name(value)} = {_shown(value)}",
        value=value,
    )


def _json_child(value, label, part, strict_objects):
    """Keep a JSON key or sequence position intact when a child is refused."""
    try:
        return frozen_json(value, label, strict_objects=strict_objects)
    except ValueError as exc:
        exc.__dict__["_input_path"] = (part, *getattr(exc, "_input_path", ()))
        raise


def frozen_attrs(value: object, label: str = "attrs") -> dict[str, JSONValue]:
    """Validate an attribute mapping once and return its read-only JSON form."""
    if not isinstance(value, Mapping):
        raise _input_error(
            label, f"expected a mapping, got {_shown(value)}", value=value
        )
    result = frozen_json(value, label)
    assert isinstance(result, dict)
    return result


def json_copy(
    value: object, label: str = "attrs", *, strict_objects: bool = False
) -> JSONValue:
    """Validate finite JSON data and return an editable plain copy."""
    if value is None:
        return None
    if isinstance(value, (bool, str, int, float, np.bool_, np.integer, np.floating)):
        return frozen_json(value, label)
    if isinstance(value, list):
        return [
            json_copy(item, f"{label}[{i}]", strict_objects=strict_objects)
            for i, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if strict_objects and not isinstance(value, dict):
            raise ValueError(
                f"{label}: JSON objects must be dict values, got {_shown(value)}"
            )
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"{label}: JSON object keys must be strings, got {_shown(key)}"
                )
            key = _plain(key, label)
            result[key] = json_copy(
                item, f"{label}.{key}", strict_objects=strict_objects
            )
        return result
    raise ValueError(
        f"{label}: expected finite JSON data, got {_type_name(value)} = {_shown(value)}"
    )
