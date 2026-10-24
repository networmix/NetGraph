"""CLI exports once, preserves real order when filtered, and replaces atomically."""

import json
from io import StringIO
from pathlib import Path

import pytest

from ngraph import Scenario, prepare, run, write_json
from ngraph.cli import _inspect_scenario, _run_scenario


def scenario(tmp_path):
    path = tmp_path / "sample.yaml"
    path.write_text("""
seed: 42
network: {nodes: {a: {}, b: {}}, links: [{source: a, target: b, capacity: 5, cost: 2}]}
workflow:
  - {type: BuildGraph, name: first}
  - {type: NetworkStats, name: second}
""")
    return path


def test_filter_only_second_keeps_actual_order_one_and_one_encoder(
    tmp_path, monkeypatch, capsys
):
    import ngraph.export as export

    original = export._encode_json
    calls = []

    def encode(result):
        calls.append(result)
        return original(result)

    monkeypatch.setattr(export, "_encode_json", encode)
    output = tmp_path / "result.json"
    _run_scenario(scenario(tmp_path), output, False, True, keys=["second"])
    captured = capsys.readouterr()
    wire = json.loads(captured.out)
    assert wire == json.loads(output.read_text())
    assert len(calls) == 1
    assert [(step["name"], step["execution_order"]) for step in wire["steps"]] == [
        ("second", 1)
    ]
    assert wire["steps"][0]["result"]["total_capacity"] == 5
    assert not list(tmp_path.glob(".result.json.*.tmp"))


def test_results_are_one_compact_line_in_the_file_on_stdout_and_from_write_json(
    tmp_path, capsys
):
    path = tmp_path / "zürich.yaml"
    path.write_text(
        "network: {nodes: {zürich: {}, b: {}}, links: [{source: zürich, target: b}]}\n"
        "workflow: [{type: NetworkStats, name: stats}]\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.json"
    _run_scenario(path, output, False, True)
    library = StringIO()
    write_json(
        run(prepare(Scenario.from_yaml(path.read_text(encoding="utf-8")))), library
    )
    texts = {
        "file": output.read_text(encoding="utf-8"),
        "stdout": capsys.readouterr().out,
        "write_json": library.getvalue(),
    }
    for where, text in texts.items():
        # No indentation or spaces after separators; key order and raw non-ASCII kept.
        compact = json.dumps(
            json.loads(text), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        assert text == compact + "\n", where
        assert "zürich" in text, where
    assert texts["file"] == texts["stdout"]


@pytest.mark.parametrize("failure", ["encoder", "replace"])
def test_output_failure_leaves_destination_and_removes_temporary_then_retries(
    tmp_path, monkeypatch, failure
):
    import ngraph.cli as cli
    import ngraph.export as export

    path = scenario(tmp_path)
    output = tmp_path / "result.json"
    output.write_text("previous")
    with monkeypatch.context() as patch:

        def fail(*args):
            raise OSError("injected publication failure")

        patch.setattr(
            export, "_encode_json", fail
        ) if failure == "encoder" else patch.setattr(cli.os, "replace", fail)
        with pytest.raises(SystemExit) as error:
            _run_scenario(path, output, False, False)
        assert error.value.code == 1
    assert output.read_text() == "previous"
    assert not list(tmp_path.glob(".result.json.*.tmp"))
    _run_scenario(path, output, False, False)
    assert [s["execution_order"] for s in json.loads(output.read_text())["steps"]] == [
        0,
        1,
    ]


def test_inspect_typed_inputs_and_profile_step_hook_keep_stdout_json(tmp_path, capsys):
    path = scenario(tmp_path)
    _inspect_scenario(path, detail=True)
    inspection = capsys.readouterr()
    assert (
        "INSPECTION COMPLETE" in inspection.out
        and "NETWORK STRUCTURE" in inspection.out
    )
    _run_scenario(path, None, True, True, profile=True, profile_memory=True)
    captured = capsys.readouterr()
    assert len(json.loads(captured.out)["steps"]) == 2
    assert "PERFORMANCE" in captured.err.upper()


def test_unknown_key_filter_refuses_before_run_with_valid_control(tmp_path, capsys):
    path = scenario(tmp_path)
    with pytest.raises(SystemExit):
        _run_scenario(path, None, True, True, keys=["missing"])
    assert "Unknown step name(s)" in capsys.readouterr().err
    _run_scenario(path, None, True, True, keys=["second", "first"])
    assert [s["name"] for s in json.loads(capsys.readouterr().out)["steps"]] == [
        "first",
        "second",
    ]


def test_output_file_write_failure_is_atomic(tmp_path, monkeypatch):
    path = scenario(tmp_path)
    output = tmp_path / "result.json"
    output.write_text("previous")
    import ngraph.cli as cli

    original = cli.os.fdopen

    class Broken:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            return self

        def write(self, text):
            self.file.write(text[:10])
            raise OSError("partial write")

        def __exit__(self, *args):
            self.file.close()

    with monkeypatch.context() as patch:
        patch.setattr(cli.os, "fdopen", lambda *a, **kw: Broken(original(*a, **kw)))
        with pytest.raises(SystemExit):
            _run_scenario(path, output, False, False)
    assert output.read_text() == "previous"
    assert {p.name for p in tmp_path.iterdir()} == {path.name, output.name}
    _run_scenario(path, output, False, False)
    assert json.loads(Path(output).read_text())["steps"][1]["name"] == "second"
