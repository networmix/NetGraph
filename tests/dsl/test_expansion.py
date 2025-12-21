"""Comprehensive tests for the variable expansion system.

Tests for ngraph.dsl.expansion modules:
- ExpansionSpec: schema for expansion configuration
- expand_templates: variable substitution in templates
- substitute_vars: single template substitution
- expand_name_patterns: bracket expansion for names
"""

import pytest

from ngraph.dsl.expansion import (
    ExpansionSpec,
    expand_name_patterns,
    expand_risk_group_refs,
    expand_templates,
    substitute_vars,
)

# ──────────────────────────────────────────────────────────────────────────────
# ExpansionSpec Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestExpansionSpec:
    """Tests for ExpansionSpec dataclass."""

    def test_default_values(self) -> None:
        """Default ExpansionSpec has empty vars and cartesian mode."""
        spec = ExpansionSpec()
        assert spec.expand_vars == {}
        assert spec.expansion_mode == "cartesian"

    def test_is_empty(self) -> None:
        """is_empty returns True for empty expand_vars."""
        assert ExpansionSpec().is_empty() is True
        assert ExpansionSpec(expand_vars={"x": [1]}).is_empty() is False

    def test_custom_values(self) -> None:
        """Custom values are preserved."""
        spec = ExpansionSpec(expand_vars={"dc": [1, 2]}, expansion_mode="zip")
        assert spec.expand_vars == {"dc": [1, 2]}
        assert spec.expansion_mode == "zip"


# ──────────────────────────────────────────────────────────────────────────────
# substitute_vars Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSubstituteVars:
    """Tests for substitute_vars function."""

    def test_dollar_var_syntax(self) -> None:
        """$var syntax is substituted."""
        result = substitute_vars("dc$num/leaf", {"num": 1})
        assert result == "dc1/leaf"

    def test_dollar_brace_syntax(self) -> None:
        """${var} syntax is substituted."""
        result = substitute_vars("dc${num}/leaf", {"num": 1})
        assert result == "dc1/leaf"

    def test_multiple_vars(self) -> None:
        """Multiple variables are substituted."""
        result = substitute_vars("dc${dc}_rack${rack}", {"dc": 1, "rack": 2})
        assert result == "dc1_rack2"

    def test_same_var_multiple_times(self) -> None:
        """Same variable used multiple times."""
        result = substitute_vars("dc${dc}/pod${dc}", {"dc": 1})
        assert result == "dc1/pod1"

    def test_no_vars_passthrough(self) -> None:
        """String without variables passes through unchanged."""
        result = substitute_vars("static_path", {})
        assert result == "static_path"

    def test_missing_var_raises(self) -> None:
        """Missing variable raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            substitute_vars("dc${missing}", {})

    def test_regex_not_confused(self) -> None:
        """Regex quantifiers {m,n} are not confused with variables."""
        result = substitute_vars("^node{1,3}$", {})
        assert result == "^node{1,3}$"

    def test_underscore_in_var_name(self) -> None:
        """Variable names with underscores work."""
        result = substitute_vars("${my_var}", {"my_var": "value"})
        assert result == "value"


# ──────────────────────────────────────────────────────────────────────────────
# expand_templates Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestExpandTemplatesCartesian:
    """Tests for expand_templates with cartesian mode."""

    def test_single_var_expands(self) -> None:
        """Single variable expands to multiple results."""
        spec = ExpansionSpec(expand_vars={"dc": [1, 2, 3]})
        results = list(expand_templates({"path": "dc${dc}"}, spec))

        assert len(results) == 3
        assert results[0] == {"path": "dc1"}
        assert results[1] == {"path": "dc2"}
        assert results[2] == {"path": "dc3"}

    def test_multiple_vars_cartesian(self) -> None:
        """Multiple variables create cartesian product."""
        spec = ExpansionSpec(expand_vars={"dc": [1, 2], "rack": ["a", "b"]})
        results = list(expand_templates({"path": "dc${dc}_rack${rack}"}, spec))

        assert len(results) == 4  # 2 * 2
        paths = [r["path"] for r in results]
        assert "dc1_racka" in paths
        assert "dc1_rackb" in paths
        assert "dc2_racka" in paths
        assert "dc2_rackb" in paths

    def test_multiple_templates(self) -> None:
        """Multiple template fields are all expanded."""
        spec = ExpansionSpec(expand_vars={"dc": [1, 2]})
        results = list(
            expand_templates({"source": "dc${dc}/leaf", "sink": "dc${dc}/spine"}, spec)
        )

        assert len(results) == 2
        assert results[0] == {"source": "dc1/leaf", "sink": "dc1/spine"}
        assert results[1] == {"source": "dc2/leaf", "sink": "dc2/spine"}

    def test_empty_vars_yields_original(self) -> None:
        """Empty expand_vars yields original template."""
        spec = ExpansionSpec()
        results = list(expand_templates({"path": "static"}, spec))

        assert len(results) == 1
        assert results[0] == {"path": "static"}


class TestExpandTemplatesZip:
    """Tests for expand_templates with zip mode."""

    def test_zip_pairs_by_index(self) -> None:
        """Zip mode pairs variables by index."""
        spec = ExpansionSpec(
            expand_vars={"src": ["a", "b"], "dst": ["x", "y"]}, expansion_mode="zip"
        )
        results = list(expand_templates({"path": "${src}->${dst}"}, spec))

        assert len(results) == 2
        assert results[0] == {"path": "a->x"}
        assert results[1] == {"path": "b->y"}

    def test_zip_mismatched_lengths_raises(self) -> None:
        """Zip mode with mismatched list lengths raises."""
        spec = ExpansionSpec(
            expand_vars={"src": ["a", "b"], "dst": ["x", "y", "z"]},
            expansion_mode="zip",
        )
        with pytest.raises(ValueError, match="equal-length"):
            list(expand_templates({"path": "${src}->${dst}"}, spec))


class TestExpandTemplatesLimits:
    """Tests for expansion limits."""

    def test_large_expansion_raises(self) -> None:
        """Expansion exceeding limit raises."""
        # Create vars that would produce > 10,000 combinations
        spec = ExpansionSpec(
            expand_vars={
                "a": list(range(50)),
                "b": list(range(50)),
                "c": list(range(50)),
            }
        )
        with pytest.raises(ValueError, match="limit"):
            list(expand_templates({"path": "${a}${b}${c}"}, spec))


# ──────────────────────────────────────────────────────────────────────────────
# expand_name_patterns Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestExpandNamePatterns:
    """Tests for bracket expansion in group names."""

    def test_no_brackets_returns_unchanged(self) -> None:
        """Name without brackets returns as single-item list."""
        assert expand_name_patterns("simple") == ["simple"]

    def test_single_range(self) -> None:
        """Single range bracket expands."""
        assert expand_name_patterns("node[1-3]") == ["node1", "node2", "node3"]

    def test_single_list(self) -> None:
        """Single list bracket expands."""
        assert expand_name_patterns("dc[a,b,c]") == ["dca", "dcb", "dcc"]

    def test_mixed_range_and_list(self) -> None:
        """Mixed range and list in single bracket."""
        result = expand_name_patterns("node[1,3,5-7]")
        assert result == ["node1", "node3", "node5", "node6", "node7"]

    def test_multiple_brackets_cartesian(self) -> None:
        """Multiple brackets create cartesian product."""
        result = expand_name_patterns("dc[1-2]_rack[a,b]")
        assert sorted(result) == sorted(
            ["dc1_racka", "dc1_rackb", "dc2_racka", "dc2_rackb"]
        )

    def test_three_brackets(self) -> None:
        """Three brackets create full cartesian product."""
        result = expand_name_patterns("a[1-2]b[3-4]c[5-6]")
        assert len(result) == 8  # 2 * 2 * 2

    def test_brackets_at_start(self) -> None:
        """Brackets at start of name."""
        assert expand_name_patterns("[a,b]suffix") == ["asuffix", "bsuffix"]

    def test_brackets_at_end(self) -> None:
        """Brackets at end of name."""
        assert expand_name_patterns("prefix[1-2]") == ["prefix1", "prefix2"]

    def test_adjacent_brackets(self) -> None:
        """Adjacent brackets expand correctly."""
        result = expand_name_patterns("[a,b][1-2]")
        assert sorted(result) == sorted(["a1", "a2", "b1", "b2"])

    def test_single_value_range(self) -> None:
        """Single value range [n-n] produces one result."""
        assert expand_name_patterns("node[5-5]") == ["node5"]

    def test_single_value_list(self) -> None:
        """Single value list [x] produces one result."""
        assert expand_name_patterns("node[x]") == ["nodex"]


class TestExpandNamePatternsEdgeCases:
    """Edge case tests for bracket expansion validation."""

    def test_alphabetic_range_raises_clear_error(self) -> None:
        """Alphabetic range [a-c] raises ValueError with helpful message."""
        with pytest.raises(ValueError) as exc_info:
            expand_name_patterns("node[a-c]")

        error_msg = str(exc_info.value)
        assert "not numeric" in error_msg
        assert "a" in error_msg  # Shows the problematic value
        assert "comma-separated" in error_msg.lower()  # Suggests alternative

    def test_alphabetic_range_end_raises_clear_error(self) -> None:
        """Range with numeric start but alphabetic end raises clear error."""
        with pytest.raises(ValueError) as exc_info:
            expand_name_patterns("node[1-z]")

        error_msg = str(exc_info.value)
        assert "not numeric" in error_msg
        assert "z" in error_msg

    def test_inverted_range_raises_clear_error(self) -> None:
        """Inverted range [5-3] raises ValueError with helpful message."""
        with pytest.raises(ValueError) as exc_info:
            expand_name_patterns("node[5-3]")

        error_msg = str(exc_info.value)
        assert "5" in error_msg and "3" in error_msg
        assert "greater" in error_msg.lower()
        assert "ascending" in error_msg.lower()

    def test_inverted_range_single_step(self) -> None:
        """Inverted range [2-1] raises error even for single step."""
        with pytest.raises(ValueError) as exc_info:
            expand_name_patterns("dc[2-1]")

        assert "greater" in str(exc_info.value).lower()

    def test_mixed_valid_and_invalid_range(self) -> None:
        """Mixed valid list and invalid range raises error on the range."""
        with pytest.raises(ValueError) as exc_info:
            expand_name_patterns("node[1,2,a-c]")

        error_msg = str(exc_info.value)
        assert "a-c" in error_msg

    def test_alphabetic_list_still_works(self) -> None:
        """Comma-separated alphabetic values still work correctly."""
        # This should work (list syntax, not range syntax)
        result = expand_name_patterns("node[a,b,c]")
        assert result == ["nodea", "nodeb", "nodec"]

    def test_zero_start_range_works(self) -> None:
        """Range starting at zero works correctly."""
        result = expand_name_patterns("node[0-2]")
        assert result == ["node0", "node1", "node2"]

    def test_leading_zeros_preserved(self) -> None:
        """Leading zeros in list values are preserved."""
        result = expand_name_patterns("port[01,02,03]")
        assert result == ["port01", "port02", "port03"]


# ──────────────────────────────────────────────────────────────────────────────
# expand_risk_group_refs Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestExpandRiskGroupRefs:
    """Tests for bracket expansion in risk group reference lists."""

    def test_no_brackets_passthrough(self) -> None:
        """List without brackets returns unchanged as set."""
        assert expand_risk_group_refs(["RG1"]) == {"RG1"}

    def test_multiple_literals(self) -> None:
        """Multiple literal names return as set."""
        assert expand_risk_group_refs(["RG1", "RG2", "RG3"]) == {"RG1", "RG2", "RG3"}

    def test_single_pattern(self) -> None:
        """Single pattern expands to multiple risk groups."""
        assert expand_risk_group_refs(["RG[1-3]"]) == {"RG1", "RG2", "RG3"}

    def test_multiple_patterns(self) -> None:
        """Multiple patterns expand independently."""
        result = expand_risk_group_refs(["A[1-2]", "B[a,b]"])
        assert result == {"A1", "A2", "Ba", "Bb"}

    def test_mixed_literal_and_pattern(self) -> None:
        """Mix of literal and pattern names."""
        result = expand_risk_group_refs(["Literal", "Pattern[1-2]"])
        assert result == {"Literal", "Pattern1", "Pattern2"}

    def test_empty_list(self) -> None:
        """Empty list returns empty set."""
        assert expand_risk_group_refs([]) == set()

    def test_cartesian_in_single_entry(self) -> None:
        """Multiple brackets in single entry create cartesian product."""
        result = expand_risk_group_refs(["DC[1-2]_Rack[a,b]"])
        assert result == {"DC1_Racka", "DC1_Rackb", "DC2_Racka", "DC2_Rackb"}

    def test_set_input(self) -> None:
        """Accepts set as input (not just list)."""
        result = expand_risk_group_refs({"RG[1-2]"})
        assert result == {"RG1", "RG2"}

    def test_duplicates_deduplicated(self) -> None:
        """Duplicate results are deduplicated."""
        # Two patterns that produce overlapping results
        result = expand_risk_group_refs(["RG[1-2]", "RG[2-3]"])
        assert result == {"RG1", "RG2", "RG3"}
