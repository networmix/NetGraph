#!/usr/bin/env python3
"""Generate the NetGraph API reference from docstrings.

The page documents the ``__all__`` of the public modules and nothing else. Run
from the project root. Prints to stdout by default; ``--write-file`` writes
docs/reference/api-full.md instead.
"""

import argparse
import ast
import dataclasses
import enum
import importlib
import inspect
import os
import platform
import re
import sys
import types
import typing
from pathlib import Path


def _normalize_markdown_lists(markdown: str) -> str:
    """Normalize common Markdown issues in free-form docstrings.

    Handles:
    - MD032: Insert blank lines before/after lists
    - MD004: Enforce dash-style bullets ("- ") over "* " or "+ "
    - MD007: Reduce excessive indentation for list items (aim for 0 or 2 spaces)
    - MD012: Collapse multiple blank lines into a single blank line
    - MD037: Remove spaces inside emphasis markers on lines without backticks

    Lines inside fenced code blocks are left unchanged.

    Args:
        markdown: Raw markdown text, possibly taken from docstrings.

    Returns:
        Normalized markdown text.
    """
    lines = markdown.splitlines()
    in_code_fence = False
    normalized_lines: list[str] = []

    def is_list_item(candidate: str) -> tuple[bool, str]:
        stripped = candidate.lstrip()
        if stripped.startswith(("- ", "* ", "+ ")):
            return True, "ul"
        # ordered list: 1. item
        i = 0
        while i < len(stripped) and stripped[i].isdigit():
            i += 1
        if (
            i > 0
            and i + 1 < len(stripped)
            and stripped[i] == "."
            and stripped[i + 1] == " "
        ):
            return True, "ol"
        return False, ""

    def fenced_flags(block: list[str]) -> list[bool]:
        # True for fence delimiters and every line between them.
        flags: list[bool] = []
        inside = False
        for text in block:
            if text.lstrip().startswith(("```", "~~~")):
                flags.append(True)
                inside = not inside
            else:
                flags.append(inside)
        return flags

    def previous_nonblank_index(out: list[str]) -> int | None:
        for idx in range(len(out) - 1, -1, -1):
            if out[idx].strip() != "":
                return idx
        return None

    def previous_list_indent(out: list[str]) -> int | None:
        for idx in range(len(out) - 1, -1, -1):
            candidate = out[idx]
            if is_list_item(candidate)[0]:
                return len(candidate) - len(candidate.lstrip())
            if candidate.strip() != "":
                # Hit content; stop searching
                return None
        return None

    for raw_line in lines:
        line = raw_line
        stripped = line.lstrip()

        # Track fenced code blocks (``` or ~~~)
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            normalized_lines.append(line)
            continue

        if in_code_fence:
            normalized_lines.append(line)
            continue

        # Enforce dash-style bullets for UL (MD004)
        if stripped.startswith("* ") or stripped.startswith("+ "):
            indent_len = len(line) - len(stripped)
            line = (" " * indent_len) + "- " + stripped[2:]
            stripped = line.lstrip()

        is_list, _ = is_list_item(line)

        # Insert a blank line before a list (MD032)
        if is_list:
            prev_idx = previous_nonblank_index(normalized_lines)
            if prev_idx is not None:
                prev_line = normalized_lines[prev_idx]
                if prev_line.strip() != "" and not is_list_item(prev_line)[0]:
                    normalized_lines.append("")

        # Reduce excessive indentation for list items (MD007, MD005 consistency)
        if is_list:
            indent_len = len(line) - len(stripped)
            # Match the previous list item's indent; otherwise top level (0).
            prev_indent = previous_list_indent(normalized_lines)
            desired_indent = prev_indent if prev_indent is not None else 0
            if indent_len != desired_indent:
                if (
                    stripped.startswith("- ")
                    or stripped.startswith("* ")
                    or stripped.startswith("+ ")
                ):
                    marker_and_text = stripped
                else:
                    # ordered list: keep the existing numbering to avoid MD029 style conflicts
                    marker_and_text = stripped
                line = (" " * desired_indent) + marker_and_text

        normalized_lines.append(line)

    # Insert a blank line after each list block (MD032)
    fenced = fenced_flags(normalized_lines)
    post: list[str] = []
    i = 0
    while i < len(normalized_lines):
        current = normalized_lines[i]
        post.append(current)
        if is_list_item(current)[0] and not fenced[i]:
            j = i + 1
            # A list block spans list items and the blank lines between them.
            while (
                j < len(normalized_lines)
                and not fenced[j]
                and (
                    normalized_lines[j].strip() == ""
                    or is_list_item(normalized_lines[j])[0]
                )
            ):
                post.append(normalized_lines[j])
                i = j
                j += 1
            if j < len(normalized_lines):
                next_stripped = normalized_lines[j].strip()
                if next_stripped != "" and not is_list_item(normalized_lines[j])[0]:
                    if post and post[-1].strip() != "":
                        post.append("")
        i += 1

    # Collapse multiple blank lines to a single blank line (MD012)
    collapsed: list[str] = []
    for ln, in_fence in zip(post, fenced_flags(post), strict=True):
        if (
            not in_fence
            and ln.strip() == ""
            and collapsed
            and collapsed[-1].strip() == ""
        ):
            continue
        collapsed.append(ln)

    # Remove spaces inside emphasis markers (MD037)
    def fix_emphasis(line: str) -> str:
        # Lines with backticks may hold code spans; leave them alone.
        if "`" in line:
            return line
        line = re.sub(r"\*\*\s+([^*][^*]*?)\s+\*\*", r"**\1**", line)
        # The lookarounds keep the italic rule off bold markers.
        line = re.sub(r"(?<!\*)\*\s+([^*][^*]*?)\s+\*(?!\*)", r"*\1*", line)
        line = re.sub(r"__\s+([^_][^_]*?)\s+__", r"__\1__", line)
        line = re.sub(r"(?<!_)_\s+([^_][^_]*?)\s+_(?!_)", r"_\1_", line)
        return line

    final_lines = [
        line_text if in_fence else fix_emphasis(line_text)
        for line_text, in_fence in zip(collapsed, fenced_flags(collapsed), strict=True)
    ]

    return "\n".join(final_lines)


# Import ngraph from the working tree when run from the project root.
if os.path.exists("ngraph"):
    sys.path.insert(0, ".")


# The public API: each module's __all__, in page order. Nothing else is documented.
PUBLIC_MODULES = ("ngraph", "ngraph.workflow", "ngraph.hardware", "ngraph.logging")


def _defined_value(module_name, name):
    """The source of the module-level assignment that defines ``name``, and its docstring.

    Follows ``from X import name`` (also under ``if TYPE_CHECKING:``) to the module
    that assigns it. The docstring is the string literal right after the assignment,
    the convention record fields use. Returns None when no assignment is found.
    """
    module = importlib.import_module(module_name)
    source = inspect.getsource(module)
    tree = ast.parse(source)
    body = list(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            body.extend(node.body)
    for index, node in enumerate(body):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id] if node.value is not None else []
        else:
            continue
        if name in targets:
            text = ast.get_source_segment(source, node.value)
            following = body[index + 1] if index + 1 < len(body) else None
            doc = None
            if (
                isinstance(following, ast.Expr)
                and isinstance(following.value, ast.Constant)
                and isinstance(following.value.value, str)
            ):
                doc = inspect.cleandoc(following.value.value)
            return text, doc
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if any(alias.name == name for alias in node.names):
                return _defined_value(node.module, name)
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            if any(alias.name == name for alias in node.names):
                package = (
                    module_name
                    if hasattr(module, "__path__")
                    else (module_name.rpartition(".")[0])
                )
                for _ in range(node.level - 1):
                    package = package.rpartition(".")[0]
                target = f"{package}.{node.module}" if node.module else package
                return _defined_value(target, name)
    return None


def _entry_kind(name, obj):
    """``class``, ``enum``, ``function``, ``version`` or ``alias`` for a public name.

    A class or function is documented as itself only under its own name; any other
    public value (``PhysicalAmount = float``, a union, a literal) is a type alias.
    """
    if name == "__version__":
        return "version"
    if getattr(obj, "__name__", None) == name and inspect.isclass(obj):
        return "enum" if issubclass(obj, enum.Enum) else "class"
    if getattr(obj, "__name__", None) == name and inspect.isfunction(obj):
        return "function"
    return "alias"


def public_entries(modules=PUBLIC_MODULES):
    """One list of entries per module, in ``__all__`` order.

    An object exported by several modules has one entry, under the first module
    that lists it, naming every import path.
    """
    sections = []
    seen = {}
    for module_name in modules:
        module = importlib.import_module(module_name)
        entries = []
        for name in module.__all__:
            obj = getattr(module, name)
            path = f"{module_name}.{name}"
            kind = _entry_kind(name, obj)
            key = (name, id(obj)) if kind != "alias" else (name, path)
            if kind != "alias" and key in seen:
                seen[key]["paths"].append(path)
                continue
            entry = {"name": name, "object": obj, "kind": kind, "paths": [path]}
            if kind == "alias":
                found = _defined_value(module_name, name)
                if found is None:
                    raise ValueError(f"{path}: no assignment defines this public name")
                entry["definition"], entry["doc"] = found
            seen[key] = entry
            entries.append(entry)
        sections.append((module_name, entries))
    return sections


class _Shown:
    """An annotation already rendered; signatures print it as is."""

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return self.text


def _union_text(annotation):
    """Render a union as ``X | Y``, or return None for any other annotation.

    Python 3.14 prints ``X | None`` as ``Union`` by name and earlier versions
    print ``Optional[X]`` in signatures; one spelling keeps the reference the
    same whichever supported interpreter generates it.
    """
    if typing.get_origin(annotation) not in (typing.Union, types.UnionType):
        return None
    return " | ".join(
        "None" if arg is type(None) else inspect.formatannotation(arg)
        for arg in typing.get_args(annotation)
    )


def _signature(obj):
    """``str(inspect.signature(obj))`` with unions rendered by ``_union_text``."""

    def shown(annotation):
        text = _union_text(annotation)
        return annotation if text is None else _Shown(text)

    sig = inspect.signature(obj)
    params = [
        p.replace(annotation=shown(p.annotation)) for p in sig.parameters.values()
    ]
    return str(
        sig.replace(parameters=params, return_annotation=shown(sig.return_annotation))
    )


def get_class_info(cls):
    """Collect a class's docstring, public methods, and dataclass fields."""
    doc = inspect.getdoc(cls)
    if dataclasses.is_dataclass(cls):
        # A dataclass without a docstring gets its signature as one, printed
        # by the running interpreter; render it the same way on every version.
        try:
            if doc == cls.__name__ + str(inspect.signature(cls)).replace(
                " -> None", ""
            ):
                doc = cls.__name__ + _signature(cls).replace(" -> None", "")
        except (ValueError, TypeError):
            pass
    info = {
        "name": cls.__name__,
        "doc": doc or "No documentation available.",
        "methods": [],
        "attributes": [],
    }

    # Static methods appear as functions and class methods as bound methods.
    for name, method in inspect.getmembers(cls):
        if not name.startswith("_") and (
            inspect.ismethod(method) or inspect.isfunction(method)
        ):
            try:
                sig = _signature(method)
            except (ValueError, TypeError):
                sig = "()"

            method_doc = inspect.getdoc(method)
            info["methods"].append(
                {
                    "name": name,
                    "signature": sig,
                    "doc": (
                        method_doc.split("\n")[0]
                        if method_doc
                        else "No documentation available."
                    ),
                }
            )

    if hasattr(cls, "__dataclass_fields__"):
        for field_name, field in cls.__dataclass_fields__.items():
            if field_name.startswith("_"):
                continue
            field_type = _union_text(field.type) or getattr(
                field.type, "__name__", str(field.type)
            )

            if field.default is not dataclasses.MISSING:
                default_val = field.default
            elif field.default_factory is not dataclasses.MISSING:
                try:
                    # Show the factory's output, e.g. [] or {}.
                    default_val = field.default_factory()
                except Exception:
                    default_val = f"{field.default_factory.__name__}()"
            else:
                default_val = None

            default_str = str(default_val) if default_val is not None else None
            # Drop non-reproducible reprs such as
            # "<unlocked _thread.lock object at 0x109648810>": the address changes
            # on every run, so the documented value is meaningless to a reader
            # and makes the generated file differ between runs.
            if default_str is not None and " object at 0x" in default_str:
                default_str = None
            # Likewise a value taken from the interpreter that generates the page.
            if default_str == platform.python_version():
                default_str = None

            # A result record states when a field is None in its field metadata (the
            # same fact the results schema renders as "Null when ...").
            null_when = field.metadata.get("null_when")
            info["attributes"].append(
                {
                    "name": field_name,
                    "type": field_type,
                    "default": default_str,
                    "none_when": null_when,
                }
            )

    return info


def get_function_info(func):
    """Collect a function's name, signature, and docstring."""
    try:
        sig = _signature(func)
    except (ValueError, TypeError):
        sig = "()"

    return {
        "name": func.__name__,
        "signature": sig,
        "doc": inspect.getdoc(func) or "No documentation available.",
    }


def document_entry(entry):
    """Render one public name: its import paths, then what its kind shows."""
    paths, obj, kind = entry["paths"], entry["object"], entry["kind"]
    doc = f"### {paths[0]}\n\n"
    if len(paths) > 1:
        also = ", ".join(f"`{path}`" for path in paths[1:])
        doc += f"Also importable as {also}.\n\n"

    if kind == "version":
        return doc + "The installed package version, a string.\n\n"

    if kind == "alias":
        doc += f"```python\n{entry['name']} = {entry['definition']}\n```\n\n"
        if entry["doc"]:
            doc += f"{_normalize_markdown_lists(entry['doc'])}\n\n"
        return doc

    if kind == "function":
        info = get_function_info(obj)
        doc += f"`{info['name']}{info['signature']}`\n\n"
        return doc + f"{_normalize_markdown_lists(info['doc'])}\n\n"

    info = get_class_info(obj)
    doc += f"{_normalize_markdown_lists(info['doc'])}\n\n"

    if kind == "enum":
        doc += "**Members:**\n\n"
        for member in obj:
            doc += f"- `{member.name}` = {member.value!r}\n"
        doc += "\n"

    if info["attributes"]:
        doc += "**Attributes:**\n\n"
        for attr in info["attributes"]:
            type_info = f" ({attr['type']})" if attr["type"] != "typing.Any" else ""
            default_info = f" = {attr['default']}" if attr["default"] else ""
            when = attr.get("none_when")
            none_info = (
                ""
                if not when
                else ": always None"
                if when == "always"
                else f": None when {when}"
            )
            # Keep attributes as a single-level list line to satisfy Markdown linters
            doc += f"- `{attr['name']}`{type_info}{default_info}{none_info}\n"
        doc += "\n"

    if info["methods"]:
        doc += "**Methods:**\n\n"
        for method in info["methods"]:
            # Avoid nested list items to satisfy Markdown linters (MD007)
            if method["doc"] and method["doc"] != "No documentation available.":
                doc += f"- `{method['name']}{method['signature']}` - {method['doc']}\n"
            else:
                doc += f"- `{method['name']}{method['signature']}`\n"
        doc += "\n"

    return doc


def generate_api_documentation(output_to_file=False, modules=PUBLIC_MODULES):
    """Render the API reference for the public names of ``modules``.

    Args:
        output_to_file (bool): If True, write to docs/reference/api-full.md.
            If False, return the documentation string.
        modules: The modules whose ``__all__`` the page documents, in page order.

    Returns:
        str: The generated documentation when ``output_to_file`` is False;
            otherwise None.
    """
    sections = public_entries(modules)
    count = sum(len(entries) for _, entries in sections)
    print(f"🔍 Documenting {count} public names of {len(modules)} modules...")

    doc = """<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# Python API (generated)

Every public name of NetGraph, generated from the docstrings: the `__all__` of `ngraph`, `ngraph.workflow`, `ngraph.hardware` and `ngraph.logging`, and nothing else. The [Python API](api.md) guide shows the same API by task, with examples.

"""
    for module_name, entries in sections:
        doc += f"## {module_name}\n\n"
        for entry in entries:
            doc += document_entry(entry)
        doc += "---\n\n"

    doc += """## Errors

`Scenario.from_yaml` refuses invalid input with `ValueError`, whose message starts with the field's path and value. A constructor refuses an invalid field with `ValueError` naming the field. Each entry's Raises section lists its other cases.
"""

    if output_to_file:
        output_path = Path("docs/reference/api-full.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(doc)

        print("✅ API documentation generated successfully!")
        print(f"📄 Written to: {output_path}")
        print(f"📊 Size: {len(doc):,} characters")
    else:
        return doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate API documentation for NetGraph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_api_docs.py                # Output to stdout
  python generate_api_docs.py --write-file   # Write to docs/reference/api-full.md
        """,
    )
    parser.add_argument(
        "--write-file",
        action="store_true",
        help="Write documentation to docs/reference/api-full.md instead of stdout",
    )

    args = parser.parse_args()

    if args.write_file:
        generate_api_documentation(output_to_file=True)
    else:
        doc = generate_api_documentation(output_to_file=False)
        print(doc)
