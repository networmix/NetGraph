"""Workflow parsing helpers.

Converts a normalized workflow section (list[dict]) into WorkflowStep
instances using the WORKFLOW_STEP_REGISTRY and attaches unique names/seeds.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional

from ngraph.utils.yaml_utils import check_no_extra_keys, normalize_yaml_dict_keys
from ngraph.workflow.base import WORKFLOW_STEP_REGISTRY, WorkflowStep


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
        step_type = step_info.get("type")
        if not step_type:
            raise ValueError(
                "Each workflow entry must have a 'type' field "
                "indicating the WorkflowStep subclass to use."
            )

        step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
        if not step_cls:
            raise ValueError(f"Unrecognized step 'type': {step_type}")

        ctor_args = {k: v for k, v in step_info.items() if k != "type"}
        normalized_ctor_args = normalize_yaml_dict_keys(ctor_args)

        raw_name = normalized_ctor_args.get("name")
        if isinstance(raw_name, str) and raw_name.strip() == "":
            raw_name = None
        step_name = raw_name or f"{step_type}_{step_index}"

        if step_name in assigned_names:
            raise ValueError(
                f"Duplicate workflow step name '{step_name}'. Each step must have a unique name."
            )
        assigned_names.add(step_name)

        normalized_ctor_args["name"] = step_name

        if "seed" not in normalized_ctor_args or normalized_ctor_args["seed"] is None:
            derived = derive_seed(step_name)
            if derived is not None:
                normalized_ctor_args["seed"] = derived

        init_fields = {f.name for f in dataclasses.fields(step_cls) if f.init}
        check_no_extra_keys(
            normalized_ctor_args, init_fields, f"workflow step '{step_name}'"
        )
        step_obj = step_cls(**normalized_ctor_args)
        if ctor_args.get("seed") is None:
            step_obj._seed_source = "scenario-derived"

        steps.append(step_obj)

    return steps
