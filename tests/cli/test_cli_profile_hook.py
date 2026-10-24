"""Tests for the CLI --profile path driven through Scenario.run step hooks."""

from __future__ import annotations

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
    name: alpha_step
"""


def test_run_profile_prints_performance_report(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """``ngraph run --profile`` emits the per-step performance report."""
    scenario_file = tmp_path / "p.yaml"
    scenario_file.write_text(_SCENARIO_YAML)
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario_file), "--profile", "--no-results"])

    captured = capsys.readouterr()
    # The report is human-facing output and goes to stderr; stdout stays
    # reserved for machine-readable results.
    assert "NETGRAPH PERFORMANCE PROFILING REPORT" in captured.err
    # Per-step profiling was driven through Scenario.run's step hook, under the
    # step's run name (its class is NetworkStats).
    assert "alpha_step" in captured.err
