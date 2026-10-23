import pytest

from ngraph import Network, StepContext, StepOutput
from ngraph.scenario import Scenario, prepare, run
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
    the subclass in the WORKFLOW_STEP_REGISTRY under the decorator's key.
    """

    @register_workflow_step("TestStep")
    class TestStep(WorkflowStep):
        def run(self, context: StepContext) -> StepOutput:
            return StepOutput({}, {})

    assert "TestStep" in WORKFLOW_STEP_REGISTRY
    assert WORKFLOW_STEP_REGISTRY["TestStep"] == TestStep


def test_workflow_step_subclass_run_method() -> None:
    """
    Verify that a concrete subclass of WorkflowStep can implement and call the run() method.
    """

    class ConcreteStep(WorkflowStep):
        def run(self, context: StepContext) -> StepOutput:
            # Set a flag on the step instance to confirm invocation
            self._ran = True
            return StepOutput({}, {"ran": True})

    step_instance = ConcreteStep(name="test_step")
    context = StepContext(
        prepare(Scenario(Network())), {}, "test_step", 0, None, "none"
    )
    output = step_instance.run(context)
    assert output.result == {"ran": True}

    assert getattr(step_instance, "_ran", False) is True
    assert step_instance.name == "test_step"


def test_execute_records_metadata_including_seed_fields() -> None:
    """Execute a minimal step and verify metadata includes seed fields."""

    class Dummy(WorkflowStep):
        def run(self, context: StepContext) -> StepOutput:
            return StepOutput({"operation": "dummy"}, {"ok": True})

    step = Dummy(name="d1")
    md = run(prepare(Scenario(Network(), (step,), seed=1010))).steps[0]
    assert md.step_type == "Dummy"
    assert md.name == "d1" and md.execution_order == 0
    # Seed fields
    assert (
        md.scenario_seed == 1010 and md.step_seed is None and md.seed_source == "none"
    )
    explicit = run(
        prepare(Scenario(Network(), (Dummy(name="d2", seed=42),), seed=1010))
    ).steps[0]
    assert explicit.step_seed == 42 and explicit.seed_source == "explicit-step"
    assert md.result == {"ok": True}
