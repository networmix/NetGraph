import json
from pathlib import Path

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
