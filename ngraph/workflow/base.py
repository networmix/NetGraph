from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    # Only imported for type-checking; not at runtime, so no circular import occurs.
    from ngraph.scenario import Scenario

WORKFLOW_STEP_REGISTRY: Dict[str, Type["WorkflowStep"]] = {}


def register_workflow_step(step_type: str):
    """
    A decorator that registers a WorkflowStep subclass under `step_type`.
    """

    def decorator(cls: Type["WorkflowStep"]):
        WORKFLOW_STEP_REGISTRY[step_type] = cls
        return cls

    return decorator


@dataclass
class WorkflowStep(ABC):
    """
    Base class for all workflow steps.
    """

    name: str = ""

    @abstractmethod
    def run(self, scenario: Scenario) -> None:
        """
        Execute the workflow step logic.
        """
        pass
