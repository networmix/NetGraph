from __future__ import annotations

import pytest

from ngraph.demand.manager.builder import (
    _coerce_flow_policy_config,
    build_traffic_matrix_set,
)
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.flows.policy import FlowPolicyConfig


def test_coerce_flow_policy_config_variants() -> None:
    assert _coerce_flow_policy_config(None) is None
    assert (
        _coerce_flow_policy_config(FlowPolicyConfig.SHORTEST_PATHS_ECMP)
        == FlowPolicyConfig.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy_config(int(FlowPolicyConfig.SHORTEST_PATHS_ECMP))
        == FlowPolicyConfig.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy_config(str(int(FlowPolicyConfig.SHORTEST_PATHS_ECMP)))
        == FlowPolicyConfig.SHORTEST_PATHS_ECMP
    )
    assert (
        _coerce_flow_policy_config("shortest_paths_ecmp")
        == FlowPolicyConfig.SHORTEST_PATHS_ECMP
    )
    with pytest.raises(ValueError):
        _coerce_flow_policy_config("not-an-enum")


def test_build_traffic_matrix_set_happy_and_errors() -> None:
    raw = {
        "default": [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 10.0,
                "priority": 0,
                "flow_policy_config": "shortest_paths_ecmp",
            }
        ]
    }
    tms = build_traffic_matrix_set(raw)
    assert isinstance(tms, TrafficMatrixSet)
    m = tms.get_default_matrix()
    assert m[0].flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_ECMP

    with pytest.raises(ValueError):
        build_traffic_matrix_set([1, 2, 3])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        build_traffic_matrix_set({"x": 1})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        build_traffic_matrix_set({"x": [1]})  # type: ignore[arg-type]
