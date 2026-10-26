"""The public refusal statements describe the executable input boundaries."""

from pathlib import Path

import pytest

from ngraph import Component
from ngraph.cli import _summarize_selector
from ngraph.hardware import hardware_inventory
from ngraph.model.components import resolve_link_end, totals_with_multiplier

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "method", ["total_capex", "total_power", "total_power_max", "total_capacity"]
)
def test_component_total_docstrings_disclose_the_finite_refusal(method):
    doc = getattr(Component, method).__doc__
    assert "Raises:" in doc and "ValueError:" in doc and "finite float range" in doc


def test_hardware_resolver_and_multiplier_refusals_are_disclosed():
    assert "finite float range" in totals_with_multiplier.__doc__
    for function in (resolve_link_end, hardware_inventory):
        assert "Raises:" in function.__doc__
        assert "``exclusive``" in function.__doc__ and "boolean" in function.__doc__
    assert "finite float range" in hardware_inventory.__doc__
    assert "a compared" not in _summarize_selector.__doc__
    assert "group key" in _summarize_selector.__doc__


def test_release_notes_disclose_the_three_boundary_changes():
    release = (ROOT / "CHANGELOG.md").read_text().split("## [0.24.1]")[0]
    boolean = next(
        line
        for line in release.splitlines()
        if "hardware `exclusive`" in line and "**BREAKING**" in line
    )
    for text in (
        "get_bom(include_disabled)",
        "print_tree(skip_leaves, detailed, include_disabled)",
        "find_links(any_direction)",
        '"false"',
        "truthiness",
        "Python boolean flag arguments",
    ):
        assert text in boolean
    assert "`2**53 + 1 > 2**53` was false" in release
    assert "integers above the float range crashed" in release
    assert "Hardware totals too large for a finite float are refused" in release
    assert "0.24 wrote them as infinity" in release
    assert "`Infinity` in the results file (not valid JSON)" in release
    assert "`inf` in `ngraph inspect`" in release
    dsl = (ROOT / "docs/reference/dsl.md").read_text()
    assert "A link end's `exclusive` must be a boolean" in dsl
    assert (
        "Hardware totals too large for a finite float are refused with the entity and field named."
        in dsl
    )
