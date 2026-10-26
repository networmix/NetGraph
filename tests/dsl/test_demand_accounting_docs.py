"""Demand accounting prose distinguishes exclusions, empty branches and no offered traffic."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_changelog_explains_redistribution_from_self_only_groups():
    changes = (
        (ROOT / "CHANGELOG.md")
        .read_text()
        .split("### Changed\n", 1)[1]
        .split("## [0.24.1]", 1)[0]
    )
    (line,) = [
        line
        for line in changes.splitlines()
        if line.startswith("- ") and "a pairwise or group-pairwise volume" in line
    ]
    for clause in (
        "node-to-itself pairs and same-label group pairs get no share",
        "group or group pair",
        "gives its share to the others",
        "for a group or group pair containing only node-to-itself pairs, 0.24 dropped that share",
        "reported whole as discarded",
        "an empty selection keeps its discarded share",
    ):
        assert clause in line
    assert line + "\n- " in changes


def test_mixed_exclusion_reason_and_empty_branch_rules_are_documented():
    text = (ROOT / "docs/reference/dsl.md").read_text()
    assert (
        "the first exclusion in canonical group and node order supplies its reason"
        in text
    )
    assert "an empty branch keeps its discarded share" in text
    # The expansion rule's home is the concepts page; the YAML reference links it.
    assert (
        "Branches whose only pairs are node-to-itself or same-label group pairs are removed recursively"
        in (ROOT / "docs/concepts.md").read_text()
    )
    assert (
        "A selection that matches no active node keeps its share as an `empty_selection` discard"
        in text
    )
    assert (
        "a group whose nodes are all filtered out is not selected and takes no share"
        in text
    )
    assert (
        "the first exclusion in canonical group and node order supplies its reason"
        in (ROOT / "docs/reference/results.md").read_text()
    )


def test_msd_nothing_offered_rule_is_documented():
    text = (ROOT / "docs/reference/workflow.md").read_text()
    assert "When a demand set offers no traffic" in text
    assert "one probe at `alpha_max`" in text
    assert "`proof` and `stop_reason` both `nothing_offered`" in text
    assert "native integer-unit range or binary64" in text
    assert "MSD reports `range` with `stop_reason` `offer_range`" in text


def test_documentation_files_are_independent_of_working_directory(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    test_changelog_explains_redistribution_from_self_only_groups()
    test_mixed_exclusion_reason_and_empty_branch_rules_are_documented()
    test_msd_nothing_offered_rule_is_documented()
