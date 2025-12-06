"""Workflow parsing helpers.

Converts a normalized workflow section (list[dict]) into WorkflowStep
instances using the WORKFLOW_STEP_REGISTRY and attaches unique names/seeds.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ngraph.logging import get_logger
from ngraph.utils.yaml_utils import normalize_yaml_dict_keys
from ngraph.workflow.base import WORKFLOW_STEP_REGISTRY, WorkflowStep

_logger = get_logger(__name__)


def build_workflow_steps(
    workflow_data: List[Dict[str, Any]],
    derive_seed: Callable[[str], Optional[int]],
) -> List[WorkflowStep]:
    """Instantiate workflow steps from normalized dictionaries.

    Args:
        workflow_data: List of step dicts; each must have "step_type".
        derive_seed: Callable that takes a step name and returns a seed or None.

    Returns:
        A list of WorkflowStep instances with unique names and optional seeds.
    """
    if not isinstance(workflow_data, list):
        raise ValueError("'workflow' must be a list if present.")

    steps: List[WorkflowStep] = []
    assigned_names: set[str] = set()

    for step_index, step_info in enumerate(workflow_data):
        step_type = step_info.get("step_type")
        if not step_type:
            raise ValueError(
                "Each workflow entry must have a 'step_type' field "
                "indicating the WorkflowStep subclass to use."
            )

        step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
        if not step_cls:
            raise ValueError(f"Unrecognized 'step_type': {step_type}")

        ctor_args = {k: v for k, v in step_info.items() if k != "step_type"}
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

        step_obj = step_cls(**normalized_ctor_args)
        try:
            step_obj._seed_source = (
                "explicit-step"
                if "seed" in ctor_args and ctor_args["seed"] is not None
                else "scenario-derived"
            )
        except Exception as exc:
            _logger.debug("Failed to set _seed_source on step %s: %s", step_name, exc)

        steps.append(step_obj)

    return steps
