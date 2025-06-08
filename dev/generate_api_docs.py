#!/usr/bin/env python3
"""
Generate API documentation for NetGraph
This script should be run from the project root directory.

By default, outputs documentation to stdout.
Use --write-file to write to docs/reference/api-full.md instead.
"""

import argparse
import dataclasses
import importlib
import inspect
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the current directory to Python path for development installs
if os.path.exists("ngraph"):
    sys.path.insert(0, ".")


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
        doc += f"{module.__doc__.strip()}\n\n"

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
        doc += f"{cls_info['doc']}\n\n"

        if cls_info["attributes"]:
            doc += "**Attributes:**\n\n"
            for attr in cls_info["attributes"]:
                type_info = f" ({attr['type']})" if attr["type"] != "typing.Any" else ""
                default_info = f" = {attr['default']}" if attr["default"] else ""
                doc += f"- `{attr['name']}`{type_info}{default_info}\n"
            doc += "\n"

        if cls_info["methods"]:
            doc += "**Methods:**\n\n"
            for method in cls_info["methods"]:
                doc += f"- `{method['name']}{method['signature']}`\n"
                if method["doc"] and method["doc"] != "No documentation available.":
                    doc += f"  - {method['doc']}\n"
            doc += "\n"

    # Document functions
    for func_info in functions:
        doc += f"### {func_info['name']}{func_info['signature']}\n\n"
        doc += f"{func_info['doc']}\n\n"

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

    # Modules to document (in order)
    modules = [
        "ngraph.scenario",
        "ngraph.network",
        "ngraph.explorer",
        "ngraph.components",
        "ngraph.blueprints",
        "ngraph.traffic_demand",
        "ngraph.failure_policy",
        "ngraph.failure_manager",
        "ngraph.traffic_manager",
        "ngraph.results",
        "ngraph.lib.graph",
        "ngraph.lib.util",
        "ngraph.lib.algorithms.spf",
        "ngraph.lib.algorithms.max_flow",
        "ngraph.lib.algorithms.base",
        "ngraph.workflow.base",
        "ngraph.workflow.build_graph",
        "ngraph.workflow.capacity_probe",
        "ngraph.transform.base",
        "ngraph.transform.enable_nodes",
        "ngraph.transform.distribute_external",
    ]

    # Generate header
    timestamp = datetime.now().strftime("%B %d, %Y at %H:%M UTC")
    header = f"""# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see **[api.md](api.md)**.

> **📋 Documentation Types:**

> - **[Main API Guide (api.md)](api.md)** - Curated examples and usage patterns
> - **This Document (api-full.md)** - Complete auto-generated reference
> - **[CLI Reference](cli.md)** - Command-line interface
> - **[DSL Reference](dsl.md)** - YAML syntax guide

**Generated from source code on:** {timestamp}

---

"""

    print("🔍 Generating API documentation...")
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
