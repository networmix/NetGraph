"""Tests for traffic matrix set builder."""

import pytest

from ngraph.exec.demand.builder import (
    _coerce_flow_policy_config,
    build_traffic_matrix_set,
)
from ngraph.model.flow.policy_config import FlowPolicyPreset


def test_build_traffic_matrix_set_basic():
    """Test building a basic traffic matrix set."""
    raw = {
        "tm1": [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 100.0,
            }
        ]
    }

    tms = build_traffic_matrix_set(raw)
    assert "tm1" in tms.matrices
    demands = tms.get_matrix("tm1")
    assert len(demands) == 1
    assert demands[0].source_path == "A"
    assert demands[0].sink_path == "B"
    assert demands[0].demand == 100.0


def test_build_traffic_matrix_set_multiple_matrices():
    """Test building multiple traffic matrices."""
    raw = {
        "tm1": [{"source_path": "A", "sink_path": "B", "demand": 100.0}],
        "tm2": [{"source_path": "C", "sink_path": "D", "demand": 200.0}],
    }

    tms = build_traffic_matrix_set(raw)
    assert "tm1" in tms.matrices
    assert "tm2" in tms.matrices
    assert len(tms.get_matrix("tm1")) == 1
    assert len(tms.get_matrix("tm2")) == 1


def test_build_traffic_matrix_set_multiple_demands():
    """Test building traffic matrix with multiple demands."""
    raw = {
        "tm1": [
            {"source_path": "A", "sink_path": "B", "demand": 100.0},
            {"source_path": "C", "sink_path": "D", "demand": 200.0},
        ]
    }

    tms = build_traffic_matrix_set(raw)
    demands = tms.get_matrix("tm1")
    assert len(demands) == 2
    assert demands[0].demand == 100.0
    assert demands[1].demand == 200.0


def test_build_traffic_matrix_set_with_flow_policy_enum():
    """Test building with FlowPolicyPreset enum."""
    raw = {
        "tm1": [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 100.0,
                "flow_policy_config": FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            }
        ]
    }

    tms = build_traffic_matrix_set(raw)
    demands = tms.get_matrix("tm1")
    assert demands[0].flow_policy_config == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_build_traffic_matrix_set_with_flow_policy_string():
    """Test building with FlowPolicyPreset as string."""
    raw = {
        "tm1": [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 100.0,
                "flow_policy_config": "SHORTEST_PATHS_ECMP",
            }
        ]
    }

    tms = build_traffic_matrix_set(raw)
    demands = tms.get_matrix("tm1")
    assert demands[0].flow_policy_config == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_build_traffic_matrix_set_with_flow_policy_int():
    """Test building with FlowPolicyPreset as integer."""
    raw = {
        "tm1": [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 100.0,
                "flow_policy_config": 1,
            }
        ]
    }

    tms = build_traffic_matrix_set(raw)
    demands = tms.get_matrix("tm1")
    assert demands[0].flow_policy_config == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_build_traffic_matrix_set_invalid_raw_type():
    """Test error handling for invalid raw type."""
    with pytest.raises(ValueError, match="must be a mapping"):
        build_traffic_matrix_set("not a dict")

    with pytest.raises(ValueError, match="must be a mapping"):
        build_traffic_matrix_set([])


def test_build_traffic_matrix_set_invalid_matrix_value():
    """Test error handling when matrix value is not a list."""
    raw = {"tm1": "not a list"}

    with pytest.raises(ValueError, match="must map to a list"):
        build_traffic_matrix_set(raw)


def test_build_traffic_matrix_set_invalid_demand_type():
    """Test error handling when demand entry is not a dict."""
    raw = {"tm1": ["not a dict"]}

    with pytest.raises(ValueError, match="must be dicts"):
        build_traffic_matrix_set(raw)


def test_coerce_flow_policy_config_none():
    """Test coercing None."""
    assert _coerce_flow_policy_config(None) is None


def test_coerce_flow_policy_config_enum():
    """Test coercing FlowPolicyPreset enum."""
    preset = FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert _coerce_flow_policy_config(preset) == preset


def test_coerce_flow_policy_config_int():
    """Test coercing integer to enum."""
    assert _coerce_flow_policy_config(1) == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert _coerce_flow_policy_config(2) == FlowPolicyPreset.SHORTEST_PATHS_WCMP
    assert _coerce_flow_policy_config(3) == FlowPolicyPreset.TE_WCMP_UNLIM
    assert _coerce_flow_policy_config(4) == FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP
    assert _coerce_flow_policy_config(5) == FlowPolicyPreset.TE_ECMP_16_LSP


def test_coerce_flow_policy_config_string():
    """Test coercing string to enum."""
    assert (
        _coerce_flow_policy_config("SHORTEST_PATHS_ECMP")
        == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy_config("shortest_paths_ecmp")
        == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy_config("SHORTEST_PATHS_WCMP")
        == FlowPolicyPreset.SHORTEST_PATHS_WCMP
    )
    assert _coerce_flow_policy_config("TE_WCMP_UNLIM") == FlowPolicyPreset.TE_WCMP_UNLIM
    assert (
        _coerce_flow_policy_config("TE_ECMP_UP_TO_256_LSP")
        == FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP
    )
    assert (
        _coerce_flow_policy_config("TE_ECMP_16_LSP") == FlowPolicyPreset.TE_ECMP_16_LSP
    )


def test_coerce_flow_policy_config_string_numeric():
    """Test coercing numeric string to enum."""
    assert _coerce_flow_policy_config("1") == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert _coerce_flow_policy_config("2") == FlowPolicyPreset.SHORTEST_PATHS_WCMP
    assert _coerce_flow_policy_config("3") == FlowPolicyPreset.TE_WCMP_UNLIM


def test_coerce_flow_policy_config_empty_string():
    """Test coercing empty string."""
    assert _coerce_flow_policy_config("") is None
    assert _coerce_flow_policy_config("   ") is None


def test_coerce_flow_policy_config_invalid_string():
    """Test error handling for invalid string."""
    with pytest.raises(ValueError, match="Unknown flow policy config"):
        _coerce_flow_policy_config("INVALID_POLICY")


def test_coerce_flow_policy_config_invalid_numeric_string():
    """Test error handling for invalid numeric string."""
    with pytest.raises(ValueError, match="Unknown flow policy config value"):
        _coerce_flow_policy_config("999")


def test_coerce_flow_policy_config_invalid_int():
    """Test error handling for invalid integer."""
    with pytest.raises(ValueError, match="Unknown flow policy config value"):
        _coerce_flow_policy_config(999)


def test_coerce_flow_policy_config_other_types():
    """Test that other types are passed through unchanged."""
    # Dict config for advanced usage
    dict_config = {"custom": "config"}
    assert _coerce_flow_policy_config(dict_config) == dict_config

    # List (unusual but should pass through)
    list_config = ["a", "b"]
    assert _coerce_flow_policy_config(list_config) == list_config
