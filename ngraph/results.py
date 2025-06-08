from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Results:
    """A container for storing arbitrary key-value data that arises during workflow steps.
    The data is organized by step name, then by key.

    Example usage:
      results.put("Step1", "total_capacity", 123.45)
      cap = results.get("Step1", "total_capacity")  # returns 123.45
      all_caps = results.get_all("total_capacity")  # might return {"Step1": 123.45, "Step2": 98.76}
    """

    # Internally, store per-step data in a nested dict:
    #   _store[step_name][key] = value
    _store: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Return a dictionary representation of all stored results.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary representation of all stored results.
        """
        return {step: data.copy() for step, data in self._store.items()}
