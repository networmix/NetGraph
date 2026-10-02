"""Markdown normalization in dev/generate_api_docs.py."""

import importlib.util
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
