from __future__ import annotations

import pytest

from ngraph.results.store import Results


def _sample_results_doc() -> dict:
    r = Results()
    r.enter_step("s1")
    r.put("metadata", {"a": 1})
    r.put("data", {"x": 2})
    r.exit_step()
    r.put_step_metadata(
        step_name="s1",
        step_type="ExampleStep",
        execution_order=0,
        scenario_seed=123,
        step_seed=None,
        seed_source="scenario-derived",
        active_seed=123,
    )
    r.set_scenario_snapshot({"name": "demo"})
    return r.to_dict()


def test_results_to_dict_shape_and_conversion() -> None:
    doc = _sample_results_doc()
    assert set(doc.keys()) >= {"workflow", "steps", "scenario"}
    assert doc["workflow"]["s1"]["step_type"] == "ExampleStep"
    assert doc["steps"]["s1"]["metadata"]["a"] == 1
    assert doc["steps"]["s1"]["data"]["x"] == 2


def test_results_scope_and_key_validation() -> None:
    r = Results()
    with pytest.raises(RuntimeError):
        r.put("metadata", {})
    r.enter_step("s1")
    with pytest.raises(ValueError):
        r.put("invalid", {})  # type: ignore[arg-type]
    r.put("metadata", {})
    r.put("data", {})
    r.exit_step()

    # Inject an invalid key via internal dict to test export validation path
    r._store["s1"]["bad"] = 42  # type: ignore[index]
    with pytest.raises(ValueError):
        r.to_dict()
