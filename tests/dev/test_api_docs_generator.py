"""dev/generate_api_docs.py: Markdown normalization, and a page of exactly the public API."""

import importlib.util
import re
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "generate_api_docs",
    Path(__file__).resolve().parents[2] / "dev" / "generate_api_docs.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
normalize = _MODULE._normalize_markdown_lists


def test_emphasis_spaces_are_removed_keeping_the_text() -> None:
    assert normalize("a ** bold ** b") == "a **bold** b"
    assert normalize("a * it * b") == "a *it* b"
    assert normalize("a __ u __ b") == "a __u__ b"


def test_fenced_code_is_left_unchanged() -> None:
    text = "```\nx = a ** b ** c\n* not a bullet\n```"
    assert normalize(text) == text


def test_code_spans_are_left_unchanged() -> None:
    assert normalize("keep `a ** b ** c` span") == "keep `a ** b ** c` span"


def test_blank_lines_inside_fenced_code_are_kept() -> None:
    text = "```\na = 1\n\n\nb = 2\n```"
    assert normalize(text) == text


def test_list_outside_code_gets_surrounding_blank_lines() -> None:
    assert (
        normalize("Intro:\n- one\n- two\nAfter.") == "Intro:\n\n- one\n- two\n\nAfter."
    )


def test_public_record_help_shows_plain_types():
    import dataclasses
    import inspect

    import ngraph

    # The page documents public records only.
    records = [
        kind
        for kind in (getattr(ngraph, name) for name in ngraph.__all__)
        if isinstance(kind, type)
        and dataclasses.is_dataclass(kind)
        and kind.__module__ == "ngraph.results"
    ]
    assert records
    for kind in records:
        types = [str(inspect.signature(kind))]
        types.extend(str(field.type) for field in dataclasses.fields(kind))
        assert all(
            "Annotated" not in text and "null_when" not in text for text in types
        ), kind.__name__


# Public modules used by the generator control.
PUBLIC = ("ngraph", "ngraph.workflow", "ngraph.hardware", "ngraph.logging")
PAGE = Path(__file__).resolve().parents[2] / "docs/reference/api-full.md"


def _entry_text(page: str, path: str) -> str:
    match = re.search(
        rf"^### {re.escape(path)}\n(.*?)(?=^### |^## |\Z)",
        page,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, path
    return match[1]


def test_multiline_alias_definition_is_valid_python():
    import ast

    definition, _ = _MODULE._defined_value("ngraph", "AnalysisResult")
    ast.parse("AnalysisResult = " + definition)
    page = _entry_text(PAGE.read_text(), "ngraph.AnalysisResult")
    block = re.search(r"```python\n(.*?)\n```", page, re.S)
    assert block is not None
    ast.parse(block[1])
    with pytest.raises(SyntaxError):
        ast.parse("AnalysisResult = A\n    | B")


@pytest.mark.parametrize(
    "definition,wrapped",
    [("Literal[\n 'a', 'b'\n]", False), ("(A\n | B)", False), ("A\n    | B", True)],
)
def test_alias_parentheses_are_added_only_for_an_invalid_expression(
    monkeypatch, definition, wrapped
):
    import ast

    monkeypatch.setattr(
        _MODULE.inspect,
        "getsource",
        lambda module: 'Alias = (A | B)\n"A public alias."\n',
    )
    monkeypatch.setattr(
        _MODULE.ast, "get_source_segment", lambda source, node: definition
    )
    actual, doc = _MODULE._defined_value("ngraph.results", "Alias")
    assert actual == (f"({definition})" if wrapped else definition)
    assert doc == "A public alias."
    ast.parse(actual, mode="eval")


def test_the_generator_renders_a_synthetic_public_callable(monkeypatch):
    import sys
    import types

    throwaway = types.ModuleType("ngraph_throwaway")

    def planted_public(value: int) -> int:
        """A public name of a throwaway module."""
        return value

    planted_public.__module__ = "ngraph_throwaway"
    throwaway.planted_public = planted_public
    throwaway.__all__ = ["planted_public"]
    monkeypatch.setitem(sys.modules, "ngraph_throwaway", throwaway)
    modules = (*PUBLIC, "ngraph_throwaway")
    # The generator reads __all__, so it writes that entry.
    generated = _MODULE.generate_api_documentation(modules=modules)
    assert "`planted_public(value: int) -> int`" in generated


def test_the_generator_renders_a_bare_record(monkeypatch):
    import dataclasses
    import sys
    import types

    # The generator renders a public class without a docstring as undocumented.
    throwaway = types.ModuleType("ngraph_throwaway")

    @dataclasses.dataclass(frozen=True)
    class Bare:
        value: int

    Bare.__module__ = "ngraph_throwaway"
    throwaway.Bare = Bare
    throwaway.__all__ = ["Bare"]
    monkeypatch.setitem(sys.modules, "ngraph_throwaway", throwaway)
    generated = _MODULE.generate_api_documentation(modules=("ngraph_throwaway",))
    assert "### ngraph_throwaway.Bare" in generated
    assert "value" in generated


GUIDE = PAGE.parent / "api.md"
SPAN = re.compile(
    r"(\[?)`((?:ngraph\.(?:workflow|hardware|logging)\.)?([A-Za-z_]\w*))(?:[.(][^`]*)?`(\]\(api-full\.md#([\w-]+)\))?"
)


def _guide_links(guide: str, entries: dict[str, str]) -> list:
    """Actual guide links whose anchor does not match their public entry."""
    prose = re.sub(r"```.*?```", "", guide, flags=re.DOTALL)
    wrong = []
    for match in SPAN.finditer(prose):
        name = match[3]
        if name not in entries or "->" in match[0]:
            continue
        if match[4]:
            if match[5] != entries[name]:
                wrong.append((name, match[5]))
    return wrong


def _anchors() -> dict[str, str]:
    """Each public name with one entry, and the anchor of that entry's heading."""
    from collections import Counter

    entries = [entry for _, part in _MODULE.public_entries() for entry in part]
    counts = Counter(entry["name"] for entry in entries)
    return {
        entry["name"]: re.sub(r"[^\w\- ]", "", entry["paths"][0].lower())
        for entry in entries
        if counts[entry["name"]] == 1
    }


def test_the_guide_links_resolve_to_their_entries():
    wrong = _guide_links(GUIDE.read_text(), _anchors())
    assert wrong == []


def test_the_guide_link_check_fails_on_a_misdirected_name():
    anchors = _anchors()
    guide = GUIDE.read_text()
    misdirected = guide.replace(
        "(api-full.md#ngraphrunresult)", "(api-full.md#ngraphrun)"
    )
    assert _guide_links(misdirected, anchors) == [("RunResult", "ngraphrun")]
