from __future__ import annotations

import pytest

from ngraph.dsl.blueprints.parser import (
    check_adjacency_keys,
    check_link_params,
    check_no_extra_keys,
    expand_name_patterns,
    join_paths,
)


def test_expand_name_patterns_no_brackets_returns_same() -> None:
    assert expand_name_patterns("fa")[0] == "fa"


def test_expand_name_patterns_single_range() -> None:
    assert expand_name_patterns("fa[1-3]") == ["fa1", "fa2", "fa3"]


def test_expand_name_patterns_multiple_ranges_cartesian() -> None:
    out = expand_name_patterns("fa[1-2]_plane[5-6]")
    assert sorted(out) == sorted(
        ["fa1_plane5", "fa1_plane6", "fa2_plane5", "fa2_plane6"]
    )


def test_join_paths_behavior() -> None:
    assert join_paths("", "/x") == "x"
    assert join_paths("p", "/x") == "p/x"
    assert join_paths("", "x") == "x"
    assert join_paths("p", "x") == "p/x"


def test_check_no_extra_keys_allows_only_expected() -> None:
    check_no_extra_keys({"a": 1}, allowed={"a"}, context="ctx")
    with pytest.raises(ValueError) as exc:
        check_no_extra_keys({"a": 1, "b": 2}, allowed={"a"}, context="ctx")
    assert "Unrecognized key(s) in ctx" in str(exc.value)


def test_check_adjacency_keys_valid_and_missing_required() -> None:
    # Valid
    check_adjacency_keys(
        {
            "source": "A",
            "target": "B",
            "pattern": "mesh",
            "link_count": 1,
            "link_params": {},
        },
        context="top-level adjacency",
    )

    # Missing required keys
    with pytest.raises(ValueError) as exc:
        check_adjacency_keys({"pattern": "mesh"}, context="adj")
    assert "must have 'source' and 'target'" in str(exc.value)

    # Extra key
    with pytest.raises(ValueError) as exc2:
        check_adjacency_keys(
            {
                "source": "A",
                "target": "B",
                "unexpected": True,
            },
            context="adj",
        )
    assert "Unrecognized key(s) in adj" in str(exc2.value)


def test_check_link_params_valid_and_extra_key() -> None:
    # Valid set of keys
    check_link_params(
        {
            "capacity": 1,
            "cost": 2,
            "disabled": False,
            "risk_groups": ["RG"],
            "attrs": {"k": "v"},
        },
        context="ctx",
    )

    # Extra key should raise
    with pytest.raises(ValueError) as exc:
        check_link_params({"capacity": 1, "extra": 0}, context="ctx")
    assert "Unrecognized link_params key(s) in ctx" in str(exc.value)
