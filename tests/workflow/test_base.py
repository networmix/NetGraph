import pytest
from unittest.mock import MagicMock

from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    WORKFLOW_STEP_REGISTRY,
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
            scenario.called = True

    mock_scenario = MagicMock()
    step_instance = ConcreteStep(name="test_step")
    step_instance.run(mock_scenario)

    # Check if run() was actually invoked
    # e.g., we set scenario.called = True in run()
    # but here we can also rely on MagicMock calls or attributes if needed
    assert hasattr(mock_scenario, "called") and mock_scenario.called is True
    assert step_instance.name == "test_step"
