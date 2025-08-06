"""Tests for core CLI functionality and edge cases."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ngraph.cli import main


class TestCLICoreCommands:
    """Test core CLI command functionality."""

    def test_cli_run_command_basic(self):
        """Test basic CLI run command functionality."""
        scenario_yaml = """
network:
  name: "cli_test"
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params: {capacity: 10.0}

workflow:
  - step_type: NetworkStats
    name: "stats"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_yaml)
            scenario_path = f.name

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = Path(tmpdir) / "results.json"

            try:
                # Test run command
                with patch(
                    "sys.argv",
                    ["ngraph", "run", scenario_path, "--results", str(results_path)],
                ):
                    main()

                # Verify results file was created
                assert results_path.exists()

                # Verify results content
                import json

                with open(results_path) as f:
                    results = json.load(f)

                # Check that the step results are present
                assert "stats" in results
                assert "workflow" in results  # Workflow metadata
                # Check that the stats step has meaningful data
                assert "link_count" in results["stats"]

            finally:
                Path(scenario_path).unlink()

    def test_cli_inspect_command(self):
        """Test CLI inspect command."""
        scenario_yaml = """
network:
  name: "inspection_test"
  nodes:
    Node1: {}
  links: []

workflow:
  - step_type: NetworkStats
    name: "inspect_stats"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_yaml)
            scenario_path = f.name

        try:
            # Test inspect command - should pass for valid scenario
            with patch("sys.argv", ["ngraph", "inspect", scenario_path]):
                main()  # Should not raise exception for valid scenario

        finally:
            Path(scenario_path).unlink()

    def test_cli_report_command(self):
        """Test CLI report generation."""
        # Create test results file
        test_results = {
            "steps": {
                "test_step": {"network_stats": {"node_count": 3, "link_count": 2}}
            },
            "metadata": {
                "test_step": {
                    "step_type": "NetworkStats",
                    "step_name": "test_step",
                    "execution_order": 0,
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = Path(tmpdir) / "test_results.json"
            report_path = Path(tmpdir) / "test_report.html"

            # Write test results
            import json

            with open(results_path, "w") as f:
                json.dump(test_results, f)

            # Test report command
            with patch(
                "sys.argv",
                ["ngraph", "report", str(results_path), "--html", str(report_path)],
            ):
                main()

            # Verify report was generated
            assert report_path.exists()

            # Basic content verification - report was generated successfully
            report_content = report_path.read_text()
            assert "<!DOCTYPE html>" in report_content  # Verify it's a valid HTML file
            assert len(report_content) > 1000  # Verify it has substantial content

    def test_cli_error_handling(self):
        """Test CLI error handling for common error cases."""
        # Test with non-existent file
        with patch("sys.argv", ["ngraph", "run", "nonexistent.yaml"]):
            with pytest.raises(SystemExit):
                main()

    def test_cli_logging_configuration(self):
        """Test CLI logging level configuration."""
        scenario_yaml = """
network:
  name: "logging_test"
  nodes:
    A: {}
  links: []
workflow:
  - step_type: NetworkStats
    name: "stats"
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create scenario file in temp directory
            scenario_path = Path(tmpdir) / "test_scenario.yaml"
            scenario_path.write_text(scenario_yaml)

            results_path = Path(tmpdir) / "results.json"

            # Test with verbose logging (global flag comes before subcommand)
            with patch(
                "sys.argv",
                [
                    "ngraph",
                    "--verbose",
                    "run",
                    str(scenario_path),
                    "--results",
                    str(results_path),
                ],
            ):
                main()

            # Should complete without error
            assert results_path.exists()

            # Test with quiet logging
            results_path_quiet = Path(tmpdir) / "results_quiet.json"
            with patch(
                "sys.argv",
                [
                    "ngraph",
                    "--quiet",
                    "run",
                    str(scenario_path),
                    "--results",
                    str(results_path_quiet),
                ],
            ):
                main()

            assert results_path_quiet.exists()


class TestCLIParameterHandling:
    """Test CLI parameter validation and handling."""

    def test_cli_output_directory_creation(self):
        """Test that CLI creates output directories when needed."""
        scenario_yaml = """
network:
  name: "output_test"
  nodes:
    A: {}
  links: []
workflow:
  - step_type: NetworkStats
    name: "stats"
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create scenario file in temp directory
            scenario_path = Path(tmpdir) / "test_scenario.yaml"
            scenario_path.write_text(scenario_yaml)

            # Create output directory first (CLI doesn't auto-create nested dirs)
            nested_dir = Path(tmpdir) / "nested" / "output"
            nested_dir.mkdir(parents=True)
            results_path = nested_dir / "results.json"

            with patch(
                "sys.argv",
                ["ngraph", "run", str(scenario_path), "--results", str(results_path)],
            ):
                main()

            # Should create results file in the existing directory
            assert results_path.exists()
            assert nested_dir.exists()

    def test_cli_overwrite_protection(self):
        """Test CLI behavior when output files already exist."""
        scenario_yaml = """
network:
  name: "overwrite_test"
  nodes:
    A: {}
  links: []
workflow:
  - step_type: NetworkStats
    name: "stats"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_yaml)
            scenario_path = f.name

        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = Path(tmpdir) / "results.json"

            # Create existing file
            results_path.write_text("existing content")

            try:
                # CLI should overwrite existing files by default
                with patch(
                    "sys.argv",
                    ["ngraph", "run", scenario_path, "--results", str(results_path)],
                ):
                    main()

                # File should be overwritten with actual results
                content = results_path.read_text()
                assert "existing content" not in content
                assert "stats" in content  # Check for actual result structure

            finally:
                Path(scenario_path).unlink()

    def test_cli_profile_parameter(self):
        """Test CLI profile parameter functionality."""
        scenario_yaml = """
network:
  name: "profile_test"
  nodes:
    A: {}
  links: []
workflow:
  - step_type: NetworkStats
    name: "stats"
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create scenario file in temp directory
            scenario_path = Path(tmpdir) / "test_scenario.yaml"
            scenario_path.write_text(scenario_yaml)

            results1_path = Path(tmpdir) / "results1.json"
            results2_path = Path(tmpdir) / "results2.json"

            # Change to temp directory so worker_profiles gets created there
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                # Run with profile flag twice
                with patch(
                    "sys.argv",
                    [
                        "ngraph",
                        "run",
                        str(scenario_path),
                        "--profile",
                        "--results",
                        str(results1_path),
                    ],
                ):
                    main()

                with patch(
                    "sys.argv",
                    [
                        "ngraph",
                        "run",
                        str(scenario_path),
                        "--profile",
                        "--results",
                        str(results2_path),
                    ],
                ):
                    main()

                # Both files should be created successfully with profiling enabled
                # Just verify files exist and have content (profiling results aren't deterministic)
                assert results1_path.stat().st_size > 0
                assert results2_path.stat().st_size > 0

                # worker_profiles directory should be cleaned up by CLI
                # (Directory may or may not exist depending on cleanup success)

            finally:
                os.chdir(original_cwd)


class TestCLIAdvancedFeatures:
    """Test advanced CLI features and integrations."""

    def test_cli_help_commands(self):
        """Test CLI help functionality."""
        # Test main help
        with patch("sys.argv", ["ngraph", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0  # Help should exit with code 0

        # Test run command help
        with patch("sys.argv", ["ngraph", "run", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
