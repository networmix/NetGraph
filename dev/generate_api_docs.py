#!/usr/bin/env python3
"""
Generate API documentation for NetGraph
This script should be run from the project root directory.

By default, outputs documentation to stdout.
Use --write-file to write to docs/reference/api-full.md instead.
"""

import argparse
import dataclasses
import glob
import importlib
import inspect
import os
import sys
from datetime import datetime
from pathlib import Path


def _normalize_markdown_lists(markdown: str) -> str:
    """Normalize common Markdown issues in free-form docstrings.

    Handles:
    - MD032: Ensure blank lines before/after lists
    - MD004: Enforce dash-style bullets ("- ") over "* " or "+ "
    - MD007: Reduce excessive indentation for list items (aim for 0 or 2 spaces)
    - MD012: Collapse multiple blank lines into a single blank line

    Skips transformations inside fenced code blocks.

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

        # Detect list items
        is_list, list_kind = is_list_item(line)

        # Ensure blank line before a list (MD032)
        if is_list:
            prev_idx = previous_nonblank_index(normalized_lines)
            if prev_idx is not None:
                prev_line = normalized_lines[prev_idx]
                if prev_line.strip() != "" and not is_list_item(prev_line)[0]:
                    normalized_lines.append("")

        # Reduce excessive indentation for list items (MD007, MD005 consistency)
        if is_list:
            indent_len = len(line) - len(stripped)
            # Use previous list item's indent if present for consistency; else top-level 0
            prev_indent = previous_list_indent(normalized_lines)
            desired_indent = prev_indent if prev_indent is not None else 0
            if indent_len != desired_indent:
                # Normalize to desired indent while preserving marker and text
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

    # Ensure blank line after list blocks (MD032) and collapse multiple blanks (MD012)
    post: list[str] = []
    i = 0
    while i < len(normalized_lines):
        current = normalized_lines[i]
        post.append(current)
        # Add blank line after a list block if next non-list, non-blank starts
        if is_list_item(current)[0]:
            j = i + 1
            # Collect contiguous list block
            while j < len(normalized_lines) and (
                normalized_lines[j].strip() == ""
                or is_list_item(normalized_lines[j])[0]
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
    for ln in post:
        if ln.strip() == "" and collapsed and collapsed[-1].strip() == "":
            continue
        collapsed.append(ln)

    # Normalize emphasis spacing (MD037) outside code and inline code spans
    import re

    def fix_emphasis(line: str) -> str:
        # Skip lines containing backticks to avoid touching code spans
        if "`" in line:
            return line
        # Bold asterisks
        line = re.sub(r"\*\*\s+([^*][^*]*?)\s+\*\*", r"**\\1**", line)
        # Italic asterisks (avoid interfering with bold by requiring not '**')
        line = re.sub(r"(?<!\*)\*\s+([^*][^*]*?)\s+\*(?!\*)", r"*\\1*", line)
        # Bold underscores
        line = re.sub(r"__\s+([^_][^_]*?)\s+__", r"__\\1__", line)
        # Italic underscores (avoid double underscores)
        line = re.sub(r"(?<!_)_\s+([^_][^_]*?)\s+_(?!_)", r"_\\1_", line)
        return line

    final_lines = [fix_emphasis(line_text) for line_text in collapsed]

    return "\n".join(final_lines)


# Add the current directory to Python path for development installs
if os.path.exists("ngraph"):
    sys.path.insert(0, ".")


def discover_modules():
    """Automatically discover all documentable Python modules in the ngraph package."""
    modules = []

    # Find all .py files in ngraph/
    for py_file in glob.glob("ngraph/**/*.py", recursive=True):
        # Skip files that shouldn't be documented
        filename = os.path.basename(py_file)
        if filename in ["__init__.py", "__main__.py"]:
            continue

        # Convert file path to module name
        module_path = py_file.replace("/", ".").replace(".py", "")
        modules.append(module_path)

    # Sort modules in logical order for documentation
    def module_sort_key(module_name):
        """Sort key to organize modules in logical documentation order."""
        parts = module_name.split(".")
        # Main ngraph modules first (ngraph.xxx)
        if len(parts) == 2:
            return (0, parts[1])
        # Order for top-level packages
        order = [
            "graph",
            "model",
            "algorithms",
            "paths",
            "flows",
            "solver",
            "demand",
            "failure",
            "workflow",
            "dsl",
            "results",
            "monte_carlo",
            "profiling",
            "types",
            "utils",
        ]
        if len(parts) >= 3 and parts[1] in order:
            return (1 + order.index(parts[1]), ".".join(parts[2:]))
        return (99, module_name)

    modules.sort(key=module_sort_key)
    return modules


def get_class_info(cls):
    """Extract comprehensive information about a class."""
    info = {
        "name": cls.__name__,
        "doc": inspect.getdoc(cls) or "No documentation available.",
        "methods": [],
        "attributes": [],
    }

    # Get methods (including static and class methods)
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

    # Get dataclass fields if applicable
    if hasattr(cls, "__dataclass_fields__"):
        for field_name, field in cls.__dataclass_fields__.items():
            field_type = getattr(field.type, "__name__", str(field.type))

            # Handle dataclass field defaults properly
            if field.default is not dataclasses.MISSING:
                default_val = field.default
            elif field.default_factory is not dataclasses.MISSING:
                try:
                    # Try to call the factory to get a representative value
                    default_val = field.default_factory()
                except Exception:
                    default_val = f"{field.default_factory.__name__}()"
            else:
                default_val = None

            info["attributes"].append(
                {
                    "name": field_name,
                    "type": field_type,
                    "default": str(default_val) if default_val is not None else None,
                }
            )

    return info


def get_function_info(func):
    """Extract information about a function."""
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
    """Generate documentation for a single module."""
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        return f"## {module_name}\n\n**Error importing module:** {e}\n\n---\n"

    doc = f"## {module_name}\n\n"

    # Module docstring
    if module.__doc__:
        docstring = _normalize_markdown_lists(module.__doc__.strip())
        doc += f"{docstring}\n\n"

    # Get classes and functions defined in this module
    classes = []
    functions = []

    for name, obj in inspect.getmembers(module):
        if not name.startswith("_"):
            if inspect.isclass(obj) and obj.__module__ == module_name:
                classes.append(get_class_info(obj))
            elif inspect.isfunction(obj) and obj.__module__ == module_name:
                functions.append(get_function_info(obj))

    # Document classes
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

    # Document functions
    for func_info in functions:
        doc += f"### {func_info['name']}{func_info['signature']}\n\n"
        doc += f"{_normalize_markdown_lists(func_info['doc'])}\n\n"

    doc += "---\n\n"
    return doc


def generate_api_documentation(output_to_file=False):
    """Generate the complete API documentation.

    Args:
        output_to_file (bool): If True, write to docs/reference/api-full.md.
                               If False, return the documentation string.

    Returns:
        str: The generated documentation (when output_to_file=False)
    """

    # Automatically discover all documentable modules
    modules = discover_modules()

    print(f"🔍 Auto-discovered {len(modules)} modules to document...")

    # Generate header
    timestamp = datetime.now().strftime("%B %d, %Y at %H:%M UTC")
    header = f"""<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see [api.md](api.md).

Quick links:

- [Main API Guide (api.md)](api.md)
- [This Document (api-full.md)](api-full.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Generated from source code on: {timestamp}

Modules auto-discovered: {len(modules)}

---

"""

    print("📝 Generating API documentation...")
    doc = header

    # Generate documentation for each module
    for module_name in modules:
        print(f"  📝 Documenting {module_name}")
        try:
            module_doc = document_module(module_name)
            doc += module_doc
        except Exception as e:
            print(f"  ⚠️  Error documenting {module_name}: {e}")
            doc += f"## {module_name}\n\n**Error:** Could not generate documentation for this module: {e}\n\n---\n\n"

    # Add footer
    footer = """
## Error Handling

NetGraph uses standard Python exceptions:

- `ValueError` - For validation errors
- `KeyError` - For missing required fields
- `RuntimeError` - For runtime errors

For complete method signatures and detailed documentation, use Python's help system:

```python
help(ngraph.scenario.Scenario)
help(ngraph.network.Network.max_flow)
```

---

*This documentation was auto-generated from the NetGraph source code.*
"""

    doc += footer

    if output_to_file:
        # Ensure output directory exists
        output_path = Path("docs/reference/api-full.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(doc)

        print("✅ API documentation generated successfully!")
        print(f"📄 Written to: {output_path}")
        print(f"📊 Size: {len(doc):,} characters")
        print(f"📚 Modules documented: {len(modules)}")
    else:
        # Return the documentation string
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
        # Output to stdout
        doc = generate_api_documentation(output_to_file=False)
        print(doc)
