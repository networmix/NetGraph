"""The scenario demand parser produces typed sets with closed model inputs."""

import pytest

from ngraph.dsl.inputs import demand_sets
from ngraph.model.demand import FlowPolicyPreset


def test_demand_sets_basic():
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

    tms = demand_sets(raw)
    assert "tm1" in tms
    demands = tms["tm1"].demands
    assert len(demands) == 1
    assert demands[0].source.path == "A"
    assert demands[0].target.path == "B"
    assert demands[0].volume == 100.0


def test_demand_sets_multiple_matrices():
    """Test building multiple traffic matrices."""
    raw = {
        "tm1": [{"source": "A", "target": "B", "volume": 100.0}],
        "tm2": [{"source": "C", "target": "D", "volume": 200.0}],
    }

    tms = demand_sets(raw)
    assert "tm1" in tms
    assert "tm2" in tms
    assert len(tms["tm1"].demands) == 1
    assert len(tms["tm2"].demands) == 1


def test_demand_sets_multiple_demands():
    """Test building traffic matrix with multiple demands."""
    raw = {
        "tm1": [
            {"source": "A", "target": "B", "volume": 100.0},
            {"source": "C", "target": "D", "volume": 200.0},
        ]
    }

    tms = demand_sets(raw)
    demands = tms["tm1"].demands
    assert len(demands) == 2
    assert demands[0].volume == 100.0
    assert demands[1].volume == 200.0


def test_demand_sets_with_preset_enum():
    """Test building with FlowPolicyPreset enum."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "preset": FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            }
        ]
    }

    tms = demand_sets(raw)
    demands = tms["tm1"].demands
    assert demands[0].policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_demand_sets_with_preset_string():
    """Test building with FlowPolicyPreset as string."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "preset": "SHORTEST_PATHS_ECMP",
            }
        ]
    }

    tms = demand_sets(raw)
    demands = tms["tm1"].demands
    assert demands[0].policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP


def test_demand_sets_rejects_integer_preset():
    """Presets are named; integer values are not accepted."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "preset": 1,
            }
        ]
    }

    with pytest.raises(ValueError, match="preset: unknown preset"):
        demand_sets(raw)


def test_demand_sets_invalid_raw_type():
    """Test error handling for invalid raw type."""
    with pytest.raises(ValueError, match="expected mapping"):
        demand_sets("not a dict")

    with pytest.raises(ValueError, match="expected mapping"):
        demand_sets([])


def test_demand_sets_invalid_matrix_value():
    """Test error handling when matrix value is not a list."""
    raw = {"tm1": "not a list"}

    with pytest.raises(ValueError, match="expected list"):
        demand_sets(raw)


def test_demand_sets_invalid_demand_type():
    """Test error handling when demand entry is not a dict."""
    raw = {"tm1": ["not a dict"]}

    with pytest.raises(ValueError, match="expected mapping"):
        demand_sets(raw)


def test_demand_sets_rejects_inline_dict_preset():
    """Inline dict preset raises at build time, not deep in analysis."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "preset": {"path_alg": "SPF", "flow_placement": "PROPORTIONAL"},
            }
        ]
    }

    with pytest.raises(ValueError, match="preset: unknown preset"):
        demand_sets(raw)


def test_demand_sets_rejects_bool_preset():
    """Bool preset raises instead of coercing to SHORTEST_PATHS_ECMP."""
    raw = {
        "tm1": [
            {
                "source": "A",
                "target": "B",
                "volume": 100.0,
                "preset": True,
            }
        ]
    }

    with pytest.raises(ValueError, match="preset: unknown preset"):
        demand_sets(raw)


def test_demand_sets_rejects_unknown_keys() -> None:
    """A mistyped key (here 'demand' for 'volume') raises instead of volume 0."""
    raw = {"tm1": [{"source": "A", "target": "B", "demand": 5}]}
    with pytest.raises(ValueError, match=r"Unrecognized key.*demands.tm1\[0\]: demand"):
        demand_sets(raw)
