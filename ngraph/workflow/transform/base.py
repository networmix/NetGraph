"""Base classes for network transformations."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Dict, Self, Type

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

from ngraph.workflow.base import WorkflowStep, register_workflow_step

TRANSFORM_REGISTRY: Dict[str, Type["NetworkTransform"]] = {}


def register_transform(name: str) -> Any:
    """Class decorator that registers a concrete :class:`NetworkTransform` and
    auto-wraps it as a :class:`WorkflowStep`.

    The same *name* is used for both the transform factory and the workflow
    ``step_type`` in YAML.

    Raises:
        ValueError: If *name* is already registered.
    """

    def decorator(cls: Type["NetworkTransform"]) -> Type["NetworkTransform"]:
        if name in TRANSFORM_REGISTRY:
            raise ValueError(f"Transform '{name}' already registered.")
        TRANSFORM_REGISTRY[name] = cls

        @register_workflow_step(name)
        class _TransformStep(WorkflowStep):
            """Auto-generated wrapper that executes *cls.apply*."""

            def __init__(self, **kwargs: Any) -> None:
                # Extract seed and name for the WorkflowStep base class
                seed = kwargs.pop("seed", None)
                step_name = kwargs.pop("name", "")
                super().__init__(name=step_name, seed=seed)

                # Pass remaining kwargs and seed to transform
                kwargs["seed"] = seed
                self._transform = cls(**kwargs)

            def run(self, scenario: "Scenario") -> None:  # noqa: D401
                self._transform.apply(scenario)

        return cls

    return decorator


class NetworkTransform(abc.ABC):
    """Stateless mutator applied to a :class:`ngraph.scenario.Scenario`.

    Subclasses must override :meth:`apply`.

    Transform-based workflow steps are automatically registered and can be used
    in YAML workflow configurations. Each transform is wrapped as a WorkflowStep
    using the @register_transform decorator.

    YAML Configuration (Generic):
        ```yaml
        workflow:
          - step_type: <TransformName>
            name: "optional_step_name"  # Optional: Custom name for this step instance
            # ... transform-specific parameters ...
        ```

    Attributes:
        label: Optional description string for this transform instance.
    """

    label: str = ""

    @abc.abstractmethod
    def apply(self, scenario: "Scenario") -> None:
        """Modify *scenario.network* in-place."""
        ...

    @classmethod
    def create(cls, step_type: str, **kwargs: Any) -> Self:
        """Instantiate a registered transform by *step_type*.

        Args:
            step_type: Name given in :func:`register_transform`.
            **kwargs: Arguments forwarded to the transform constructor.

        Returns:
            A concrete :class:`NetworkTransform`.

        Raises:
            KeyError: If *step_type* is not found.
        """
        try:
            impl = TRANSFORM_REGISTRY[step_type]
        except KeyError as exc:
            raise KeyError(f"Unknown transform '{step_type}'.") from exc
        return impl(**kwargs)  # type: ignore[call-arg]
