"""Supported submodules advertise their importable public boundary."""

import importlib
import subprocess
import sys


def test_public_module_exports_are_explicit_and_resolve_to_the_owned_types():
    import ngraph.hardware as hardware
    import ngraph.logging as logging
    import ngraph.workflow as workflow
    from ngraph.analysis.preparation import StepNeeds
    from ngraph.model.components import resolve_link_end
    from ngraph.workflow.base import step_name

    assert set(hardware.__all__) == {
        "hardware_inventory",
        "HardwareInventory",
        "HardwareUse",
        "link_active",
        "resolve_link_end",
    }
    assert set(logging.__all__) == {
        "get_logger",
        "setup_root_logger",
        "set_global_log_level",
    }
    assert {"StepNeeds", "step_name"} <= set(workflow.__all__)
    assert hardware.resolve_link_end is resolve_link_end
    assert workflow.StepNeeds is StepNeeds and workflow.step_name is step_name
    for module_name in (
        "ngraph",
        "ngraph.workflow",
        "ngraph.hardware",
        "ngraph.logging",
    ):
        module = importlib.import_module(module_name)
        assert len(module.__all__) == len(set(module.__all__))
        assert all(getattr(module, name) is not None for name in module.__all__)


def test_workflow_needs_reexport_is_safe_in_both_fresh_import_orders():
    for first in ("ngraph.scenario", "ngraph.workflow"):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import {first}; from ngraph.workflow import StepNeeds, step_name; from ngraph.analysis.preparation import StepNeeds as Original; assert StepNeeds is Original; assert callable(step_name)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
