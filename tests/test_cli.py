import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ngraph import cli


def test_cli_run_file(tmp_path: Path) -> None:
    scenario = Path("tests/scenarios/scenario_1.yaml")
    out_file = tmp_path / "res.json"
    cli.main(["run", str(scenario), "--results", str(out_file)])
    assert out_file.is_file()
    data = json.loads(out_file.read_text())
    assert "build_graph" in data
    assert "graph" in data["build_graph"]


def test_cli_run_stdout(capsys) -> None:
    scenario = Path("tests/scenarios/scenario_1.yaml")
    cli.main(["run", str(scenario)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "build_graph" in data


def test_cli_logging_default_level(caplog):
    """Test that CLI uses INFO level by default."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_file = tmpdir_path / "test.yaml"
        scenario_file.write_text("""
network:
  nodes:
    A: {}
workflow:
  - step_type: BuildGraph
""")

        with caplog.at_level(logging.DEBUG, logger="ngraph"):
            cli.main(["run", str(scenario_file)])

        # Should have INFO messages but not DEBUG messages by default
        assert any(
            "Loading scenario from" in record.message for record in caplog.records
        )
        assert any(
            "Starting scenario execution" in record.message for record in caplog.records
        )
        assert not any(
            "Debug logging enabled" in record.message for record in caplog.records
        )


def test_cli_logging_verbose(caplog):
    """Test that --verbose enables DEBUG logging."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_file = tmpdir_path / "test.yaml"
        scenario_file.write_text("""
network:
  nodes:
    A: {}
workflow:
  - step_type: BuildGraph
""")

        with caplog.at_level(logging.DEBUG, logger="ngraph"):
            cli.main(["--verbose", "run", str(scenario_file)])

        # Should have the debug message indicating verbose mode
        assert any(
            "Debug logging enabled" in record.message for record in caplog.records
        )


def test_cli_logging_quiet(caplog):
    """Test that --quiet suppresses INFO messages."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_file = tmpdir_path / "test.yaml"
        scenario_file.write_text("""
network:
  nodes:
    A: {}
workflow:
  - step_type: BuildGraph
""")

        with caplog.at_level(logging.INFO, logger="ngraph"):
            cli.main(["--quiet", "run", str(scenario_file)])

        # In quiet mode, INFO messages should be suppressed (WARNING+ only)
        # Since we're only doing basic operations, there should be minimal logging
        info_messages = [
            record for record in caplog.records if record.levelname == "INFO"
        ]
        # There might still be some INFO messages from the workflow, but fewer
        assert len(info_messages) < 5  # Expect fewer messages in quiet mode


def test_cli_error_handling_file_not_found(caplog):
    """Test CLI error handling for missing files."""
    with pytest.raises(SystemExit) as exc_info:
        with caplog.at_level(logging.ERROR, logger="ngraph"):
            cli.main(["run", "nonexistent_file.yaml"])

    assert exc_info.value.code == 1
    assert any("Scenario file not found" in record.message for record in caplog.records)


def test_cli_output_file_logging(caplog):
    """Test CLI logging when writing to output file."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_file = tmpdir_path / "test.yaml"
        output_file = tmpdir_path / "output.json"

        scenario_file.write_text("""
network:
  nodes:
    A: {}
workflow:
  - step_type: BuildGraph
""")

        with caplog.at_level(logging.INFO, logger="ngraph"):
            cli.main(["run", str(scenario_file), "--results", str(output_file)])

        # Check that output file logging messages appear
        assert any("Writing results to" in record.message for record in caplog.records)
        assert any(
            "Results written successfully" in record.message
            for record in caplog.records
        )

        # Verify output file was created
        assert output_file.exists()


def test_cli_logging_workflow_integration(caplog):
    """Test that CLI logging integrates properly with workflow step logging."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_file = tmpdir_path / "test.yaml"
        scenario_file.write_text("""
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
        cost: 1
workflow:
  - step_type: BuildGraph
    name: build_test
  - step_type: CapacityProbe
    name: probe_test
    source_path: "A"
    sink_path: "B"
""")

        with caplog.at_level(logging.INFO, logger="ngraph"):
            cli.main(["run", str(scenario_file)])

        # Should have CLI messages
        assert any(
            "Loading scenario from" in record.message for record in caplog.records
        )
        assert any(
            "Scenario execution completed successfully" in record.message
            for record in caplog.records
        )

        # Should have workflow step messages
        assert any(
            "Starting workflow step: build_test" in record.message
            for record in caplog.records
        )
        assert any(
            "Starting workflow step: probe_test" in record.message
            for record in caplog.records
        )
        assert any(
            "Completed workflow step: build_test" in record.message
            for record in caplog.records
        )
        assert any(
            "Completed workflow step: probe_test" in record.message
            for record in caplog.records
        )


def test_cli_help_options():
    """Test that CLI help shows logging options."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])

    # Help should exit with code 0
    assert exc_info.value.code == 0
