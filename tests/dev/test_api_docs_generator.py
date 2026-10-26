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


def test_multiline_alias_definition_is_valid_python():
    import ast

    definition, _ = _MODULE._defined_value("ngraph", "UnitConstraint")
    ast.parse("UnitConstraint = " + definition)
    page = _entry_text(PAGE.read_text(), "ngraph.UnitConstraint")
    block = re.search(r"```python\n(.*?)\n```", page, re.S)
    assert block is not None
    ast.parse(block[1])
    with pytest.raises(SyntaxError):
        ast.parse("UnitConstraint = A\n    | B")


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


def _undocumented(page: str) -> list[str]:
    """Entries that say nothing about their object.

    An entry's first paragraph after its import paths, signature and definition is
    its description. It is missing when it is absent, the generator's placeholder,
    a record's default ``Immutable X record.`` text, or a dataclass signature that
    stands in for a docstring.
    """
    found = []
    for block in re.split(r"^### ", page, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        path = heading.strip()
        name = path.rpartition(".")[2]
        body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        paragraphs = [
            text
            for text in (part.strip() for part in re.split(r"\n\s*\n", body))
            if text
            and not text.startswith("Also importable as ")
            and not re.fullmatch(r"`[^`\n]+`", text)
        ]
        first = paragraphs[0] if paragraphs else ""
        if (
            not first
            or first.startswith("**")
            or first == "No documentation available."
            or first == f"Immutable {name} record."
            or first.startswith(f"{name}(")
        ):
            found.append(path)
    return found


def test_every_entry_says_what_its_object_is():
    assert _undocumented(PAGE.read_text()) == []


def test_the_description_check_fails_on_each_kind_of_missing_text(monkeypatch):
    import dataclasses
    import sys
    import types

    page = PAGE.read_text()
    planted = page
    for path, text in (
        ("ngraph.capacity", "No documentation available."),
        ("ngraph.Endpoints", "Immutable Endpoints record."),
        (
            "ngraph.DemandSet",
            "DemandSet(name: 'str', demands: 'tuple[DemandSpec, ...]')",
        ),
    ):
        entry = _entry_text(page, path)
        description = next(
            part.strip()
            for part in re.split(r"\n\s*\n", entry)
            if part.strip()
            and not part.strip().startswith("Also importable as ")
            and not re.fullmatch(r"`[^`\n]+`", part.strip())
        )
        planted = planted.replace(
            f"### {path}\n{entry}",
            f"### {path}\n{entry.replace(description, text, 1)}",
        )
    # An alias entry whose definition has no docstring after it.
    entry = _entry_text(page, "ngraph.Workers")
    planted = planted.replace(
        f"### ngraph.Workers\n{entry}",
        f"### ngraph.Workers\n{entry.split('```')[0]}```python\nWorkers = int\n```\n\n",
    )
    assert sorted(_undocumented(planted)) == [
        "ngraph.DemandSet",
        "ngraph.Endpoints",
        "ngraph.Workers",
        "ngraph.capacity",
    ]

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
    assert _undocumented(generated) == ["ngraph_throwaway.Bare"]


GUIDE = PAGE.parent / "api.md"
SPAN = re.compile(
    r"(\[?)`((?:ngraph\.(?:workflow|hardware|logging)\.)?([A-Za-z_]\w*))(?:[.(][^`]*)?`(\]\(api-full\.md#([\w-]+)\))?"
)


def _guide_links(
    guide: str, entries: dict[str, str]
) -> tuple[set[str], set[str], list]:
    """Public names the guide's prose mentions, those it links, and wrong anchors.

    A mention is a code span outside code blocks that starts with the name; a
    method signature (with ``->``) names no public function.
    """
    prose = re.sub(r"```.*?```", "", guide, flags=re.DOTALL)
    mentioned, linked, wrong = set(), set(), []
    for match in SPAN.finditer(prose):
        name = match[3]
        if name not in entries or "->" in match[0]:
            continue
        mentioned.add(name)
        if match[4]:
            linked.add(name)
            if match[5] != entries[name]:
                wrong.append((name, match[5]))
    return mentioned, linked, wrong


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


def test_the_guide_links_each_public_name_it_mentions_to_its_entry():
    mentioned, linked, wrong = _guide_links(GUIDE.read_text(), _anchors())
    assert len(mentioned) >= 40
    assert sorted(mentioned - linked) == []
    assert wrong == []


def test_the_guide_link_check_fails_on_an_unlinked_or_misdirected_name():
    anchors = _anchors()
    guide = GUIDE.read_text()
    unlinked = re.sub(r"\[`(RunResult)`\]\(api-full\.md#[\w-]+\)", r"`\1`", guide)
    assert sorted(
        _guide_links(unlinked, anchors)[0] - _guide_links(unlinked, anchors)[1]
    ) == ["RunResult"]
    misdirected = guide.replace(
        "(api-full.md#ngraphrunresult)", "(api-full.md#ngraphrun)"
    )
    assert _guide_links(misdirected, anchors)[2] == [("RunResult", "ngraphrun")]
