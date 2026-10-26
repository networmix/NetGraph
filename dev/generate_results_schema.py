"""Generate the results JSON Schema from the record declarations.

A plain record (one the exporter writes as its declared class constants and
fields) gets its definition from its type annotations; an ``Annotated``
mapping on a field adds JSON Schema keywords. Type aliases of records or
literals become ``anyOf`` or ``enum`` definitions. Every other definition
(native results, rows, cases, envelopes, questions) is the explicit fragment
in ``dev/explicit_results_schema.json``, matching the exporter's explicit code.

Every field has a description in its one source: a record field's attribute
docstring (the string line after it), or the fragment node's ``description``.
A field without one is refused. The reference page ``docs/reference/results.md``
is written from the generated schema.

Usage: python dev/generate_results_schema.py [--check]
Without ``--check`` it writes ``ngraph/schemas/results.json`` and the reference
page; with it, it exits nonzero when either committed file differs from the
declarations.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import inspect
import json
import re
import sys
import textwrap
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
PAGE = ROOT / "docs/reference/results.md"
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


def field_docs(kind: type) -> dict[str, str]:
    """The attribute docstrings of a record's fields, by field name."""
    body = ast.parse(textwrap.dedent(inspect.getsource(kind))).body[0].body
    docs = {}
    for node, following in zip(body, body[1:], strict=False):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
        ):
            docs[node.target.id] = following.value.value
    return docs


def record(kind: type) -> dict:
    hints = typing.get_type_hints(kind, include_extras=True)
    docs = field_docs(kind)
    # Field metadata: JSON Schema keywords of the field and its presence facts.
    extra = {f.name: dict(f.metadata) for f in dataclasses.fields(kind)}
    properties = {}
    for name in layout(kind):
        value = {**schema(hints[name]), **extra.get(name, {})}
        if name in docs:
            value = {"description": docs[name], **value}
        properties[name] = value
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


def undescribed(
    node: object, path: str, out: list[str], fields: bool = True, root: object = None
) -> None:
    """Field nodes without a non-empty description, here and in every ``$defs`` entry.

    Each definition is walked once, from the document's ``$defs``; a ``$ref`` that names
    no definition is reported too. ``if``/``then``/``else`` hold constraints, not fields.
    """
    if not isinstance(node, dict):
        return
    root = node if root is None else root
    definitions = root.get("$defs", {}) if isinstance(root, dict) else {}
    if node is root:
        for name, value in node.get("$defs", {}).items():
            undescribed(value, f"{path}/$defs/{name}", out, fields, root)
    reference = node.get("$ref")
    if isinstance(reference, str) and reference.rsplit("/", 1)[-1] not in definitions:
        out.append(f"{path} ($ref {reference} names no definition)")
    for name, value in node.get("properties", {}).items():
        description = value.get("description") if isinstance(value, dict) else None
        if fields and not (isinstance(description, str) and description.strip()):
            out.append(f"{path}/{name}")
        undescribed(value, f"{path}/{name}", out, fields, root)
    for key in ("items", "additionalProperties", "not"):
        undescribed(node.get(key), f"{path}/{key}", out, fields, root)
    for key in ("if", "then", "else"):
        undescribed(node.get(key), f"{path}/{key}", out, False, root)
    for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
        for i, value in enumerate(node.get(key, [])):
            undescribed(value, f"{path}/{key}[{i}]", out, fields, root)


PRESENCE_KEYS = ("absent_when", "null_when")


def _accepts_null(node: dict, definitions: dict) -> bool:
    """Whether null validates against a property node: `$ref`s (JSONValue included) and
    anyOf/oneOf/allOf resolved by the schema itself, not by inspecting its shape."""
    import jsonschema

    plain = {k: v for k, v in node.items() if k not in PRESENCE_KEYS}
    return jsonschema.Draft202012Validator({**plain, "$defs": definitions}).is_valid(
        None
    )


# The definition-level keywords the presence check classifies (all the schema uses).
_OBJECT_KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "minProperties",
    "description",
    "allOf",
    "oneOf",
    "if",
    "then",
    "else",
}
_UNION_KEYWORDS = {"anyOf", "enum", "description"}


def _forms(node: object) -> str:
    return "{" + ", ".join(sorted(node)) + "}" if isinstance(node, dict) else repr(node)


def _union_member(node: object) -> bool:
    """A member of a union definition the presence check classifies: a reference, a plain
    type, an array or mapping of references, or a nested union of those."""
    if not isinstance(node, dict):
        return False
    if set(node) == {"$ref"}:
        return True
    if set(node) == {"anyOf"}:
        return all(_union_member(m) for m in node["anyOf"])
    inner = [node[k] for k in ("items", "additionalProperties") if k in node]
    return (
        "type" in node
        and set(node) <= {"type", "items", "additionalProperties"}
        and all(isinstance(i, dict) and set(i) == {"$ref"} for i in inner)
    )


def _narrowed_reference(node: dict) -> bool:
    """A property that narrows a referenced definition where it appears: `allOf` of one
    `$ref` and requirements on its keys (`required`, or `not` of `required`). It leaves the
    presence of the referenced definition's own properties as declared there."""
    members = node.get("allOf")
    if not isinstance(members, list) or not set(node) <= {"allOf", "description"}:
        return False
    refs = [m for m in members if isinstance(m, dict) and set(m) == {"$ref"}]
    rest = [m for m in members if m not in refs]
    return len(refs) == 1 and all(
        isinstance(m, dict)
        and (
            set(m) == {"required"}
            or (set(m) == {"not"} and set(m["not"]) == {"required"})
        )
        for m in rest
    )


def _always_present(definition: dict) -> set[str] | str:
    """The own properties every valid object of a closed definition has, or why that is not
    classified. Besides `required`, a key is always present when the object cannot reach
    `minProperties` without it, or when every `oneOf` alternative that some object matches
    alone (its smallest object: its keys and the own required ones) has it."""
    names, required = set(definition["properties"]), set(definition.get("required", ()))
    least, members = definition.get("minProperties"), definition.get("oneOf")
    if least is None and members is None:
        return required
    if definition.get("additionalProperties") is not False:
        return (
            "minProperties or oneOf on an object that is not closed is not classified"
        )
    if least is not None and members is not None:
        return "minProperties and oneOf together are not classified"
    if not required <= names:
        return f"required keys it does not declare: {sorted(required - names)}"
    if least is not None:
        if not isinstance(least, int) or least > len(names):
            return f"minProperties {least!r} leaves no valid object"
        return required | (names if len(names) - 1 < least else set())
    if not all(isinstance(m, dict) and set(m) == {"required"} for m in members):
        return "oneOf has a member that is not a required list; only alternatives of required keys are classified"
    smallest = [required | set(m["required"]) for m in members]
    if not set().union(*smallest) <= names:
        return f"oneOf requires keys it does not declare: {sorted(set().union(*smallest) - names)}"
    alone = [
        keys
        for i, keys in enumerate(smallest)
        if not any(j != i and set(m["required"]) <= keys for j, m in enumerate(members))
    ]
    if not alone:
        return "no object matches exactly one oneOf alternative"
    return set.intersection(*alone)


def _constant_test(test: object, names: set[str] | None) -> bool:
    """An `if` that tests one key for a constant value, the key on the object itself (one of
    `names`) or one level down: `{"properties": {k: {"const": v}}}` or
    `{"properties": {k: {"properties": {k2: {"const": v}}}}}`, each level optionally
    requiring its key."""
    if not (isinstance(test, dict) and set(test) <= {"properties", "required"}):
        return False
    tested = test.get("properties")
    if not (isinstance(tested, dict) and len(tested) == 1):
        return False
    ((key, inner),) = tested.items()
    if names is not None and key not in names:
        return False
    if test.get("required", [key]) != [key] or not isinstance(inner, dict):
        return False
    return set(inner) == {"const"} or (
        names is not None and _constant_test(inner, None)
    )


def _conditional(node: object, names: set[str]) -> str | None:
    """Why a conditional constraint cannot be classified, or None. Only the form the schema
    uses is classified: a constant test on one key, and `then`/`else` that constrain the
    values of the object's own properties. A `required` list there is refused, so no
    condition makes a key required and presence is read from the definition alone."""
    if not (
        isinstance(node, dict) and "if" in node and set(node) <= {"if", "then", "else"}
    ):
        return "only conditional constraints (if/then/else) are classified"
    if not _constant_test(node["if"], names):
        return "its if is not a constant test on one own key or one level down"
    for branch in ("then", "else"):
        if branch not in node:
            continue
        held = node[branch]
        if isinstance(held, dict) and "required" in held:
            return f"its {branch} holds a required list"
        if not (
            isinstance(held, dict)
            and set(held) == {"properties"}
            and isinstance(held["properties"], dict)
            and set(held["properties"]) <= names
        ):
            return f"its {branch} holds more than value constraints on own properties"
    return None


def presence_forms(document: dict) -> list[str]:
    """Refuse, by name and form, every schema shape the presence check cannot classify.

    The check reads a definition's own `properties`, `required`, `minProperties` and `oneOf`
    (see `_always_present`), so it accepts only the forms the results schema uses. An object
    definition is closed and may add conditional constraints (`if`/`then`/`else`, also as
    `allOf` members) that test one key for a constant and constrain only the values of its
    own properties, and `oneOf` alternatives of required keys, none required by all of them;
    a property may narrow a referenced definition, as a whole, with requirements on its keys.
    A union definition (no properties of its own) is an `enum` or an `anyOf` of references,
    plain types, arrays or mappings of references, and unions of those. Anything else fails
    closed: presence facts outside a definition's own properties (the document root
    included), another keyword or composition, a requirement inside a conditional or through
    composition or a `$ref`, and an inline object.
    """
    out = []

    def stray_facts(node, path):
        if isinstance(node, dict):
            for key in PRESENCE_KEYS:
                if key in node:
                    out.append(
                        f"{path}: {key} outside a definition's own properties "
                        "(only $defs.<D>.properties.<field> may declare presence facts)"
                    )
            for key, value in node.items():
                stray_facts(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                stray_facts(value, f"{path}/{i}")

    def inline_objects(node, path):
        if isinstance(node, dict):
            if _narrowed_reference(node):
                return
            if "properties" in node or "required" in node:
                out.append(
                    f"{path}: an inline object; give it a definition of its own so its "
                    "properties' presence can be classified"
                )
                return
            for key, value in node.items():
                inline_objects(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                inline_objects(value, f"{path}/{i}")

    for key, value in document.items():
        if key != "$defs":
            stray_facts({key: value}, "#")
    for name, definition in document.get("$defs", {}).items():
        where = f"$defs.{name}"
        properties = definition.get("properties")
        for key, value in definition.items():
            if key != "properties":
                stray_facts(value, f"{where}/{key}")
        for field, node in (properties or {}).items():
            if isinstance(node, dict):
                for key, value in node.items():
                    if key not in PRESENCE_KEYS:
                        stray_facts(value, f"{where}.{field}/{key}")
                inline_objects(
                    {k: v for k, v in node.items() if k not in PRESENCE_KEYS},
                    f"{where}.{field}",
                )
        allowed = _OBJECT_KEYWORDS if properties else _UNION_KEYWORDS
        for key in sorted(set(definition) - allowed):
            members = definition[key] if isinstance(definition[key], list) else None
            if key in ("allOf", "anyOf", "oneOf") and members is not None:
                for i, member in enumerate(members):
                    out.append(
                        f"{where}: {key}[{i}] has the form {_forms(member)}, which the "
                        "presence check cannot classify here (declare properties and "
                        "requirements directly on a definition)"
                    )
            elif key == "$ref":
                out.append(
                    f"{where}: a $ref beside its own keywords may require properties; the "
                    "presence check cannot classify it (list every requirement in the "
                    "definition's own required)"
                )
            else:
                out.append(
                    f"{where}: the keyword {key} cannot be classified by the presence check"
                )
        if not properties:
            for i, member in enumerate(definition.get("anyOf", [])):
                if not _union_member(member):
                    out.append(
                        f"{where}: anyOf[{i}] has the form {_forms(member)}, which the "
                        "presence check cannot classify (make a union only of references "
                        "and types)"
                    )
            continue
        if "if" in definition:
            reason = _conditional(
                {k: definition[k] for k in ("if", "then", "else") if k in definition},
                set(properties),
            )
            if reason:
                out.append(f"{where}: its if/then/else cannot be classified: {reason}")
        elif {"then", "else"} & set(definition):
            out.append(f"{where}: then or else without if cannot be classified")
        for i, member in enumerate(definition.get("allOf", [])):
            reason = _conditional(member, set(properties))
            if reason:
                out.append(
                    f"{where}: allOf[{i}] has the form {_forms(member)}; {reason}, so it "
                    "could make a property required (list every requirement in the "
                    "definition's own required)"
                )
        members = definition.get("oneOf")
        if isinstance(members, list) and all(
            isinstance(m, dict) and isinstance(m.get("required"), list) for m in members
        ):
            always = set.intersection(*(set(m["required"]) for m in members))
            if always:
                out.append(
                    f"{where}: oneOf requires {sorted(always)} in every alternative, so "
                    "unconditionally; list them in the definition's own required"
                )
                continue
        present = _always_present(definition)
        if isinstance(present, str):
            out.append(f"{where}: {present}")
    return out


def apply_presence(document: dict) -> list[str]:
    """Render each property's declared presence facts and return the disagreements.

    A property's free `description` says what the value is; when it is missing is declared
    apart, as data: `absent_when` on an optional property, `null_when` on a property null can
    validate against (`"always"` for one that is always null). The generator takes the two
    keys off the node and renders them after the text ("Null when ...", "Absent when ...",
    "Always null: ..."). It refuses a declaration that disagrees with the schema: an optional
    property without `absent_when`, a nullable one without `null_when`, either on a required
    or non-nullable property, and free text that itself says null or absent. Whether each
    declared condition is true of the exporter is a review matter, not checked here.
    """
    out = presence_forms(document)
    if out:
        return out  # the shapes must be classified before any fact is read
    definitions = document.get("$defs", {})
    for name, definition in definitions.items():
        required = (
            _always_present(definition) if definition.get("properties") else set()
        )
        for field, node in definition.get("properties", {}).items():
            if not isinstance(node, dict):
                continue
            where = f"{name}.{field}"
            absent, null = node.pop("absent_when", None), node.pop("null_when", None)
            text = node.get("description", "")
            nullable, optional = _accepts_null(node, definitions), field not in required
            if re.search(r"(?i)\bnull\b", text):
                out.append(f"{where}: the free text says null (declare null_when)")
            if re.search(r"(?i)\babsent\b", text):
                out.append(f"{where}: the free text says absent (declare absent_when)")
            if optional and not absent:
                out.append(f"{where}: optional without absent_when")
            if absent and not optional:
                out.append(f"{where}: absent_when on a required property")
            if nullable and not null:
                out.append(f"{where}: nullable without null_when")
            if null and not nullable:
                out.append(f"{where}: null_when on a property that cannot be null")
            if null == "always":
                text = "Always null: " + text[:1].lower() + text[1:]
            elif null:
                text = f"{text} Null when {null}."
            if absent:
                text = f"{text} Absent when {absent}."
            if text:
                node["description"] = text
    return out


class PresenceError(ValueError):
    """Presence facts that disagree with the schema."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("; ".join(problems))


def _type(node: dict) -> str:
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return f"[{name}](#{name.lower()})"
    if "enum" in node:
        return " \\| ".join(f"`{json.dumps(value)}`" for value in node["enum"])
    if "anyOf" in node:
        return " or ".join(_type(member) for member in node["anyOf"])
    if "allOf" in node:
        # A definition refined by constraints: the definition, then what it adds.
        kinds, notes = [], []
        for member in node["allOf"]:
            if set(member) == {"required"}:
                notes.append("with " + ", ".join(f"`{k}`" for k in member["required"]))
            elif set(member) == {"not"} and set(member["not"]) == {"required"}:
                notes.append(
                    "without " + ", ".join(f"`{k}`" for k in member["not"]["required"])
                )
            else:
                kinds.append(_type(member))
        return " and ".join(kinds) + (f" ({'; '.join(notes)})" if notes else "")
    if node.get("type") == "array":
        return "list of " + _type(node.get("items", {}))
    if "type" in node:
        return str(node["type"])
    return "JSON value"


def page(document: dict) -> str:
    """The results reference: every definition with its fields, types and descriptions."""
    lines = [
        "# Results",
        "",
        "Every JSON object of a results file (`ngraph/schemas/results.json`) and what each",
        "field means, generated from the result declarations. [How NetGraph",
        "computes](../concepts.md#results-and-their-units) explains the numbers. They come",
        "in five kinds:",
        "",
        "- **Bandwidth units:** every `*_units` field and the native amounts, integers in",
        "  units of the run's resolution `q` (the units report holds `q`); units × `q` is the",
        "  physical amount.",
        "- **Physical amounts:** inputs, question offers and designs, `NetworkStats`",
        "  capacities and the units report's input samples, as declared.",
        "- **Ratios:** delivery ratios, alpha, shares and caps, with no unit.",
        "- **Routing costs:** path costs, tunnel costs and their sums, which never take `q`.",
        "  `total_cost` is cost × bandwidth units, so `total_cost` × `q` is cost × physical",
        "  bandwidth.",
        "- **Hardware money and power:** capex and watts.",
        "",
        "Counts are plain integers. An exact fraction is written",
        '`{"numerator": n, "denominator": d}`. A missing key and a `null` value differ: each',
        "field says when it is absent and when it is null. The analysis's `outputs.details`",
        "selects which detail fields appear ([Output",
        "selection](workflow.md#output-selection)). T1 is a `distributed_te` model; T2 is a",
        "`centralized_te` model with a `tunnel_count`.",
        "",
    ]
    for name, definition in document["$defs"].items():
        properties = definition.get("properties")
        if not properties:
            # An alias or a union of other definitions, an enumeration or any JSON value.
            lines += [f"## {name}", "", f"One of: {_type(definition)}.", ""]
            continue
        lines += [
            f"## {name}",
            "",
            "| Field | Type | Description |",
            "| --- | --- | --- |",
        ]
        for field, node in properties.items():
            description = node.get("description", "").replace("|", "\\|")
            lines.append(f"| `{field}` | {_type(node)} | {description} |")
        lines.append("")
    return "\n".join(lines)


def generate() -> str:
    explicit = json.loads(EXPLICIT.read_text())
    definitions = dict(explicit["$defs"])
    for kind in _PLAIN:
        definitions[kind.__name__ + "JSON"] = record(kind)
    for name in ALIASES:
        definitions[name + "JSON"] = alias(name)
    document = {**explicit["root"], "$defs": dict(sorted(definitions.items()))}
    problems = apply_presence(document)
    if problems:
        raise PresenceError(problems)
    return json.dumps(document, indent=2) + "\n"


def main() -> None:
    # Arguments are parsed before anything is generated: --help and an unknown
    # argument stop here and write nothing.
    parser = argparse.ArgumentParser(
        description="Generate the results JSON Schema and its reference page."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit nonzero when either committed file differs, writing nothing",
    )
    check = parser.parse_args().check
    try:
        text = generate()
    except PresenceError as exc:
        sys.exit("results schema presence facts disagree with the schema: " + str(exc))
    missing: list[str] = []
    undescribed(json.loads(text), "#", missing)
    if missing:
        sys.exit("results schema fields without a description: " + ", ".join(missing))
    reference = page(json.loads(text))
    if check:
        if TARGET.read_text() != text or PAGE.read_text() != reference:
            sys.exit(
                "ngraph/schemas/results.json or docs/reference/results.md differs from"
                " the record declarations; run python dev/generate_results_schema.py"
            )
        print("Results schema and reference match the record declarations.")
        return
    TARGET.write_text(text)
    PAGE.write_text(reference)
    print(f"Wrote {TARGET.relative_to(ROOT)} and {PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
