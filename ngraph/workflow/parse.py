"""Workflow parsing helpers.

Converts a normalized workflow section (list[dict]) into WorkflowStep
instances using the WORKFLOW_STEP_REGISTRY and attaches unique names/seeds.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional

from ngraph.utils.values import _shown
from ngraph.utils.yaml_utils import (
    check_no_extra_keys,
    normalize_yaml_dict_keys,
)
from ngraph.workflow.base import WorkflowStep, _check_name_length
from ngraph.workflow.base import step_type as registered_step
from ngraph.workflow.diagnostics import (
    workflow_declared,
    workflow_error,
    workflow_location,
)


def build_workflow_steps(
    workflow_data: List[Dict[str, Any]],
    derive_seed: Callable[[str], Optional[int]],
) -> List[WorkflowStep]:
    """Instantiate workflow steps from normalized dictionaries.

    Args:
        workflow_data: List of step dicts; each must have "type".
        derive_seed: Callable that takes a step name and returns a seed or None.

    Returns:
        WorkflowStep instances. An unnamed step is named "{type}_{index}"; a
        step without a seed gets ``derive_seed(name)`` when that is not None.

    Raises:
        ValueError: If ``workflow_data`` is not a list, a step lacks ``type``
            or names an unregistered type, two steps resolve to the same
            name, or a step carries a key its step class does not define.
    """
    if not isinstance(workflow_data, list):
        raise ValueError("'workflow' must be a list if present.")

    steps: List[WorkflowStep] = []
    assigned_names: set[str] = set()

    for step_index, step_info in enumerate(workflow_data):
        location = workflow_location(step_index, step_info.get("name"))
        step_type = step_info.get("type")
        if not step_type:
            raise workflow_error(
                location,
                step_info["type"] if "type" in step_info else step_info,
                "Each workflow entry must have a 'type' field "
                "indicating the WorkflowStep subclass to use.",
                "type" if "type" in step_info else "",
            )

        step_cls = registered_step(step_type)
        if not step_cls:
            raise workflow_error(location, step_type, "unrecognized step type", "type")

        ctor_args = {k: v for k, v in step_info.items() if k != "type"}
        normalized_ctor_args = normalize_yaml_dict_keys(ctor_args)

        raw_name = workflow_declared(
            location,
            step_info,
            lambda normalized_ctor_args=normalized_ctor_args: _check_name_length(
                normalized_ctor_args.get("name")
            ),
        )
        if isinstance(raw_name, str) and raw_name.strip() == "":
            raw_name = None
        step_name = raw_name or f"{step_type}_{step_index}"

        workflow_declared(
            workflow_location(step_index, step_name),
            {"name": step_name},
            lambda step_name=step_name: _check_name_length(step_name),
        )
        if step_name in assigned_names:
            raise workflow_error(
                workflow_location(step_index, step_name),
                normalized_ctor_args.get("name"),
                f"Duplicate workflow step name {step_name!r}. Each step must have a unique name; got {normalized_ctor_args.get('name')!r}.",
                "name",
            )
        assigned_names.add(step_name)

        normalized_ctor_args["name"] = step_name

        # Each step type turns its own YAML keys into constructor arguments.
        location = workflow_location(step_index, step_name)
        normalized_ctor_args = workflow_declared(
            location,
            step_info,
            lambda step_cls=step_cls,
            normalized_ctor_args=normalized_ctor_args,
            step_name=step_name: step_cls.yaml_arguments(
                normalized_ctor_args, step_name
            ),
            f"workflow step {step_name}",
        )

        # Declaration provenance is the parser's, never a YAML key.
        init_fields = {f.name for f in dataclasses.fields(step_cls) if f.init} - {
            "yaml_label",
            "derived_seed",
        }
        workflow_declared(
            location,
            step_info,
            lambda normalized_ctor_args=normalized_ctor_args,
            init_fields=init_fields,
            step_name=step_name: check_no_extra_keys(
                normalized_ctor_args,
                init_fields,
                f"workflow step {_shown(str.__str__(step_name) if isinstance(step_name, str) else step_name)}",
            ),
        )
        provenance: Dict[str, Any] = {"yaml_label": f"workflow step {step_name}"}
        if normalized_ctor_args.get("seed") is None:
            derived = derive_seed(step_name)
            if derived is not None:
                normalized_ctor_args["seed"] = provenance["derived_seed"] = derived
        step = workflow_declared(
            location,
            step_info,
            lambda step_cls=step_cls,
            normalized_ctor_args=normalized_ctor_args,
            provenance=provenance: step_cls(**normalized_ctor_args, **provenance),
            step_type,
            f"workflow step {step_name}",
            f"workflow.{step_name}",
        )
        steps.append(step)

    return steps
