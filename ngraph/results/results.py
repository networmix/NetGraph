"""Generic results store for workflow steps and their metadata.

`Results` organizes arbitrary key-value outputs by workflow step name and
records lightweight `WorkflowStepMetadata` to preserve execution context.
All stored values are kept as-is; objects that implement ``to_dict()`` are
converted when exporting with `Results.to_dict()` for JSON serialization.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class WorkflowStepMetadata:
    """Metadata for a workflow step execution.

    Attributes:
        step_type: The workflow step class name (e.g., 'CapacityEnvelopeAnalysis').
        step_name: The instance name of the step.
        execution_order: Order in which this step was executed (0-based).
    """

    step_type: str
    step_name: str
    execution_order: int


@dataclass
class Results:
    """A container for storing arbitrary key-value data that arises during workflow steps.

    The data is organized by step name, then by key. Each step also has associated
    metadata that describes the workflow step type and execution context.

    Example usage:
      results.put("Step1", "total_capacity", 123.45)
      cap = results.get("Step1", "total_capacity")  # returns 123.45
      all_caps = results.get_all("total_capacity")  # might return {"Step1": 123.45, "Step2": 98.76}
      metadata = results.get_step_metadata("Step1")  # returns WorkflowStepMetadata
    """

    # Internally, store per-step data in a nested dict:
    #   _store[step_name][key] = value
    _store: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Store metadata for each workflow step:
    #   _metadata[step_name] = WorkflowStepMetadata
    _metadata: Dict[str, WorkflowStepMetadata] = field(default_factory=dict)

    def put(self, step_name: str, key: str, value: Any) -> None:
        """Store a value under (step_name, key).
        If the step_name sub-dict does not exist, it is created.

        Args:
            step_name (str): The workflow step that produced the result.
            key (str): A short label describing the data (e.g. "total_capacity").
            value (Any): The actual data to store (can be any Python object).
        """
        if step_name not in self._store:
            self._store[step_name] = {}
        self._store[step_name][key] = value

    def put_step_metadata(
        self, step_name: str, step_type: str, execution_order: int
    ) -> None:
        """Store metadata for a workflow step.

        Args:
            step_name: The step instance name.
            step_type: The workflow step class name.
            execution_order: Order in which this step was executed (0-based).
        """
        self._metadata[step_name] = WorkflowStepMetadata(
            step_type=step_type, step_name=step_name, execution_order=execution_order
        )

    def get(self, step_name: str, key: str, default: Any = None) -> Any:
        """Retrieve the value from (step_name, key). If the key is missing, return `default`.

        Args:
            step_name (str): The workflow step name.
            key (str): The key under which the data was stored.
            default (Any): Value to return if the (step_name, key) is not present.

        Returns:
            Any: The data, or `default` if not found.
        """
        return self._store.get(step_name, {}).get(key, default)

    def get_all(self, key: str) -> Dict[str, Any]:
        """Retrieve a dictionary of {step_name: value} for all step_names that contain the specified key.

        Args:
            key (str): The key to look up in each step.

        Returns:
            Dict[str, Any]: A dict mapping step_name -> value for all steps that have stored something under 'key'.
        """
        result = {}
        for step_name, data in self._store.items():
            if key in data:
                result[step_name] = data[key]
        return result

    def get_step_metadata(self, step_name: str) -> Optional[WorkflowStepMetadata]:
        """Get metadata for a workflow step.

        Args:
            step_name: The step name.

        Returns:
            WorkflowStepMetadata if found, None otherwise.
        """
        return self._metadata.get(step_name)

    def get_all_step_metadata(self) -> Dict[str, WorkflowStepMetadata]:
        """Get metadata for all workflow steps.

        Returns:
            Dictionary mapping step names to their metadata.
        """
        return self._metadata.copy()

    def get_steps_by_execution_order(self) -> list[str]:
        """Get step names ordered by their execution order.

        Returns:
            List of step names in execution order.
        """
        return sorted(
            self._metadata.keys(), key=lambda step: self._metadata[step].execution_order
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of all stored results.

        Automatically converts any stored objects that have a to_dict() method
        to their dictionary representation for JSON serialization.

        Returns:
            Dict[str, Any]: Dictionary representation including results and workflow metadata.
        """
        out: Dict[str, Any] = {}

        # Add workflow metadata
        out["workflow"] = {
            step_name: {
                "step_type": metadata.step_type,
                "step_name": metadata.step_name,
                "execution_order": metadata.execution_order,
            }
            for step_name, metadata in self._metadata.items()
        }

        # Add step results
        for step, data in self._store.items():
            out[step] = {}
            for key, value in data.items():
                out[step][key] = value.to_dict() if hasattr(value, "to_dict") else value

        return out
