"""Regression tests for Results.to_dict deep conversion.

Covers recursion into ``to_dict()`` output and conversion of the scenario
snapshot section, which previously escaped JSON-safe normalization.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from ngraph.results import Results
from ngraph.results.artifacts import CapacityEnvelope


class _Inner:
    def to_dict(self) -> Dict[Any, Any]:
        return {2.5: ("a", "b")}


class _Outer:
    def to_dict(self) -> Dict[Any, Any]:
        # Float keys, a tuple, and a nested convertible object
        return {1.5: 2, "nested": _Inner(), "items": (1, 2)}


def test_to_dict_recurses_into_to_dict_output() -> None:
    results = Results()
    results.put_step_metadata("s1", "Dummy", 0)
    results.enter_step("s1")
    results.put("metadata", {})
    results.put("data", {"obj": _Outer()})
    results.exit_step()

    exported = results.to_dict()
    obj = exported["steps"]["s1"]["data"]["obj"]
    assert obj == {"1.5": 2, "nested": {"2.5": ["a", "b"]}, "items": [1, 2]}
    # The whole document must be JSON-serializable without fallbacks
    json.dumps(exported)


def test_to_dict_converts_capacity_envelope_frequencies_keys() -> None:
    results = Results()
    results.put_step_metadata("s1", "Dummy", 0)
    results.enter_step("s1")
    results.put("metadata", {})
    env = CapacityEnvelope.from_values("^A$", "^B$", "combine", [10.0, 10.0, 20.0])
    results.put("data", {"envelope": env})
    results.exit_step()

    exported = results.to_dict()
    freqs = exported["steps"]["s1"]["data"]["envelope"]["frequencies"]
    assert all(isinstance(k, str) for k in freqs)
    assert freqs["10.0"] == 2
    assert freqs["20.0"] == 1
    json.dumps(exported)


def test_to_dict_converts_scenario_snapshot() -> None:
    results = Results()
    results.set_scenario_snapshot({"meta": {1: (1, 2)}, "name": "demo"})

    exported = results.to_dict()
    assert exported["scenario"] == {"meta": {"1": [1, 2]}, "name": "demo"}
    json.dumps(exported)
