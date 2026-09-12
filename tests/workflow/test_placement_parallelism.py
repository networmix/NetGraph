"""resolve_placement_parallelism: 'auto' means threads only where they help."""

from __future__ import annotations

import os

import pytest

from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.workflow import traffic_matrix_placement_step as tm
from ngraph.workflow.traffic_matrix_placement_step import resolve_placement_parallelism


def _td(preset):
    return TrafficDemand(source="A", target="B", volume=1.0, flow_policy=preset)


@pytest.fixture(autouse=True)
def gil_interpreter(monkeypatch):
    monkeypatch.setattr(tm, "_python_is_free_threaded", lambda: False)


def test_explicit_worker_count_is_honoured():
    assert (
        resolve_placement_parallelism(4, [_td(FlowPolicyPreset.SHORTEST_PATHS_ECMP)])
        == 4
    )
    assert resolve_placement_parallelism(1, [_td(FlowPolicyPreset.TE_ECMP_16_LSP)]) == 1


@pytest.mark.parametrize(
    "preset",
    [
        None,  # default preset is SHORTEST_PATHS_ECMP
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
        FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
        FlowPolicyPreset.TE_WCMP_UNLIM,
    ],
)
def test_auto_is_serial_for_cacheable_presets(preset):
    assert resolve_placement_parallelism("auto", [_td(preset)]) == 1


@pytest.mark.parametrize(
    "preset", [FlowPolicyPreset.TE_ECMP_16_LSP, FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP]
)
def test_auto_uses_cpu_count_for_engine_bound_presets(preset):
    demands = [_td(FlowPolicyPreset.SHORTEST_PATHS_ECMP), _td(preset)]
    assert resolve_placement_parallelism("auto", demands) == max(1, os.cpu_count() or 1)


def test_auto_uses_cpu_count_when_free_threaded(monkeypatch):
    monkeypatch.setattr(tm, "_python_is_free_threaded", lambda: True)
    demands = [_td(FlowPolicyPreset.SHORTEST_PATHS_ECMP)]
    assert resolve_placement_parallelism("auto", demands) == max(1, os.cpu_count() or 1)


def test_invalid_values_still_raise():
    with pytest.raises(ValueError):
        resolve_placement_parallelism("many", [])
    with pytest.raises(ValueError):
        resolve_placement_parallelism(0, [])
