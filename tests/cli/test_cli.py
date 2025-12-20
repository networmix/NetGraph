import json
import logging
from pathlib import Path
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
    assert "steps" in data and "workflow" in data
    # built step is named 'build_graph'
    assert "build_graph" in data["steps"]
    assert "graph" in data["steps"]["build_graph"]["data"]


def test_run_stdout_and_default_results(tmp_path: Path, capsys, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--stdout"])
    captured = capsys.readouterr()
    payload = json.loads(extract_json_from_stdout(captured.out))

    assert "steps" in payload and "build_graph" in payload["steps"]
    # default <scenario_name>.results.json is created when --results not passed
    assert (tmp_path / "scenario_1.results.json").exists()


def test_run_no_results_flag_produces_no_file(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--no-results"])  # still prints a status line
    captured = capsys.readouterr()

    assert not (tmp_path / "scenario_1.results.json").exists()
    assert "Scenario execution completed" in captured.out


def test_run_custom_results_path_disables_default(tmp_path: Path, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    out_path = tmp_path / "custom.json"
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--results", str(out_path)])

    assert out_path.exists()
    assert not (tmp_path / "scenario_1.results.json").exists()


def test_run_output_dir_default_naming(tmp_path: Path) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()

    out_dir = tmp_path / "out"
    cli.main(["run", str(scenario), "-o", str(out_dir)])

    # With output dir, default naming uses '<prefix>.results.json'
    expected = out_dir / "scenario_1.results.json"
    assert expected.exists()


def test_run_output_dir_with_relative_override(tmp_path: Path, monkeypatch) -> None:
    scenario = Path("tests/integration/scenario_1.yaml").resolve()
    out_dir = tmp_path / "out2"
    monkeypatch.chdir(tmp_path)

    # Relative override should be resolved under output dir
    cli.main(["run", str(scenario), "-o", str(out_dir), "--results", "custom.json"])
    assert (out_dir / "custom.json").exists()
    # No default file should be created in CWD
    assert not (tmp_path / "scenario_1.results.json").exists()


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

    assert set(filtered_data.get("steps", {}).keys()) == {"capacity_analysis_forward"}
    assert set(filtered_data.get("steps", {}).keys()).issubset(
        set(all_data.get("steps", {}).keys())
    )


def test_run_filter_nonexistent_step_produces_empty_results(
    tmp_path: Path, monkeypatch
) -> None:
    scenario = Path("tests/integration/scenario_3.yaml").resolve()
    out_path = tmp_path / "empty.json"
    monkeypatch.chdir(tmp_path)

    cli.main(["run", str(scenario), "--results", str(out_path), "--keys", "missing"])
    data = json.loads(out_path.read_text())
    assert data.get("steps", {}) == {}


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
    assert "steps" in data and "stats" in data["steps"]


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


def test_inspect_detail_mode_cost_shows_decimals(tmp_path: Path) -> None:
    scenario_file = tmp_path / "s_cost.yaml"
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
        capacity: 10
        cost: 0.1
workflow:
  - step_type: BuildGraph
"""
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file), "--detail"])

    out = "\n".join(str(c.args[0]) for c in mprint.call_args_list)
    # Expect decimal cost to be preserved, not rounded to integer "0"
    assert "0.1" in out


def test_inspect_workflow_node_selection_preview_basic(tmp_path: Path) -> None:
    scenario_file = tmp_path / "s.yaml"
    scenario_file.write_text(
        """
seed: 1
network:
  nodes:
    src-1: {}
    src-2: {}
    dst-1: {}
workflow:
  - step_type: MaxFlow
    name: cap
    source: "^src"
    sink: "^dst"
"""
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file)])

    out = "\n".join(str(c.args[0]) for c in mprint.call_args_list)
    assert "Node selection preview:" in out
    assert "source:" in out and "sink:" in out
    assert "groups" in out and "nodes" in out


def test_inspect_workflow_node_selection_detail_and_warning(tmp_path: Path) -> None:
    scenario_file = tmp_path / "s2.yaml"
    scenario_file.write_text(
        """
seed: 1
network:
  nodes:
    A: {}
workflow:
  - step_type: MaxFlow
    name: cap2
    source: "^none"
    sink: "^none"
"""
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file), "--detail"])

    out = "\n".join(str(c.args[0]) for c in mprint.call_args_list)
    assert "Node matches:" in out
    assert "Field" in out and "Pattern" in out and "Matches" in out
    assert "WARNING: No nodes matched" in out


def test_inspect_capacity_vs_demand_summary_basic(tmp_path: Path) -> None:
    scenario_file = tmp_path / "cap_vs_demand.yaml"
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
        capacity: 100
traffic_matrix_set:
  default:
    - source: "^A$"
      sink: "^B$"
      demand: 50
workflow:
  - step_type: BuildGraph
"""
    )

    with patch("sys.stdout", new=Mock()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file)])

    out = "\n".join(str(c.args[0]) for c in mprint.call_args_list)
    assert "Capacity vs Demand:" in out
    assert "enabled link capacity: 100.0" in out
    assert "total demand (all matrices): 50.0" in out
    assert "capacity/demand: 2.00x" in out
    assert "demand/capacity: 50.00%" in out


def test_run_profile_uses_output_dir_profiles(tmp_path: Path, monkeypatch) -> None:
    # Minimal scenario
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
    out_dir = tmp_path / "outprof"
    res_path = out_dir / "res.json"
    monkeypatch.chdir(tmp_path)

    cli.main(
        [
            "run",
            str(scenario_file),
            "--profile",
            "--results",
            str(res_path),
            "-o",
            str(out_dir),
        ]
    )

    assert res_path.exists()
    # Worker profiles directory should be created under output dir, named '<prefix>.profiles'
    assert (out_dir / "p.profiles").exists()


def test_main_with_no_args_exits() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
