import json
import logging
import os
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

from ngraph import cli


def extract_json_from_stdout(output: str) -> str:
    """Extract JSON content from stdout that may contain emoji feedback messages."""
    # Find JSON content by looking for { to } block
    json_start = output.find("{")
    if json_start == -1:
        return output  # No JSON found, return as-is

    # Find the matching closing brace
    brace_count = 0
    json_end = -1
    for i in range(json_start, len(output)):
        if output[i] == "{":
            brace_count += 1
        elif output[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break

    if json_end == -1:
        return output  # No complete JSON found

    return output[json_start:json_end]


def test_cli_run_file(tmp_path: Path) -> None:
    scenario = Path("tests/integration/scenario_1.yaml")
    out_file = tmp_path / "res.json"
    cli.main(["run", str(scenario), "--results", str(out_file)])
    assert out_file.is_file()
    data = json.loads(out_file.read_text())
    assert "build_graph" in data
    assert "graph" in data["build_graph"]


def test_cli_run_stdout(tmp_path: Path, capsys, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--stdout"])
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    data = json.loads(json_output)
    assert "build_graph" in data
    # With new behavior, should create results.json by default even with --stdout
    assert (tmp_path / "results.json").exists()


def test_cli_filter_keys(tmp_path: Path, capsys, monkeypatch) -> None:
    """Verify filtering of specific step names."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--stdout", "--keys", "capacity_analysis_forward"])
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    data = json.loads(json_output)
    assert list(data.keys()) == ["capacity_analysis_forward"]
    assert "capacity_envelopes" in data["capacity_analysis_forward"]
    # Should create results.json by default
    assert (tmp_path / "results.json").exists()


def test_cli_filter_multiple_steps(tmp_path: Path, capsys, monkeypatch) -> None:
    """Test filtering with multiple step names."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(
        [
            "run",
            str(scenario),
            "--stdout",
            "--keys",
            "capacity_analysis_forward",
            "capacity_analysis_forward_balanced",
        ]
    )
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    data = json.loads(json_output)

    # Should only have the two capacity analysis steps
    assert set(data.keys()) == {
        "capacity_analysis_forward",
        "capacity_analysis_forward_balanced",
    }

    # Both should have capacity_envelopes results
    assert "capacity_envelopes" in data["capacity_analysis_forward"]
    assert "capacity_envelopes" in data["capacity_analysis_forward_balanced"]

    # Should not have build_graph
    assert "build_graph" not in data
    # Should create results.json by default
    assert (tmp_path / "results.json").exists()


def test_cli_filter_single_step(tmp_path: Path, capsys, monkeypatch) -> None:
    """Test filtering with a single step name."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--stdout", "--keys", "build_graph"])
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    data = json.loads(json_output)

    # Should only have build_graph step
    assert list(data.keys()) == ["build_graph"]
    assert "graph" in data["build_graph"]

    # Should not have capacity analysis steps
    assert "capacity_analysis_forward" not in data
    assert "capacity_analysis_forward_balanced" not in data
    # Should create results.json by default
    assert (tmp_path / "results.json").exists()


def test_cli_filter_nonexistent_step(tmp_path: Path, capsys, monkeypatch) -> None:
    """Test filtering with a step name that doesn't exist."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--stdout", "--keys", "nonexistent_step"])
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    data = json.loads(json_output)

    # Should result in empty dictionary
    assert data == {}
    # Should create results.json by default
    assert (tmp_path / "results.json").exists()


def test_cli_filter_mixed_existing_nonexistent(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Test filtering with mix of existing and non-existing step names."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(
        [
            "run",
            str(scenario),
            "--stdout",
            "--keys",
            "capacity_analysis_forward",
            "nonexistent_step",
        ]
    )
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    data = json.loads(json_output)

    # Should only have the existing step
    assert list(data.keys()) == ["capacity_analysis_forward"]
    assert "capacity_envelopes" in data["capacity_analysis_forward"]
    # Should create results.json by default
    assert (tmp_path / "results.json").exists()


def test_cli_no_filter_vs_filter(tmp_path: Path, monkeypatch) -> None:
    """Test that filtering actually reduces the output compared to no filter."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    # First run without filter
    results_file1 = tmp_path / "results_no_filter.json"
    cli.main(["run", str(scenario), "--results", str(results_file1)])
    no_filter_data = json.loads(results_file1.read_text())

    # Then run with filter
    results_file2 = tmp_path / "results_with_filter.json"
    cli.main(
        [
            "run",
            str(scenario),
            "--results",
            str(results_file2),
            "--keys",
            "capacity_analysis_forward",
        ]
    )
    filter_data = json.loads(results_file2.read_text())

    # No filter should have more keys than filtered
    assert len(no_filter_data.keys()) > len(filter_data.keys())

    # Filtered data should be a subset of unfiltered data
    assert set(filter_data.keys()).issubset(set(no_filter_data.keys()))

    # The filtered step should have the same content in both
    assert (
        filter_data["capacity_analysis_forward"]
        == no_filter_data["capacity_analysis_forward"]
    )


def test_cli_filter_to_file_and_stdout(tmp_path: Path, capsys, monkeypatch) -> None:
    """Test filtering works correctly when writing to both file and stdout."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    results_file = tmp_path / "filtered_results.json"
    monkeypatch.chdir(tmp_path)

    cli.main(
        [
            "run",
            str(scenario),
            "--results",
            str(results_file),
            "--stdout",
            "--keys",
            "capacity_analysis_forward",
        ]
    )

    # Check stdout output
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    stdout_data = json.loads(json_output)

    # Check file output
    file_data = json.loads(results_file.read_text())

    # Both should be identical and contain only the filtered step
    assert stdout_data == file_data
    assert list(stdout_data.keys()) == ["capacity_analysis_forward"]
    assert "capacity_envelopes" in stdout_data["capacity_analysis_forward"]

    # Default results.json should NOT be created when custom path is specified
    assert not (tmp_path / "results.json").exists()


def test_cli_filter_preserves_step_data_structure(tmp_path: Path, monkeypatch) -> None:
    """Test that filtering preserves the complete data structure of filtered steps."""
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    # Get unfiltered results
    results_file_all = tmp_path / "results_all.json"
    cli.main(["run", str(scenario), "--results", str(results_file_all)])
    all_data = json.loads(results_file_all.read_text())

    # Get filtered results
    results_file_filtered = tmp_path / "results_filtered.json"
    cli.main(
        [
            "run",
            str(scenario),
            "--results",
            str(results_file_filtered),
            "--keys",
            "build_graph",
        ]
    )
    filtered_data = json.loads(results_file_filtered.read_text())

    # Should have complete graph structure
    assert "build_graph" in filtered_data
    assert "graph" in filtered_data["build_graph"]
    assert "nodes" in filtered_data["build_graph"]["graph"]
    assert "links" in filtered_data["build_graph"]["graph"]

    # Should have the same number of nodes and links
    assert len(filtered_data["build_graph"]["graph"]["nodes"]) == len(
        all_data["build_graph"]["graph"]["nodes"]
    )
    assert len(filtered_data["build_graph"]["graph"]["links"]) == len(
        all_data["build_graph"]["graph"]["links"]
    )


def test_cli_logging_default_level(caplog, monkeypatch):
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

        monkeypatch.chdir(tmpdir_path)
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


def test_cli_logging_verbose(caplog, monkeypatch):
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

        monkeypatch.chdir(tmpdir_path)
        with caplog.at_level(logging.DEBUG, logger="ngraph"):
            cli.main(["--verbose", "run", str(scenario_file)])

        # Should have the debug message indicating verbose mode
        assert any(
            "Debug logging enabled" in record.message for record in caplog.records
        )


def test_cli_logging_quiet(caplog, monkeypatch):
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

        monkeypatch.chdir(tmpdir_path)
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


def test_cli_logging_workflow_integration(caplog, monkeypatch):
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
  - step_type: CapacityEnvelopeAnalysis
    name: probe_test
    source_path: "A"
    sink_path: "B"
    iterations: 1
    baseline: false
    failure_policy: null
""")

        monkeypatch.chdir(tmpdir_path)
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


def test_cli_regression_empty_results_with_filter() -> None:
    """Regression test for result filtering by step names."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenario_file = tmpdir_path / "test_scenario.yaml"
        results_file = tmpdir_path / "results.json"

        # Create a simple scenario with multiple steps
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
    name: build_step
  - step_type: CapacityEnvelopeAnalysis
    name: probe_step
    source_path: "A"
    sink_path: "B"
    iterations: 1
    baseline: false
    failure_policy: null
""")

        # Run with filter - this should NOT return empty results
        cli.main(
            [
                "run",
                str(scenario_file),
                "--results",
                str(results_file),
                "--keys",
                "probe_step",
            ]
        )

        # Verify results were written and are not empty
        assert results_file.exists()
        data = json.loads(results_file.read_text())

        # Should contain the filtered step
        assert "probe_step" in data
        assert len(data) == 1  # Only the filtered step

        # Should not contain the build step
        assert "build_step" not in data

        # The probe step should have actual data
        assert len(data["probe_step"]) > 0


def test_cli_run_results_default(tmp_path: Path, monkeypatch) -> None:
    """Test that run without --results creates results.json by default."""
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario)])
    assert (tmp_path / "results.json").exists()
    data = json.loads((tmp_path / "results.json").read_text())
    assert "build_graph" in data


def test_cli_run_results_custom_path(tmp_path: Path, monkeypatch) -> None:
    """Test that --results with custom path creates file at that location."""
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--results", "custom_output.json"])
    assert (tmp_path / "custom_output.json").exists()
    assert not (tmp_path / "results.json").exists()
    data = json.loads((tmp_path / "custom_output.json").read_text())
    assert "build_graph" in data


def test_cli_run_results_and_stdout(tmp_path: Path, capsys, monkeypatch) -> None:
    """Test that --results and --stdout work together."""
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--stdout"])

    # Check stdout output
    captured = capsys.readouterr()
    json_output = extract_json_from_stdout(captured.out)
    stdout_data = json.loads(json_output)
    assert "build_graph" in stdout_data

    # Check file output (should be created by default)
    assert (tmp_path / "results.json").exists()
    file_data = json.loads((tmp_path / "results.json").read_text())
    assert "build_graph" in file_data

    # Should be the same data
    assert stdout_data == file_data


def test_cli_run_no_output(tmp_path: Path, capsys, monkeypatch) -> None:
    """Test that running with --no-results creates no files."""
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    cli.main(["run", str(scenario), "--no-results"])

    # No files should be created
    assert not (tmp_path / "results.json").exists()

    # Only success message should be produced (no JSON)
    captured = capsys.readouterr()
    assert captured.out == "✅ Scenario execution completed\n"


def test_cli_run_with_scenario_file(tmp_path, monkeypatch):
    """Test running a scenario via CLI."""
    monkeypatch.chdir(tmp_path)
    # Create a simple scenario file
    scenario_content = """
seed: 42
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
workflow:
  - step_type: BuildGraph
    name: test_step
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)

    # Capture stdout to avoid cluttering test output
    with patch("sys.stdout", new=Mock()):
        with patch("sys.argv", ["ngraph", "run", str(scenario_file)]):
            cli.main()


def test_cli_inspect_with_scenario_file(tmp_path):
    """Test inspecting a scenario file."""
    # Create a simple scenario file
    scenario_content = """
seed: 42
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
workflow:
  - step_type: BuildGraph
    name: test_step
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)

    # Capture stdout to check output
    with (
        patch("sys.stdout", new=Mock()),
        patch("builtins.print") as mock_print,
    ):
        with patch("sys.argv", ["ngraph", "inspect", str(scenario_file)]):
            cli.main()

    # Check that print was called with expected content
    print_calls = [call.args[0] for call in mock_print.call_args_list]

    # Should have scenario overview
    assert any("NETGRAPH SCENARIO INSPECTION" in str(call) for call in print_calls)
    # Should show network structure
    assert any("2. NETWORK STRUCTURE" in str(call) for call in print_calls)
    # Should show node count
    assert any("Total Nodes: 2" in str(call) for call in print_calls)
    # Should show link count
    assert any("Total Links: 1" in str(call) for call in print_calls)
    # Should show workflow steps with table format
    assert any("7. WORKFLOW STEPS" in str(call) for call in print_calls)
    # Should show deterministic seed info
    assert any("Seed: 42 (deterministic)" in str(call) for call in print_calls)
    # Should show workflow table headers
    assert any("Type" in str(call) for call in print_calls)


def test_cli_inspect_detail_mode(tmp_path):
    """Test inspecting a scenario with detail mode."""
    # Create a scenario with more content for detail mode
    scenario_content = """
seed: 1001
network:
  nodes:
    A: {}
    B: {}
    C: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
    - source: B
      target: C
      link_params:
        capacity: 200
failure_policy_set:
  test_policy:
    rules:
      - entity_scope: node
        rule_type: choice
        count: 1
traffic_matrix_set:
  default:
    - source_path: A
      sink_path: C
      demand: 50
workflow:
  - step_type: BuildGraph
    name: build_graph
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)

    # Test detail mode
    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mock_print:
        with patch("sys.argv", ["ngraph", "inspect", str(scenario_file), "--detail"]):
            cli.main()

    # Check that print was called with expected content
    print_calls = [call.args[0] for call in mock_print.call_args_list]

    # Should show complete node table in detail mode
    assert any("Nodes:" in str(call) for call in print_calls)
    # Should show node capacity and link count columns
    assert any("Tot. Capacity" in str(call) for call in print_calls)
    assert any("Links" in str(call) for call in print_calls)
    # Should show failure policy rules in detail mode
    assert any("1. node choice" in str(call) for call in print_calls)
    # Should show traffic demands in detail mode
    assert any("1. A → C (50)" in str(call) for call in print_calls)


def test_cli_inspect_nonexistent_file():
    """Test inspecting a non-existent file."""
    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mock_print:
        with patch("sys.argv", ["ngraph", "inspect", "nonexistent.yaml"]):
            with pytest.raises(SystemExit):
                cli.main()

    # Should print error message
    print_calls = [call.args[0] for call in mock_print.call_args_list]
    assert any("ERROR: Scenario file not found" in str(call) for call in print_calls)


def test_cli_inspect_invalid_yaml(tmp_path):
    """Test inspecting an invalid YAML file."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("invalid: yaml: content: [")

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mock_print:
        with patch("sys.argv", ["ngraph", "inspect", str(invalid_yaml)]):
            with pytest.raises(SystemExit):
                cli.main()

    # Should print error message
    print_calls = [call.args[0] for call in mock_print.call_args_list]
    assert any("ERROR: Failed to inspect scenario" in str(call) for call in print_calls)


def test_cli_inspect_help(capsys):
    """Test inspect command help."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["inspect", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "inspect" in out
    assert "--detail" in out


def test_main_with_no_args():
    """Test main function with no arguments."""
    with pytest.raises(SystemExit):
        cli.main([])


# Removed deprecated placeholder: test_run_scenario_success


def test_run_scenario_with_stdout(tmp_path, monkeypatch):
    """Test scenario run with stdout output."""
    monkeypatch.chdir(tmp_path)
    scenario_content = """
seed: 42
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
workflow:
  - step_type: BuildGraph
    name: test_step
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)

    with patch("builtins.print") as mock_print:
        with patch("sys.argv", ["ngraph", "run", str(scenario_file), "--stdout"]):
            cli.main()

    # Should print JSON results to stdout
    print_calls = [call.args[0] for call in mock_print.call_args_list]
    # Should contain JSON-like output
    json_output = "".join(str(call) for call in print_calls)
    assert "test_step" in json_output


def test_run_scenario_with_results_file(tmp_path, monkeypatch):
    """Test scenario run with results file output."""
    monkeypatch.chdir(tmp_path)
    scenario_content = """
seed: 42
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
workflow:
  - step_type: BuildGraph
    name: test_step
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)
    results_file = tmp_path / "results.json"

    with patch("sys.stdout", new=Mock()):
        with patch(
            "sys.argv",
            ["ngraph", "run", str(scenario_file), "--results", str(results_file)],
        ):
            cli.main()

    # Results file should exist and contain data
    assert results_file.exists()
    results_content = results_file.read_text()
    assert "test_step" in results_content


def test_cli_run_with_profile_flag(tmp_path: Path, monkeypatch) -> None:
    """Test running a scenario with --profile writes results successfully."""
    monkeypatch.chdir(tmp_path)
    scenario_content = """
seed: 123
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 10
workflow:
  - step_type: NetworkStats
    name: stats
"""
    scenario_file = tmp_path / "test_profile.yaml"
    scenario_file.write_text(scenario_content)

    results_file = tmp_path / "results_profile.json"

    cli.main(
        [
            "run",
            str(scenario_file),
            "--profile",
            "--results",
            str(results_file),
        ]
    )

    assert results_file.exists()
    data = json.loads(results_file.read_text())
    assert "stats" in data


def test_verbose_logging(tmp_path):
    """Test verbose logging option."""
    # Create a simple scenario file
    scenario_content = """
seed: 42
network:
  nodes:
    A: {}
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)

    with patch("ngraph.cli.set_global_log_level") as mock_set_level:
        with patch("sys.argv", ["ngraph", "--verbose", "inspect", str(scenario_file)]):
            with patch("builtins.print"):  # Suppress output
                cli.main()

        # Should have set DEBUG level
        import logging

        mock_set_level.assert_called_with(logging.DEBUG)


def test_quiet_logging(tmp_path):
    """Test quiet logging option."""
    # Create a simple scenario file
    scenario_content = """
seed: 42
network:
  nodes:
    A: {}
"""
    scenario_file = tmp_path / "test.yaml"
    scenario_file.write_text(scenario_content)

    with patch("ngraph.cli.set_global_log_level") as mock_set_level:
        with patch("sys.argv", ["ngraph", "--quiet", "inspect", str(scenario_file)]):
            with patch("builtins.print"):  # Suppress output
                cli.main()

        # Should have set WARNING level
        import logging

        mock_set_level.assert_called_with(logging.WARNING)


def test_cli_report_command_help(capsys):
    """Test report command help text."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["report", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "Path to results JSON file" in out
    assert "--notebook" in out
    assert "--html" in out
    assert "--include-code" in out


def test_cli_report_command_missing_file(capsys):
    """Test report command with missing results file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        missing_file = tmpdir_path / "missing.json"
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["report", str(missing_file)])
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Results file not found" in out


def test_cli_report_command_invalid_json(capsys):
    """Test report command with invalid JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        invalid_file = tmpdir_path / "invalid.json"
        invalid_file.write_text("{ invalid json }")
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["report", str(invalid_file)])
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Invalid JSON" in out


def test_cli_report_command_empty_results(capsys):
    """Test report command with empty results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        empty_file = tmpdir_path / "empty.json"
        empty_file.write_text('{"workflow": {}}')
        with pytest.raises(SystemExit) as exc_info:
            cli.main(["report", str(empty_file)])
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "No analysis results found" in out


def test_cli_report_command_notebook_only(monkeypatch, capsys):
    """Test report command generating notebook only (fast path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        results_file = tmpdir_path / "results.json"
        results_file.write_text(
            '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"data": "value"}}'
        )

        notebook_file = tmpdir_path / "test.ipynb"

        class FakeRG:
            def __init__(self, results_path):
                self.results_path = Path(results_path)

            def load_results(self):
                json.loads(self.results_path.read_text())

            def generate_notebook(self, output_path):
                Path(output_path).write_text("{}")
                return Path(output_path)

            def generate_html_report(
                self, notebook_path, html_path, include_code=False
            ):
                Path(notebook_path).write_text("{}")
                Path(html_path).write_text("<html></html>")
                return Path(html_path)

        monkeypatch.setattr(cli, "ReportGenerator", FakeRG)

        cli.main(["report", str(results_file), "--notebook", str(notebook_file)])
        out = capsys.readouterr().out
        assert "Notebook generated:" in out
        assert notebook_file.exists()


def test_cli_report_command_with_html(monkeypatch, capsys):
    """Test report command generating both notebook and HTML (fast path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        results_file = tmpdir_path / "results.json"
        results_file.write_text(
            '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"data": "value"}}'
        )

        notebook_file = tmpdir_path / "test.ipynb"
        html_file = tmpdir_path / "test.html"

        class FakeRG:
            def __init__(self, results_path):
                self.results_path = Path(results_path)

            def load_results(self):
                json.loads(self.results_path.read_text())

            def generate_notebook(self, output_path):
                Path(output_path).write_text("{}")
                return Path(output_path)

            def generate_html_report(
                self, notebook_path, html_path, include_code=False
            ):
                Path(notebook_path).write_text("{}")
                Path(html_path).write_text("<html></html>")
                return Path(html_path)

        monkeypatch.setattr(cli, "ReportGenerator", FakeRG)

        cli.main(
            [
                "report",
                str(results_file),
                "--notebook",
                str(notebook_file),
                "--html",
                str(html_file),
            ]
        )

        out = capsys.readouterr().out
        assert "Notebook generated:" in out
        assert "HTML report generated:" in out
        assert notebook_file.exists()
        assert html_file.exists()


def test_cli_report_command_html_default(monkeypatch, capsys):
    """Test report command generating HTML with default filename (fast path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        results_file = tmpdir_path / "results.json"
        results_file.write_text(
            '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"data": "value"}}'
        )

        class FakeRG:
            def __init__(self, results_path):
                self.results_path = Path(results_path)

            def load_results(self):
                json.loads(self.results_path.read_text())

            def generate_notebook(self, output_path):
                Path(output_path).write_text("{}")
                return Path(output_path)

            def generate_html_report(
                self, notebook_path, html_path, include_code=False
            ):
                Path(notebook_path).write_text("{}")
                Path(html_path).write_text("<html></html>")
                return Path(html_path)

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            monkeypatch.setattr(cli, "ReportGenerator", FakeRG)
            cli.main(["report", str(results_file), "--html"])
            out = capsys.readouterr().out
            assert "Notebook generated:" in out
            assert "HTML report generated:" in out
            assert (tmpdir_path / "analysis.ipynb").exists()
            assert (tmpdir_path / "analysis.html").exists()
        finally:
            os.chdir(original_cwd)


def test_cli_report_command_with_code_included(monkeypatch, capsys):
    """Test report command with code cells included in HTML (fast path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        results_file = tmpdir_path / "results.json"
        results_file.write_text(
            '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"data": "value"}}'
        )

        notebook_file = tmpdir_path / "test.ipynb"
        html_file = tmpdir_path / "test.html"

        class FakeRG:
            def __init__(self, results_path):
                self.results_path = Path(results_path)

            def load_results(self):
                json.loads(self.results_path.read_text())

            def generate_notebook(self, output_path):
                Path(output_path).write_text("{}")
                return Path(output_path)

            def generate_html_report(
                self, notebook_path, html_path, include_code=False
            ):
                Path(notebook_path).write_text("{}")
                Path(html_path).write_text("<html></html>")
                return Path(html_path)

        monkeypatch.setattr(cli, "ReportGenerator", FakeRG)

        cli.main(
            [
                "report",
                str(results_file),
                "--notebook",
                str(notebook_file),
                "--html",
                str(html_file),
                "--include-code",
            ]
        )

        out = capsys.readouterr().out
        assert "Notebook generated:" in out
        assert "HTML report generated:" in out
        assert notebook_file.exists()
        assert html_file.exists()


def test_cli_report_command_custom_notebook_path(monkeypatch, capsys):
    """Test report command with custom notebook path (fast path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        results_file = tmpdir_path / "results.json"
        results_file.write_text(
            '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"data": "value"}}'
        )

        custom_notebook = tmpdir_path / "custom_analysis.ipynb"

        class FakeRG:
            def __init__(self, results_path):
                self.results_path = Path(results_path)

            def load_results(self):
                json.loads(self.results_path.read_text())

            def generate_notebook(self, output_path):
                Path(output_path).write_text("{}")
                return Path(output_path)

            def generate_html_report(
                self, notebook_path, html_path, include_code=False
            ):
                Path(notebook_path).write_text("{}")
                Path(html_path).write_text("<html></html>")
                return Path(html_path)

        monkeypatch.setattr(cli, "ReportGenerator", FakeRG)

        cli.main(["report", str(results_file), "--notebook", str(custom_notebook)])
        out = capsys.readouterr().out
        assert "Notebook generated:" in out
        assert custom_notebook.exists()


def test_cli_report_command_default_results_file(monkeypatch, capsys):
    """Test report command with default results.json file (fast path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            results_file = Path("results.json")
            results_file.write_text(
                '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"data": "value"}}'
            )

            class FakeRG:
                def __init__(self, results_path):
                    self.results_path = Path(results_path)

                def load_results(self):
                    json.loads(self.results_path.read_text())

                def generate_notebook(self, output_path):
                    Path(output_path).write_text("{}")
                    return Path(output_path)

                def generate_html_report(
                    self, notebook_path, html_path, include_code=False
                ):
                    Path(notebook_path).write_text("{}")
                    Path(html_path).write_text("<html></html>")
                    return Path(html_path)

            monkeypatch.setattr(cli, "ReportGenerator", FakeRG)
            cli.main(["report"])
            out = capsys.readouterr().out
            assert "Notebook generated:" in out
            assert Path("analysis.ipynb").exists()
        finally:
            os.chdir(original_cwd)
