"""Generate the results JSON Schema from the record declarations.

A plain record (one the exporter writes as its declared class constants and
fields) gets its definition from its type annotations; an ``Annotated``
mapping on a field adds JSON Schema keywords. Type aliases of records or
literals become ``anyOf`` or ``enum`` definitions. Every other definition
(native results, rows, cases, envelopes, questions) is the explicit fragment
in ``dev/explicit_results_schema.json``, matching the exporter's explicit code.

Usage: python dev/generate_results_schema.py [--check]
Without ``--check`` it writes ``ngraph/schemas/results.json``; with it, it
exits nonzero when the committed file differs from the declarations.
"""

from __future__ import annotations

import json
import sys
import types
import typing
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path

import netgraph_core as ngc

import ngraph.results as results
from ngraph.export import _PLAIN, layout

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ngraph/schemas/results.json"
EXPLICIT = ROOT / "dev/explicit_results_schema.json"
ALIASES = (
    "UnitConstraint",
    "CostReport",
    "CostUnavailableReason",
    "MSDStatus",
    "MSDStopReason",
    "MSDProof",
)
JSON_MAPPING = {"type": "object", "additionalProperties": {"$ref": "#/$defs/JSONValue"}}
NAMED = {ngc.OutputOptions: "NativeOutputsJSON"}


def _ref(name: str) -> dict:
    return {"$ref": f"#/$defs/{name}"}


def _is_json(annotation: object) -> bool:
    # JSONValue's forward references are evaluated into a new union.
    members = typing.get_args(annotation)
    return type(None) in members and bool in members and str in members


def schema(annotation: object) -> dict:
    """The JSON Schema of one declared type."""
    aliases = {id(getattr(results, name)): name for name in ALIASES}
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if id(annotation) in aliases:
        return _ref(aliases[id(annotation)] + "JSON")
    if origin is typing.Annotated:
        return {**schema(args[0]), **args[1]}
    if origin is typing.ClassVar:
        return schema(args[0])
    if origin is typing.Literal:
        return {"enum": list(args)}
    if origin in (types.UnionType, typing.Union):
        return {"anyOf": [schema(member) for member in args]}
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        return {"type": "array", "items": schema(args[0])}
    if origin is Mapping and args[0] is str and _is_json(args[1]):
        return dict(JSON_MAPPING)
    simple = {int: "integer", float: "number", str: "string", bool: "boolean"}
    if annotation in simple:
        return {"type": simple[annotation]}
    if annotation is type(None):
        return {"type": "null"}
    if annotation is Fraction:
        return _ref("FractionJSON")
    if annotation in NAMED:
        return _ref(NAMED[annotation])
    if isinstance(annotation, type) and annotation in _PLAIN:
        return _ref(annotation.__name__ + "JSON")
    raise TypeError(f"results schema: no schema for {annotation!r}")


def record(kind: type) -> dict:
    hints = typing.get_type_hints(kind, include_extras=True)
    properties = {name: schema(hints[name]) for name in layout(kind)}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def alias(name: str) -> dict:
    value = getattr(results, name)
    if typing.get_origin(value) is typing.Literal:
        return {"enum": list(typing.get_args(value))}
    return {"anyOf": [schema(member) for member in typing.get_args(value)]}


def generate() -> str:
    explicit = json.loads(EXPLICIT.read_text())
    definitions = dict(explicit["$defs"])
    for kind in _PLAIN:
        definitions[kind.__name__ + "JSON"] = record(kind)
    for name in ALIASES:
        definitions[name + "JSON"] = alias(name)
    document = {**explicit["root"], "$defs": dict(sorted(definitions.items()))}
    return json.dumps(document, indent=2) + "\n"


def main() -> None:
    text = generate()
    if "--check" in sys.argv[1:]:
        if TARGET.read_text() != text:
            sys.exit(
                "ngraph/schemas/results.json differs from the record declarations;"
                " run python dev/generate_results_schema.py"
            )
        print("Results schema matches the record declarations.")
        return
    TARGET.write_text(text)
    print(f"Wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
