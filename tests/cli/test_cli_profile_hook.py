"""Tests for the CLI --profile path driven through Scenario.run step hooks."""

from __future__ import annotations

import os
from pathlib import Path

from ngraph import cli

_SCENARIO_YAML = """
seed: 1
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      capacity: 1
workflow:
  - type: NetworkStats
    name: stats
"""


def test_run_profile_prints_performance_report(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """``ngraph run --profile`` still emits the per-step performance report."""
    scenario_file = tmp_path / "p.yaml"
    scenario_file.write_text(_SCENARIO_YAML)
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario_file), "--profile", "--no-results"])

    captured = capsys.readouterr()
    # The report is human-facing output and goes to stderr; stdout stays
    # reserved for machine-readable results.
    assert "NETGRAPH PERFORMANCE PROFILING REPORT" in captured.err
    # Per-step profiling was driven through Scenario.run's step hook
    assert "stats" in captured.err


def test_run_profile_restores_profile_dir_env(tmp_path: Path, monkeypatch) -> None:
    """NGRAPH_PROFILE_DIR is restored after a --profile run completes."""
    scenario_file = tmp_path / "p.yaml"
    scenario_file.write_text(_SCENARIO_YAML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NGRAPH_PROFILE_DIR", raising=False)

    cli.main(["run", str(scenario_file), "--profile", "--no-results"])

    # Previously unset, so it must be removed (not left pointing at a stale
    # directory that would silently re-enable worker profiling later).
    assert "NGRAPH_PROFILE_DIR" not in os.environ


def test_run_profile_restores_preexisting_profile_dir_env(
    tmp_path: Path, monkeypatch
) -> None:
    """A pre-existing NGRAPH_PROFILE_DIR value is restored after --profile."""
    scenario_file = tmp_path / "p.yaml"
    scenario_file.write_text(_SCENARIO_YAML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NGRAPH_PROFILE_DIR", "/tmp/preexisting-profile-dir")

    cli.main(["run", str(scenario_file), "--profile", "--no-results"])

    assert os.environ["NGRAPH_PROFILE_DIR"] == "/tmp/preexisting-profile-dir"
