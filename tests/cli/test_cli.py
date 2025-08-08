import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

from ngraph import cli

# Utilities


def extract_json_from_stdout(output: str) -> str:
    """Return the JSON payload from stdout that may include status lines.

    This helper isolates the first balanced JSON object for reliable parsing.
    """
    json_start = output.find("{")
    if json_start == -1:
        return output

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
    return output[json_start:json_end] if json_end != -1 else output


# High-value CLI run command tests


def test_run_writes_results_file_and_contains_build_graph(tmp_path: Path) -> None:
    scenario = Path("tests/integration/scenario_1.yaml")
    results_path = tmp_path / "res.json"

    cli.main(["run", str(scenario), "--results", str(results_path)])

    assert results_path.exists()
    data = json.loads(results_path.read_text())
    assert "build_graph" in data
    assert "graph" in data["build_graph"]


def test_run_stdout_and_default_results(tmp_path: Path, capsys, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--stdout"])
    captured = capsys.readouterr()
    payload = json.loads(extract_json_from_stdout(captured.out))

    assert "build_graph" in payload
    # default results.json is created when --results not passed
    assert (tmp_path / "results.json").exists()


def test_run_no_results_flag_produces_no_file(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--no-results"])  # still prints a status line
    captured = capsys.readouterr()

    assert not (tmp_path / "results.json").exists()
    assert "Scenario execution completed" in captured.out


def test_run_custom_results_path_disables_default(tmp_path: Path, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    out_path = tmp_path / "custom.json"
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--results", str(out_path)])

    assert out_path.exists()
    assert not (tmp_path / "results.json").exists()


def test_run_filter_by_step_names_subsets_results(tmp_path: Path, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    all_path = tmp_path / "all.json"
    cli.main(["run", str(scenario), "--results", str(all_path)])
    all_data = json.loads(all_path.read_text())

    filtered_path = tmp_path / "filtered.json"
    cli.main(
        [
            "run",
            str(scenario),
            "--results",
            str(filtered_path),
            "--keys",
            "capacity_analysis_forward",
        ]
    )
    filtered_data = json.loads(filtered_path.read_text())

    assert set(filtered_data.keys()) == {"capacity_analysis_forward"}
    assert "capacity_envelopes" in filtered_data["capacity_analysis_forward"]
    assert set(filtered_data.keys()).issubset(set(all_data.keys()))


def test_run_filter_nonexistent_step_produces_empty_results(
    tmp_path: Path, monkeypatch
) -> None:
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    out_path = tmp_path / "empty.json"
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--results", str(out_path), "--keys", "missing"])
    data = json.loads(out_path.read_text())
    assert data == {}


def test_run_profile_flag_writes_results(tmp_path: Path, monkeypatch) -> None:
    scenario_file = tmp_path / "p.yaml"
    scenario_file.write_text(
        """
seed: 1
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 1
workflow:
  - step_type: NetworkStats
    name: stats
"""
    )
    out_path = tmp_path / "res.json"
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario_file), "--profile", "--results", str(out_path)])

    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert "stats" in data


# Logging behavior (value assertions, not implementation details)


def test_logging_levels_default_verbose_quiet(
    caplog, tmp_path: Path, monkeypatch
) -> None:
    scenario_file = tmp_path / "t.yaml"
    scenario_file.write_text(
        """
network:
  nodes:
    A: {}
workflow:
  - step_type: BuildGraph
"""
    )
    monkeypatch.chdir(tmp_path)

    # default = INFO
    with caplog.at_level(logging.DEBUG, logger="ngraph"):
        cli.main(["run", str(scenario_file)])
    assert any("Loading scenario from" in r.message for r in caplog.records)
    assert not any("Debug logging enabled" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="ngraph"):
        cli.main(["--verbose", "run", str(scenario_file)])
    assert any("Debug logging enabled" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ngraph"):
        cli.main(["--quiet", "run", str(scenario_file)])
    # fewer/no INFO-level messages when quiet
    info_records = [r for r in caplog.records if r.levelname == "INFO"]
    assert len(info_records) < 5


# Inspect command tests (functional output presence)


def test_inspect_happy_path_prints_sections(tmp_path: Path) -> None:
    scenario_file = tmp_path / "s.yaml"
    scenario_file.write_text(
        """
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
    name: build
"""
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file)])

    out_lines = [c.args[0] for c in mprint.call_args_list]
    assert any("NETGRAPH SCENARIO INSPECTION" in str(x) for x in out_lines)
    assert any("2. NETWORK STRUCTURE" in str(x) for x in out_lines)
    assert any("7. WORKFLOW STEPS" in str(x) for x in out_lines)


def test_inspect_detail_mode_includes_tables(tmp_path: Path) -> None:
    scenario_file = tmp_path / "s.yaml"
    scenario_file.write_text(
        """
seed: 1
network:
  nodes:
    A: {}
    B: {}
    C: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 10
    - source: B
      target: C
      link_params:
        capacity: 20
workflow:
  - step_type: BuildGraph
"""
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file), "--detail"])

    out = "\n".join(str(c.args[0]) for c in mprint.call_args_list)
    assert "Nodes:" in out
    assert "Links:" in out


def test_inspect_errors_for_missing_and_invalid_files(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.yaml"
    invalid.write_text("invalid: yaml: content: [")

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        with pytest.raises(SystemExit):
            cli.main(["inspect", str(invalid)])
    assert any(
        "ERROR: Failed to inspect scenario" in str(c.args[0])
        for c in mprint.call_args_list
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint2:
        with pytest.raises(SystemExit):
            cli.main(["inspect", str(tmp_path / "missing.yaml")])
    assert any(
        "ERROR: Scenario file not found" in str(c.args[0])
        for c in mprint2.call_args_list
    )


# Report command tests (fast path with fake generator)


def test_report_fast_paths(monkeypatch, capsys) -> None:
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        results = tmp / "results.json"
        results.write_text(
            '{"workflow": {"step1": {"step_type": "NetworkStats", "step_name": "step1", "execution_order": 0}}, "step1": {"x": 1}}'
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

        nb = tmp / "a.ipynb"
        html = tmp / "a.html"
        monkeypatch.setattr(cli, "ReportGenerator", FakeRG)

        # notebook only
        cli.main(["report", str(results), "--notebook", str(nb)])
        out = capsys.readouterr().out
        assert "Notebook generated:" in out
        assert nb.exists()

        # notebook + html
        cli.main(["report", str(results), "--notebook", str(nb), "--html", str(html)])
        out = capsys.readouterr().out
        assert "Notebook generated:" in out and "HTML report generated:" in out
        assert nb.exists() and html.exists()


def test_report_error_paths(capsys) -> None:
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # missing file
        missing = tmp / "missing.json"
        with pytest.raises(SystemExit):
            cli.main(["report", str(missing)])
        assert "Results file not found" in capsys.readouterr().out

        # invalid json
        bad = tmp / "bad.json"
        bad.write_text("{ invalid }")
        with pytest.raises(SystemExit):
            cli.main(["report", str(bad)])
        assert "Invalid JSON" in capsys.readouterr().out

        # empty results
        empty = tmp / "empty.json"
        empty.write_text('{"workflow": {}}')
        with pytest.raises(SystemExit):
            cli.main(["report", str(empty)])
        assert "No analysis results found" in capsys.readouterr().out


# Module entrypoint minimal coverage (keep separate dedicated file for runpy cases)


def test_main_with_no_args_exits() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
