"""Validation of domain input values and their immutable JSON form."""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import Enum
from numbers import Real
from typing import Any, NoReturn, TypeAlias, cast

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)

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


def physical(value: object, label: str, *, positive: bool = False) -> float:
    """Promote a finite nonnegative physical input to binary64."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label}: expected a finite real number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label}: physical value is outside binary64 range") from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(
            f"{label}: expected a finite {'positive' if positive else 'nonnegative'} amount"
        )
    return number


def integer(
    value: object, label: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    """Validate exact integer domain inputs without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label}: expected an integer")
    if value < minimum or (maximum is not None and value >= maximum):
        raise ValueError(f"{label}: integer outside [{minimum}, {maximum})")
    return value


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
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return str.__str__(value)
        if isinstance(value, int):
            return int.__int__(value)
        if isinstance(value, float):
            return float.__float__(value)
    except MemoryError:
        raise
    except Exception as exc:
        raise ValueError(
            f"{label}: cannot normalize scalar {_type_name(value)}"
        ) from exc
    return value


def scalar(value: Any, label: str) -> Any:
    """Store a scalar field as its exact built-in value; refuse other scalar types.

    None, bool, int, float, str and Enum members are kept; a subclass of str,
    int or float becomes its stored built-in value; anything else (a NumPy
    scalar, for example) is refused with the field's label.
    """
    if (
        value is None
        or type(value) in (bool, int, float, str)
        or isinstance(value, Enum)
    ):
        return value
    if isinstance(value, (str, int, float)):
        return _plain(value, label)
    raise ValueError(f"{label}: expected a built-in scalar, got {_type_name(value)}")


def own_scalars(record: object, label: str, names: tuple[str, ...]) -> None:
    """Normalize the named scalar fields of a record during its construction."""
    for name in names:
        value = getattr(record, name)
        plain = scalar(value, f"{label}.{name}")
        if plain is not value:
            object.__setattr__(record, name, plain)


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
    if isinstance(value, (bool, str, int, float)):
        try:
            plain = _plain(value, label)
        except ValueError as exc:
            raise ValueError(
                f"{label}: expected finite JSON data, got {_type_name(value)}"
            ) from exc
        if not isinstance(plain, float) or math.isfinite(plain):
            return plain
    elif isinstance(value, list):
        items = [
            frozen_json(item, f"{label}[{i}]", strict_objects=strict_objects)
            for i, item in enumerate(value)
        ]
        if type(value) is _FrozenList and all(
            new is old for new, old in zip(items, value, strict=True)
        ):
            return value
        return _frozen_list(items)
    elif isinstance(value, Mapping):
        if strict_objects and not isinstance(value, dict):
            raise ValueError(f"{label}: JSON objects must be dict values")
        result, same = {}, type(value) is _FrozenDict
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label}: JSON object keys must be strings")
            plain = _plain(key, label)
            result[plain] = frozen_json(
                item, f"{label}.{plain}", strict_objects=strict_objects
            )
            same = same and plain is key and result[plain] is item
        return cast(dict, value) if same else frozen_dict(result)
    raise ValueError(f"{label}: expected finite JSON data, got {_type_name(value)}")


def frozen_attrs(value: object, label: str = "attrs") -> dict[str, JSONValue]:
    """Validate an attribute mapping once and return its read-only JSON form."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}: expected a mapping")
    result = frozen_json(value, label)
    assert isinstance(result, dict)
    return result


def json_copy(
    value: object, label: str = "attrs", *, strict_objects: bool = False
) -> JSONValue:
    """Validate finite JSON data and return an editable plain copy."""
    if value is None:
        return None
    if isinstance(value, (bool, str, int, float)):
        return frozen_json(value, label)
    if isinstance(value, list):
        return [
            json_copy(item, f"{label}[{i}]", strict_objects=strict_objects)
            for i, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if strict_objects and not isinstance(value, dict):
            raise ValueError(f"{label}: JSON objects must be dict values")
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label}: JSON object keys must be strings")
            key = _plain(key, label)
            result[key] = json_copy(
                item, f"{label}.{key}", strict_objects=strict_objects
            )
        return result
    raise ValueError(f"{label}: expected finite JSON data, got {_type_name(value)}")
