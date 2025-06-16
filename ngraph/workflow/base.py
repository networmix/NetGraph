"""Base classes and utilities for workflow components."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Type

from ngraph.logging import get_logger

if TYPE_CHECKING:
    # Only imported for type-checking; not at runtime, so no circular import occurs.
    from ngraph.scenario import Scenario

logger = get_logger(__name__)

WORKFLOW_STEP_REGISTRY: Dict[str, Type["WorkflowStep"]] = {}


def register_workflow_step(step_type: str):
    """A decorator that registers a WorkflowStep subclass under `step_type`."""

    def decorator(cls: Type["WorkflowStep"]):
        WORKFLOW_STEP_REGISTRY[step_type] = cls
        return cls

    return decorator


@dataclass
class WorkflowStep(ABC):
    """Base class for all workflow steps.

    All workflow steps are automatically logged with execution timing information.

    YAML Configuration:
        ```yaml
        workflow:
          - step_type: <StepTypeName>
            name: "optional_step_name"  # Optional: Custom name for this step instance
            # ... step-specific parameters ...
        ```

    Attributes:
        name: Optional custom identifier for this workflow step instance,
            used for logging and result storage purposes.
    """

    name: str = ""

    def execute(self, scenario: "Scenario") -> None:
        """Execute the workflow step with automatic logging.

        This method wraps the abstract run() method with timing and logging.

        Args:
            scenario: The scenario to execute the step on.
        """
        step_type = self.__class__.__name__
        step_name = self.name or step_type

        logger.info(f"Starting workflow step: {step_name} ({step_type})")
        start_time = time.time()

        try:
            self.run(scenario)
            end_time = time.time()
            duration = end_time - start_time
            logger.info(
                f"Completed workflow step: {step_name} ({step_type}) "
                f"in {duration:.3f} seconds"
            )
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(
                f"Failed workflow step: {step_name} ({step_type}) "
                f"after {duration:.3f} seconds - {type(e).__name__}: {e}"
            )
            raise

    @abstractmethod
    def run(self, scenario: "Scenario") -> None:
        """Execute the workflow step logic.

        This method should be implemented by concrete workflow step classes.
        It is called by execute() which handles logging and timing.

        Args:
            scenario: The scenario to execute the step on.
        """
        pass
