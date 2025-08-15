from ngraph.results import Results
from ngraph.results.artifacts import FailurePatternResult


def test_put_and_get():
    """
    Validate step-scoped put/get via exported dict structure.
    """
    results = Results()
    results.put_step_metadata("Step1", "Dummy", 0)
    results.enter_step("Step1")
    results.put("metadata", {})
    results.put("data", {"total_capacity": 123.45})
    results.exit_step()

    exported = results.to_dict()
    assert exported["steps"]["Step1"]["data"]["total_capacity"] == 123.45


def test_get_with_default_missing_key():
    """
    Validate exported dict absence.
    """
    results = Results()
    results.put_step_metadata("StepX", "Dummy", 0)
    exported = results.to_dict()
    assert "StepX" not in exported.get("steps", {})


def test_get_with_default_missing_step():
    """
    Validate absence of a non-existent step in exported dict.
    """
    results = Results()
    results.put_step_metadata("Step1", "Dummy", 0)
    results.enter_step("Step1")
    results.put("metadata", {})
    results.put("data", {"some_key": 42})
    results.exit_step()

    exported = results.to_dict()
    assert "Step2" not in exported.get("steps", {})


def test_get_all_single_key_multiple_steps():
    """
    Ensure both steps present under steps map.
    """
    results = Results()
    results.put_step_metadata("Step1", "Dummy", 0)
    results.enter_step("Step1")
    results.put("metadata", {})
    results.put("data", {"duration": 5.5})
    results.exit_step()

    results.put_step_metadata("Step2", "Dummy", 1)
    results.enter_step("Step2")
    results.put("metadata", {})
    results.put("data", {"duration": 3.2, "other_key": "unused"})
    results.exit_step()

    results.put_step_metadata("Step3", "Dummy", 2)
    results.enter_step("Step3")
    results.put("metadata", {})
    results.put("data", {"different_key": 99})
    results.exit_step()

    exported = results.to_dict()
    assert exported["steps"]["Step1"]["data"]["duration"] == 5.5
    assert exported["steps"]["Step2"]["data"]["duration"] == 3.2
    assert "duration" not in exported["steps"]["Step3"]["data"]


def test_overwriting_value():
    """
    Validate that subsequent puts overwrite previous entries within the step.
    """
    results = Results()
    results.put_step_metadata("Step1", "Dummy", 0)
    results.enter_step("Step1")
    results.put("metadata", {})
    results.put("data", {"cost": 10})
    results.put("data", {"cost": 20})
    results.exit_step()

    exported = results.to_dict()
    assert exported["steps"]["Step1"]["data"]["cost"] == 20


def test_empty_results():
    """
    Newly instantiated Results has empty steps/workflow maps.
    """
    results = Results()
    exported = results.to_dict()
    assert exported.get("steps", {}) == {}


def test_results_to_dict_includes_workflow_and_step_data():
    results = Results()
    # Simulate metadata
    results.put_step_metadata("stepA", "DummyStep", 0)
    results.enter_step("stepA")
    results.put("metadata", {})
    # Include an artifact object to confirm to_dict conversion
    fpr = FailurePatternResult(
        excluded_nodes=["n1"],
        excluded_links=["l1"],
        capacity_matrix={"A->B": 10.0},
        count=2,
    )
    results.put("data", {"pattern": fpr, "value": 1})
    results.exit_step()

    d = results.to_dict()
    assert "workflow" in d
    assert "stepA" in d["workflow"]
    assert d["steps"]["stepA"]["data"]["value"] == 1
    assert isinstance(d["steps"]["stepA"]["data"]["pattern"], dict)
