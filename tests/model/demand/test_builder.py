"""Tests for traffic matrix set builder."""

import pytest

from ngraph.model.demand.builder import (
    _coerce_flow_policy,
    build_demand_set,
)
from ngraph.model.flow.policy_config import FlowPolicyPreset


def test_build_demand_set_basic():
    """Test building a basic traffic matrix set."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
            }
        ]
    }

    tms = build_demand_set(raw)
    assert "tm1" in tms.sets
    demands = tms.get_set("tm1")
    assert len(demands) == 1
    assert demands[0].source == "A"
    assert demands[0].target == "B"
    assert demands[0].volume == 100.0


def test_build_demand_set_multiple_matrices():
    """Test building multiple traffic matrices."""
    raw = {
        "tm1": [{"source": "A", "target": "B", "volume": 100.0}],
        "tm2": [{"source": "C", "target": "D", "volume": 200.0}],
    }

    tms = build_demand_set(raw)
    assert "tm1" in tms.sets
    assert "tm2" in tms.sets
    assert len(tms.get_set("tm1")) == 1
    assert len(tms.get_set("tm2")) == 1


def test_build_demand_set_multiple_demands():
    """Test building traffic matrix with multiple demands."""
    raw = {
        "tm1": [
            {"source": "A", "target": "B", "volume": 100.0},
            {"source": "C", "target": "D", "volume": 200.0},
        ]
    }

    tms = build_demand_set(raw)
    demands = tms.get_set("tm1")
    assert len(demands) == 2
    assert demands[0].volume == 100.0
    assert demands[1].volume == 200.0


def test_build_demand_set_with_flow_policy_enum():
    """Test building with FlowPolicyPreset enum."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "flow_policy": FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            }
        ]
    }

    tms = build_demand_set(raw)
    demands = tms.get_set("tm1")
    assert demands[0].flow_policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_build_demand_set_with_flow_policy_string():
    """Test building with FlowPolicyPreset as string."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "flow_policy": "SHORTEST_PATHS_ECMP",
            }
        ]
    }

    tms = build_demand_set(raw)
    demands = tms.get_set("tm1")
    assert demands[0].flow_policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_build_demand_set_with_flow_policy_int():
    """Test building with FlowPolicyPreset as integer."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "flow_policy": 1,
            }
        ]
    }

    tms = build_demand_set(raw)
    demands = tms.get_set("tm1")
    assert demands[0].flow_policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_build_demand_set_invalid_raw_type():
    """Test error handling for invalid raw type."""
    with pytest.raises(ValueError, match="must be a mapping"):
        build_demand_set("not a dict")

    with pytest.raises(ValueError, match="must be a mapping"):
        build_demand_set([])


def test_build_demand_set_invalid_matrix_value():
    """Test error handling when matrix value is not a list."""
    raw = {"tm1": "not a list"}

    with pytest.raises(ValueError, match="must map to a list"):
        build_demand_set(raw)


def test_build_demand_set_invalid_demand_type():
    """Test error handling when demand entry is not a dict."""
    raw = {"tm1": ["not a dict"]}

    with pytest.raises(ValueError, match="must be dicts"):
        build_demand_set(raw)


def test_coerce_flow_policy_none():
    """Test coercing None."""
    assert _coerce_flow_policy(None) is None


def test_coerce_flow_policy_enum():
    """Test coercing FlowPolicyPreset enum."""
    preset = FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert _coerce_flow_policy(preset) == preset


def test_coerce_flow_policy_int():
    """Test coercing integer to enum."""
    assert _coerce_flow_policy(1) == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert _coerce_flow_policy(2) == FlowPolicyPreset.SHORTEST_PATHS_WCMP
    assert _coerce_flow_policy(3) == FlowPolicyPreset.TE_WCMP_UNLIM
    assert _coerce_flow_policy(4) == FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP
    assert _coerce_flow_policy(5) == FlowPolicyPreset.TE_ECMP_16_LSP


def test_coerce_flow_policy_string():
    """Test coercing string to enum."""
    assert (
        _coerce_flow_policy("SHORTEST_PATHS_ECMP")
        == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy("shortest_paths_ecmp")
        == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy("SHORTEST_PATHS_WCMP")
        == FlowPolicyPreset.SHORTEST_PATHS_WCMP
    )
    assert _coerce_flow_policy("TE_WCMP_UNLIM") == FlowPolicyPreset.TE_WCMP_UNLIM
    assert (
        _coerce_flow_policy("TE_ECMP_UP_TO_256_LSP")
        == FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP
    )
    assert _coerce_flow_policy("TE_ECMP_16_LSP") == FlowPolicyPreset.TE_ECMP_16_LSP


def test_coerce_flow_policy_string_numeric():
    """Test coercing numeric string to enum."""
    assert _coerce_flow_policy("1") == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert _coerce_flow_policy("2") == FlowPolicyPreset.SHORTEST_PATHS_WCMP
    assert _coerce_flow_policy("3") == FlowPolicyPreset.TE_WCMP_UNLIM


def test_coerce_flow_policy_empty_string():
    """Test coercing empty string."""
    assert _coerce_flow_policy("") is None
    assert _coerce_flow_policy("   ") is None


def test_coerce_flow_policy_invalid_string():
    """Test error handling for invalid string."""
    with pytest.raises(ValueError, match="Unknown flow policy"):
        _coerce_flow_policy("INVALID_POLICY")


def test_coerce_flow_policy_invalid_numeric_string():
    """Test error handling for invalid numeric string."""
    with pytest.raises(ValueError, match="Unknown flow policy value"):
        _coerce_flow_policy("999")


def test_coerce_flow_policy_invalid_int():
    """Test error handling for invalid integer."""
    with pytest.raises(ValueError, match="Unknown flow policy value"):
        _coerce_flow_policy(999)


def test_coerce_flow_policy_other_types():
    """Test that other types are passed through unchanged."""
    # Dict config for advanced usage
    dict_config = {"custom": "config"}
    assert _coerce_flow_policy(dict_config) == dict_config

    # List (unusual but should pass through)
    list_config = ["a", "b"]
    assert _coerce_flow_policy(list_config) == list_config
