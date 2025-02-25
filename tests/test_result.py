import pytest
from ngraph.results import Results


def test_put_and_get():
    """
    Test that putting a value in the store and then getting it works as expected.
    """
    results = Results()
    results.put("Step1", "total_capacity", 123.45)
    assert results.get("Step1", "total_capacity") == 123.45


def test_get_with_default_missing_key():
    """
    Test retrieving a non-existent key with a default value.
    """
    results = Results()
    default_value = "not found"
    assert results.get("StepX", "unknown_key", default_value) == default_value


def test_get_with_default_missing_step():
    """
    Test retrieving from a non-existent step with a default value.
    """
    results = Results()
    results.put("Step1", "some_key", 42)
    default_value = "missing step"
    assert results.get("Step2", "some_key", default_value) == default_value


def test_get_all_single_key_multiple_steps():
    """
    Test retrieving all values for a single key across multiple steps.
    """
    results = Results()
    results.put("Step1", "duration", 5.5)
    results.put("Step2", "duration", 3.2)
    results.put("Step2", "other_key", "unused")
    results.put("Step3", "different_key", 99)

    durations = results.get_all("duration")
    assert durations == {"Step1": 5.5, "Step2": 3.2}

    # No 'duration' key in Step3, so it won't appear in durations
    assert "Step3" not in durations


def test_overwriting_value():
    """
    Test that storing a new value under an existing step/key pair overwrites the old value.
    """
    results = Results()
    results.put("Step1", "cost", 10)
    assert results.get("Step1", "cost") == 10

    # Overwrite
    results.put("Step1", "cost", 20)
    assert results.get("Step1", "cost") == 20


def test_empty_results():
    """
    Test that a newly instantiated Results object does not have any stored data.
    """
    results = Results()
    assert results.get("StepX", "keyX") is None
    assert results.get_all("keyX") == {}
