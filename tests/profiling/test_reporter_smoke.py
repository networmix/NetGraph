from __future__ import annotations

import importlib


def test_profiling_reporter_module_importable() -> None:
    # Smoke: module provides docstring and is importable
    mod = importlib.import_module("ngraph.profiling.reporter")
    assert hasattr(mod, "__doc__")
