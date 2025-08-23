"""Base classes for workflow automation.

Defines the workflow step abstraction, registration decorator, and execution
wrapper that adds timing and logging. Steps implement `run()` and are executed
via `execute()` which records metadata and re-raises failures.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Optional, Type

from ngraph.logging import get_logger

if TYPE_CHECKING:
    # Only imported for type-checking; not at runtime, so no circular import occurs.
    from ngraph.scenario import Scenario

logger = get_logger(__name__)

# Registry for workflow step classes
WORKFLOW_STEP_REGISTRY: Dict[str, Type["WorkflowStep"]] = {}

# Global execution counter for tracking step order
_execution_counter = 0


def register_workflow_step(step_type: str):
    """Return a decorator that registers a `WorkflowStep` subclass.

    Args:
        step_type: Registry key used to instantiate steps from configuration.

    Returns:
        A class decorator that adds the class to `WORKFLOW_STEP_REGISTRY`.
    """

    def decorator(cls: Type["WorkflowStep"]) -> Type["WorkflowStep"]:
        WORKFLOW_STEP_REGISTRY[step_type] = cls
        return cls

    return decorator


@dataclass
class WorkflowStep(ABC):
    """Base class for all workflow steps.

    All workflow steps are automatically logged with execution timing information.
    All workflow steps support seeding for reproducible random operations.
    Workflow metadata is automatically stored in scenario.results for analysis.

    YAML Configuration:
        ```yaml
        workflow:
          - step_type: <StepTypeName>
            name: "optional_step_name"  # Optional: Custom name for this step instance
            seed: 42                    # Optional: Seed for reproducible random operations
            # ... step-specific parameters ...
        ```

    Attributes:
        name: Optional custom identifier for this workflow step instance,
            used for logging and result storage purposes.
        seed: Optional seed for reproducible random operations. If None,
            random operations will be non-deterministic.
    """

    name: str = ""
    seed: Optional[int] = None
    # Internal: provenance of the step seed ("explicit-step" or "scenario-derived" or "none").
    _seed_source: str = ""

    def execute(self, scenario: "Scenario") -> None:
        """Execute the workflow step with logging and metadata storage.

        This method wraps the abstract run() method with timing, logging, and
        automatic metadata storage for the analysis registry system.

        Args:
            scenario: The scenario to execute the step on.

        Returns:
            None

        Raises:
            Exception: Re-raises any exception raised by `run()` after logging
                duration and context.
        """
        global _execution_counter

        step_type = self.__class__.__name__
        # Guarantee a stable results namespace even when name is not provided
        step_name = self.name or step_type
        display_name = step_name

        # Determine seed provenance and effective seed for this step
        scenario_seed = getattr(scenario, "seed", None)
        step_seed = self.seed
        explicit_source = getattr(self, "_seed_source", None)
        if step_seed is not None and explicit_source == "explicit-step":
            seed_source = "explicit-step"
            active_seed = step_seed
        elif step_seed is not None and explicit_source == "scenario-derived":
            # Step received a derived seed at construction time
            seed_source = "scenario-derived"
            active_seed = step_seed
        elif scenario_seed is not None:
            seed_source = "scenario-derived"
            # Scenario.from_yaml derives per-step seeds when seed is provided; if a
            # concrete seed was not set on the step (self.seed is None), treat the
            # scenario seed as the active base (workers may derive offsets internally).
            active_seed = scenario_seed
        else:
            seed_source = "none"
            active_seed = None

        # Enter step scope and store workflow metadata
        scenario.results.enter_step(step_name)
        scenario.results.put_step_metadata(
            step_name=step_name,
            step_type=step_type,
            execution_order=_execution_counter,
            scenario_seed=scenario_seed,
            step_seed=step_seed,
            seed_source=seed_source,
            active_seed=active_seed,
        )
        _execution_counter += 1

        if self.seed is not None:
            logger.debug(
                "Executing step: %s (%s) with seed=%s",
                step_name,
                step_type,
                str(self.seed),
            )
        logger.info(f"Starting workflow step: {display_name} ({step_type})")
        start_time = time.time()

        try:
            self.run(scenario)
            end_time = time.time()
            duration = end_time - start_time
            # Persist step duration into step-scoped metadata for downstream analysis
            existing_md = scenario.results.get("metadata", {})
            if not isinstance(existing_md, dict):
                raise TypeError("Results metadata must be a dict")
            updated_md = dict(existing_md)
            updated_md["duration_sec"] = float(duration)
            scenario.results.put("metadata", updated_md)
            logger.info(
                f"Completed workflow step: {display_name} ({step_type}) "
                f"in {duration:.3f} seconds"
            )
            try:
                store = getattr(scenario.results, "_store", {})
                keys = ", ".join(sorted(list(store.get(step_name, {}).keys())))
            except Exception as exc:
                logger.debug(
                    "Failed to read results keys for step %s: %s", display_name, exc
                )
                keys = "-"
            logger.debug(
                "Step %s finished: duration=%.3fs, results_keys=%s",
                display_name,
                duration,
                keys or "-",
            )
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(
                f"Failed workflow step: {display_name} ({step_type}) "
                f"after {duration:.3f} seconds - {type(e).__name__}: {e}"
            )
            raise
        finally:
            # Always exit step scope
            try:
                scenario.results.exit_step()
            except Exception as exc:
                logger.warning(
                    "Failed to exit step scope cleanly for %s: %s", display_name, exc
                )

    @abstractmethod
    def run(self, scenario: "Scenario") -> None:
        """Execute the workflow step logic.

        This method should be implemented by concrete workflow step classes.
        It is called by execute() which handles logging, timing, and metadata storage.

        Args:
            scenario: The scenario to execute the step on.

        Returns:
            None
        """
        pass
