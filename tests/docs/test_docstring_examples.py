"""The examples in the package's docstrings run and print what they show.

Every `Example:`, `Examples:` or `Usage:` section of a docstring is a doctest (its first
line a `>>>` prompt), so its shown answers are compared when the examples run.
"""

import ast
import doctest
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SECTION = re.compile(r"^\s*(Examples?|Usage):(.*)$")


def module_name(path):
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def sections(path):
    """(line, rest of the header line, first nonblank line after it) per example section."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        docstring = ast.get_docstring(node, clean=False)
        if not docstring:
            continue
        start = node.body[0].lineno
        lines = docstring.splitlines()
        for index, line in enumerate(lines):
            found = SECTION.match(line)
            if found:
                following = next(
                    (x.strip() for x in lines[index + 1 :] if x.strip()), ""
                )
                yield start + index, found[2].strip(), following


SOURCES = sorted((ROOT / "ngraph").rglob("*.py"))
MODULES = tuple(module_name(path) for path in SOURCES if ">>>" in path.read_text())


def test_every_docstring_example_is_a_doctest():
    found = [
        (path.relative_to(ROOT), line, rest, following)
        for path in SOURCES
        for line, rest, following in sections(path)
    ]
    assert len(found) >= 10
    assert [f for f in found if f[2] or not f[3].startswith(">>>")] == []


def test_the_docstring_examples_are_found():
    assert set(MODULES) >= {
        "ngraph.cli",
        "ngraph.dsl.blueprints.expand",
        "ngraph.dsl.blueprints.parser",
        "ngraph.dsl.expansion",
        "ngraph.dsl.expansion.brackets",
        "ngraph.explorer",
        "ngraph.model.selectors",
        "ngraph.model.selectors.conditions",
        "ngraph.utils.seed_manager",
        "ngraph.utils.yaml_utils",
    }


@pytest.mark.parametrize("name", MODULES)
def test_docstring_examples(name):
    result = doctest.testmod(importlib.import_module(name))
    assert result.attempted > 0 and result.failed == 0
