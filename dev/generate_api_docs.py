#!/usr/bin/env python3
"""Generate the NetGraph API reference from docstrings.

Run from the project root. Prints to stdout by default; ``--write-file``
writes docs/reference/api-full.md instead.
"""

import argparse
import dataclasses
import glob
import importlib
import inspect
import os
import re
import sys
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

        is_list, list_kind = is_list_item(line)

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


def discover_modules():
    """Return ngraph module names to document, in documentation order.

    Skips ``__init__.py`` and ``__main__.py``.
    """
    modules = []

    for py_file in glob.glob("ngraph/**/*.py", recursive=True):
        filename = os.path.basename(py_file)
        if filename in ["__init__.py", "__main__.py"]:
            continue

        module_path = py_file.replace("/", ".").replace(".py", "")
        modules.append(module_path)

    def module_sort_key(module_name):
        """Put top-level modules first, then subpackages in the listed order."""
        parts = module_name.split(".")
        if len(parts) == 2:
            return (0, parts[1])
        # Subpackages not listed here sort last.
        order = [
            "model",
            "workflow",
            "dsl",
            "results",
            "profiling",
            "types",
            "utils",
            "analysis",
            "lib",
        ]
        if len(parts) >= 3 and parts[1] in order:
            return (1 + order.index(parts[1]), ".".join(parts[2:]))
        return (99, module_name)

    modules.sort(key=module_sort_key)
    return modules


def get_class_info(cls):
    """Collect a class's docstring, public methods, and dataclass fields."""
    info = {
        "name": cls.__name__,
        "doc": inspect.getdoc(cls) or "No documentation available.",
        "methods": [],
        "attributes": [],
    }

    # Static methods appear as functions and class methods as bound methods.
    for name, method in inspect.getmembers(cls):
        if not name.startswith("_") and (
            inspect.ismethod(method) or inspect.isfunction(method)
        ):
            try:
                sig = str(inspect.signature(method))
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
            field_type = getattr(field.type, "__name__", str(field.type))

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

            info["attributes"].append(
                {
                    "name": field_name,
                    "type": field_type,
                    "default": default_str,
                }
            )

    return info


def get_function_info(func):
    """Collect a function's name, signature, and docstring."""
    try:
        sig = str(inspect.signature(func))
    except (ValueError, TypeError):
        sig = "()"

    return {
        "name": func.__name__,
        "signature": sig,
        "doc": inspect.getdoc(func) or "No documentation available.",
    }


def document_module(module_name):
    """Render one module's section: docstring, public classes, and functions.

    An import failure yields a section that reports the error.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        return f"## {module_name}\n\n**Error importing module:** {e}\n\n---\n"

    doc = f"## {module_name}\n\n"

    if module.__doc__:
        docstring = _normalize_markdown_lists(module.__doc__.strip())
        doc += f"{docstring}\n\n"

    # Skip names imported from other modules.
    classes = []
    functions = []

    for name, obj in inspect.getmembers(module):
        if not name.startswith("_"):
            if inspect.isclass(obj) and obj.__module__ == module_name:
                classes.append(get_class_info(obj))
            elif inspect.isfunction(obj) and obj.__module__ == module_name:
                functions.append(get_function_info(obj))

    for cls_info in classes:
        doc += f"### {cls_info['name']}\n\n"
        doc += f"{_normalize_markdown_lists(cls_info['doc'])}\n\n"

        if cls_info["attributes"]:
            doc += "**Attributes:**\n\n"
            for attr in cls_info["attributes"]:
                type_info = f" ({attr['type']})" if attr["type"] != "typing.Any" else ""
                default_info = f" = {attr['default']}" if attr["default"] else ""
                # Keep attributes as a single-level list line to satisfy Markdown linters
                doc += f"- `{attr['name']}`{type_info}{default_info}\n"
            doc += "\n"

        if cls_info["methods"]:
            doc += "**Methods:**\n\n"
            for method in cls_info["methods"]:
                # Avoid nested list items to satisfy Markdown linters (MD007)
                if method["doc"] and method["doc"] != "No documentation available.":
                    doc += (
                        f"- `{method['name']}{method['signature']}` - {method['doc']}\n"
                    )
                else:
                    doc += f"- `{method['name']}{method['signature']}`\n"
            doc += "\n"

    for func_info in functions:
        doc += f"### {func_info['name']}{func_info['signature']}\n\n"
        doc += f"{_normalize_markdown_lists(func_info['doc'])}\n\n"

    doc += "---\n\n"
    return doc


def generate_api_documentation(output_to_file=False):
    """Render the API reference for every discovered module.

    Args:
        output_to_file (bool): If True, write to docs/reference/api-full.md.
            If False, return the documentation string.

    Returns:
        str: The generated documentation when ``output_to_file`` is False;
            otherwise None.
    """
    modules = discover_modules()

    print(f"🔍 Auto-discovered {len(modules)} modules to document...")

    header = f"""<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

Every public module, class and function, generated from the docstrings.
The [API guide](api.md) covers the same API with examples.

Quick links:

- [API Guide](api.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Modules auto-discovered: {len(modules)}

---

"""

    print("📝 Generating API documentation...")
    doc = header

    for module_name in modules:
        print(f"  📝 Documenting {module_name}")
        try:
            module_doc = document_module(module_name)
            doc += module_doc
        except Exception as e:
            print(f"  ⚠️  Error documenting {module_name}: {e}")
            doc += f"## {module_name}\n\n**Error:** Could not generate documentation for this module: {e}\n\n---\n\n"

    footer = """
## Errors

Invalid input mostly raises `ValueError`; a scenario that fails schema validation raises `jsonschema.ValidationError`. Each entry's Raises section lists its cases.
"""

    doc += footer

    if output_to_file:
        output_path = Path("docs/reference/api-full.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(doc)

        print("✅ API documentation generated successfully!")
        print(f"📄 Written to: {output_path}")
        print(f"📊 Size: {len(doc):,} characters")
        print(f"📚 Modules documented: {len(modules)}")
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
