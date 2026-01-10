from __future__ import annotations

import pytest

from ngraph.dsl.blueprints.parser import (
    check_link_keys,
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


def test_check_link_keys_valid_and_missing_required() -> None:
    """Test check_link_keys with valid and invalid link definitions."""
    # Valid with flat properties
    check_link_keys(
        {
            "source": "A",
            "target": "B",
            "pattern": "mesh",
            "count": 1,
            "capacity": 100,
            "cost": 10,
        },
        context="top-level link",
    )

    # Missing required keys
    with pytest.raises(ValueError) as exc:
        check_link_keys({"pattern": "mesh"}, context="link")
    assert "must have 'source' and 'target'" in str(exc.value)

    # Extra key
    with pytest.raises(ValueError) as exc2:
        check_link_keys(
            {
                "source": "A",
                "target": "B",
                "unexpected": True,
            },
            context="link",
        )
    assert "Unrecognized key(s) in link" in str(exc2.value)
