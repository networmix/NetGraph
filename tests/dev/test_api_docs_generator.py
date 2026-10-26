"""dev/generate_api_docs.py: Markdown normalization, and a page of exactly the public API."""

import importlib.util
import re
from pathlib import Path

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


def test_the_api_reference_shows_plain_types_and_says_when_a_field_is_none():
    import dataclasses
    import inspect
    import pydoc
    import re
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[2] / "docs/reference/api-full.md"
    ).read_text()
    # Field metadata (schema keywords, presence facts) is for the generators, not users.
    assert "Annotated[" not in page
    assert not re.search(r"\{'(null_when|absent_when|minimum|exclusiveMinimum)'", page)
    import ngraph

    # The page documents public records only.
    records = [
        kind
        for kind in (getattr(ngraph, name) for name in ngraph.__all__)
        if isinstance(kind, type)
        and dataclasses.is_dataclass(kind)
        and kind.__module__ == "ngraph.results"
    ]
    stated = 0
    for kind in records:
        text = pydoc.render_doc(kind, renderer=pydoc.plaintext) + str(
            inspect.signature(kind)
        )
        assert "Annotated" not in text and "null_when" not in text, kind.__name__
        for item in dataclasses.fields(kind):
            when = item.metadata.get("null_when")
            if when:
                # The same metadata says when, in words, on the page.
                assert f"- `{item.name}` (" in page and f": None when {when}" in page, (
                    kind.__name__,
                    item.name,
                )
                stated += 1
    assert stated >= 11


# The public API is the __all__ of these modules; the page must list exactly those names.
PUBLIC = ("ngraph", "ngraph.workflow", "ngraph.hardware", "ngraph.logging")
PAGE = Path(__file__).resolve().parents[2] / "docs/reference/api-full.md"


def _page_entries(page: str) -> list[list[str]]:
    """Each entry's import paths: its heading, then any "Also importable as" paths."""
    entries = []
    for block in re.split(r"^### ", page, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        paths = [heading.strip()]
        also = re.match(r"\s*Also importable as (.*)\.\n", body)
        if also:
            paths += re.findall(r"`([^`]+)`", also[1])
        entries.append(paths)
    return entries


def _listed(modules) -> set[str]:
    import importlib

    return {
        f"{name}.{item}"
        for name in modules
        for item in importlib.import_module(name).__all__
    }


def _missing(page: str, modules) -> list[str]:
    found = {path for paths in _page_entries(page) for path in paths}
    return sorted(_listed(modules) - found)


def _extra(page: str, modules) -> list[str]:
    listed = _listed(modules)
    unlisted = [
        path for paths in _page_entries(page) for path in paths if path not in listed
    ]
    private = re.findall(r"^- `(_[A-Za-z0-9_]*)`", page, flags=re.MULTILINE)
    return sorted(unlisted + private)


def _entry_text(page: str, path: str) -> str:
    match = re.search(
        rf"^### {re.escape(path)}\n(.*?)(?=^### |^## |\Z)",
        page,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, path
    return match[1]


def test_every_public_name_has_one_entry_and_nothing_else_does():
    page = PAGE.read_text()
    assert _missing(page, PUBLIC) == []
    assert _extra(page, PUBLIC) == []
    paths = [path for paths in _page_entries(page) for path in paths]
    assert len(paths) == len(set(paths))
    # Two different objects share a name: each gets its own entry.
    assert "ngraph.TunnelCountAnalysis" in paths
    assert "ngraph.workflow.TunnelCountAnalysis" in paths
    # One object exported twice gets one entry naming both paths.
    assert ["ngraph.WorkflowStep", "ngraph.workflow.WorkflowStep"] in (
        _page_entries(page)
    )
    for alias in ("Workers", "MSDStatus", "MSDStopReason", "PhysicalAmount"):
        assert f"{alias} = " in _entry_text(page, f"ngraph.{alias}")


def test_every_member_of_a_public_enum_is_listed():
    import enum
    import importlib

    page = PAGE.read_text()
    checked = 0
    for module_name in PUBLIC:
        module = importlib.import_module(module_name)
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, type) and issubclass(value, enum.Enum):
                text = _entry_text(page, f"{module_name}.{name}")
                for member in value:
                    assert f"- `{member.name}` = " in text, (name, member.name)
                checked += 1
    assert checked >= 1


def test_the_checks_fail_on_a_missing_entry_and_on_an_extra_one(monkeypatch):
    import sys
    import types

    page = PAGE.read_text()
    throwaway = types.ModuleType("ngraph_throwaway")

    def planted_public(value: int) -> int:
        """A public name of a throwaway module."""
        return value

    planted_public.__module__ = "ngraph_throwaway"
    throwaway.planted_public = planted_public
    throwaway.__all__ = ["planted_public"]
    monkeypatch.setitem(sys.modules, "ngraph_throwaway", throwaway)
    modules = (*PUBLIC, "ngraph_throwaway")
    # A listed name without an entry is missing.
    assert _missing(page, modules) == ["ngraph_throwaway.planted_public"]
    # The generator reads __all__, so it writes that entry.
    generated = _MODULE.generate_api_documentation(modules=modules)
    assert _missing(generated, modules) == []
    assert "`planted_public(value: int) -> int`" in generated
    # An unlisted helper's entry and a private attribute line are extra.
    planted = page.replace(
        "### ngraph.Link\n",
        "### ngraph.model.network.helper\n\nA helper.\n\n### ngraph.Link\n\n- `_cache` (dict)\n",
    )
    assert _extra(planted, PUBLIC) == ["_cache", "ngraph.model.network.helper"]
