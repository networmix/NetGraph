from __future__ import annotations

import logging
from pathlib import Path

from ngraph import cli


def test_cli_verbose_and_quiet_switch_levels(
    caplog, tmp_path: Path, monkeypatch
) -> None:
    # Minimal scenario
    scenario = tmp_path / "t.yaml"
    scenario.write_text(
        """
network:
  nodes:
    A: {}
workflow:
  - step_type: BuildGraph
"""
    )

    # run in temp directory to avoid polluting repo
    monkeypatch.chdir(tmp_path)

    # verbose enables debug
    with caplog.at_level(logging.DEBUG, logger="ngraph"):
        cli.main(
            ["--verbose", "run", str(scenario), "--no-results"]
        )  # avoid writing results
    assert any("Debug logging enabled" in r.message for r in caplog.records)

    # quiet suppresses info
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ngraph"):
        cli.main(
            ["--quiet", "run", str(scenario), "--no-results"]
        )  # avoid writing results
    assert not any(r.levelno == logging.INFO for r in caplog.records)
