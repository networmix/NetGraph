from unittest.mock import MagicMock

import pytest

from ngraph.scenario import Scenario
from ngraph.workflow.base import (
    WORKFLOW_STEP_REGISTRY,
    WorkflowStep,
    register_workflow_step,
)


def test_workflow_step_is_abstract() -> None:
    """
    Verify that WorkflowStep is an abstract class and cannot be instantiated directly.
    """
    with pytest.raises(TypeError) as exc_info:
        WorkflowStep()  # type: ignore
    assert "abstract class" in str(exc_info.value)


def test_register_workflow_step_decorator() -> None:
    """
    Verify that using the @register_workflow_step decorator registers
    the subclass in the WORKFLOW_STEP_REGISTRY with the correct key.
    """

    @register_workflow_step("TestStep")
    class TestStep(WorkflowStep):
        def run(self, scenario) -> None:
            pass

    # Check if the class is registered correctly
    assert "TestStep" in WORKFLOW_STEP_REGISTRY
    assert WORKFLOW_STEP_REGISTRY["TestStep"] == TestStep


def test_workflow_step_subclass_run_method() -> None:
    """
    Verify that a concrete subclass of WorkflowStep can implement and call the run() method.
    """

    class ConcreteStep(WorkflowStep):
        def run(self, scenario) -> None:
            # Set a flag on the step instance to confirm invocation
            self._ran = True

    mock_scenario = MagicMock(spec=Scenario)
    step_instance = ConcreteStep(name="test_step")
    step_instance.run(mock_scenario)

    # Check if run() was actually invoked
    assert getattr(step_instance, "_ran", False) is True
    assert step_instance.name == "test_step"


def test_execute_records_metadata_including_seed_fields() -> None:
    """Execute a minimal step and verify metadata includes seed fields."""
    from ngraph.results import Results

    class Dummy(WorkflowStep):
        def run(self, scenario) -> None:
            scenario.results.put("metadata", {"ok": True})

    scen = MagicMock(spec=Scenario)
    scen.results = Results()
    scen.seed = 1010
    step = Dummy(name="d1")
    step.execute(scen)

    md = scen.results.get_step_metadata("d1")
    assert md is not None
    assert md.step_type == "Dummy"
    assert md.step_name == "d1"
    assert isinstance(md.execution_order, int) and md.execution_order >= 0
    # Seed fields
    assert hasattr(md, "scenario_seed") and md.scenario_seed == 1010
    assert hasattr(md, "step_seed")
    assert hasattr(md, "seed_source")
