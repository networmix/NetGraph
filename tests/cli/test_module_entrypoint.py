"""Tests for running NetGraph as a module (`python -m ngraph`).

These tests exercise the `ngraph.__main__` entrypoint to improve coverage
for the module execution path.
"""

from __future__ import annotations

import runpy
from unittest.mock import patch

import pytest


def test_module_help_exits_zero() -> None:
    """Running with --help should exit cleanly with code 0."""
    with patch("sys.argv", ["ngraph", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ngraph", run_name="__main__")
    assert exc_info.value.code == 0


def test_module_cli_subcommand_help_exits_zero() -> None:
    """Invoking a subcommand's help via module entrypoint should exit 0."""
    with patch("sys.argv", ["ngraph", "inspect", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("ngraph", run_name="__main__")
    assert exc_info.value.code == 0
