"""Qualification and replay tests use fake measurements, never a timing window."""

import json
import subprocess
from copy import deepcopy

import pytest

from dev import scenario_perf as perf


@pytest.fixture
def manifest(tmp_path):
    patterns = tmp_path / "patterns.json"
    patterns.write_text('{"cases": []}')
    native = tmp_path / "native.so"
    native.write_bytes(b"frozen native bytes")
    side = {
        "argv": ["/usr/bin/python3", "worker.py", "{report}", "{patterns}"],
        "cwd": str(tmp_path),
        "origins": {"_netgraph_core": str(native)},
        "dependencies_sha256": "d" * 64,
        "output_sha256": "e" * 64,
    }
    return {
        "schema_version": 1,
        "artifacts": {str(p): perf.digest(p) for p in (patterns, native)},
        "rows": [
            {
                "name": "square-mesh",
                "boundary": "product_cli",
                "patterns": str(patterns),
                "timeout_seconds": 30,
                "output_selection": "full declared outputs",
                "sides": {"old": deepcopy(side), "new": deepcopy(side)},
            }
        ],
    }


def report(manifest):
    row = manifest["rows"][0]
    side = row["sides"]["new"]
    return {
        "exit_code": 0,
        "product_cli_seconds": 0.25,
        "iterations": 1,
        "patterns_sha256": perf.digest(row["patterns"]),
        "origins": side["origins"],
        "dependencies_sha256": side["dependencies_sha256"],
        "output_selection": row["output_selection"],
        "output_sha256": side["output_sha256"],
    }


def test_manifest_accepts_frozen_comparison_and_rejects_artifact_drift(manifest):
    perf.validate_manifest(manifest)
    name = next(iter(manifest["artifacts"]))
    manifest["artifacts"][name] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        perf.validate_manifest(manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("boundary", "solver-only"),
        ("name", "../outside"),
        ("timeout_seconds", 0),
        ("timeout_seconds", float("inf")),
        ("output_selection", ""),
        ("patterns", "/unfrozen.json"),
    ],
)
def test_manifest_refuses_unqualified_rows_with_valid_control(manifest, field, value):
    perf.validate_manifest(manifest)
    manifest["rows"][0][field] = value
    with pytest.raises(ValueError):
        perf.validate_manifest(manifest)


def test_new_question_has_separate_budget_and_not_an_invented_old_comparator(manifest):
    row = manifest["rows"][0]
    del row["sides"]["old"]
    with pytest.raises(ValueError, match="explicit budget"):
        perf.validate_manifest(manifest)
    row["budget_seconds"] = 1
    perf.validate_manifest(manifest)


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("invalid", [4, 4.01, -1, float("nan"), float("inf"), True])
def test_all_three_load_averages_must_qualify(index, invalid):
    state = {"load": [0.5, 0.5, 0.5], "power": "Now drawing from 'AC Power'"}
    perf.qualify(state)
    state["load"][index] = invalid
    with pytest.raises(RuntimeError, match="three load"):
        perf.qualify(state)


def test_battery_refuses_despite_low_load():
    with pytest.raises(RuntimeError, match="AC power"):
        perf.qualify({"load": [0, 0, 0], "power": "Now drawing from 'Battery Power'"})


@pytest.mark.parametrize(
    "field,value",
    [
        ("exit_code", 1),
        ("exit_code", False),
        ("product_cli_seconds", 0),
        ("product_cli_seconds", float("nan")),
        ("product_cli_seconds", True),
        ("iterations", True),
        ("iterations", 2),
        ("patterns_sha256", "wrong replay"),
        ("origins", {"_netgraph_core": "/published/native.so"}),
        ("dependencies_sha256", "drift"),
        ("output_selection", "different outputs"),
        ("output_sha256", "wrong result"),
    ],
)
def test_child_protocol_requires_correct_replay_output_origins_and_completion(
    manifest, field, value
):
    row = manifest["rows"][0]
    side = row["sides"]["new"]
    valid = report(manifest)
    perf.validate_report(valid, side, row, valid["patterns_sha256"])
    invalid = {**valid, field: value}
    with pytest.raises(ValueError):
        perf.validate_report(invalid, side, row, valid["patterns_sha256"])


def test_order_ratios_and_calibration_iteration_counts_without_timing(
    manifest, monkeypatch, tmp_path
):
    calls = []

    def child(row, side, directory, deadline):
        calls.append(side)
        return {"side": side, "seconds": 0.5 if side == "old" else 1}

    monkeypatch.setattr(perf, "child_run", child)
    result = perf.execute(manifest, tmp_path / "aba", "aba", 1e10, "test fake", 3)
    assert calls == ["old", "new", "old"] * 3
    row = result["rows"]["square-mesh"]
    assert row["ratio"] == 2 and row["profile_required"] is True
    assert row["old_median_seconds"] == 0.5 and row["new_median_seconds"] == 1
    calls.clear()
    result = perf.execute(manifest, tmp_path / "cal", "calibrate", 1e10, "test fake", 3)
    assert calls == ["old"] * 4 + ["new"] * 2
    assert result["rows"]["square-mesh"]["iteration_counts"] == {"old": 4, "new": 2}


def test_failed_child_propagates_and_saves_failure_record(
    manifest, monkeypatch, tmp_path
):
    def failed(*args):
        raise RuntimeError("child timeout witness")

    monkeypatch.setattr(perf, "child_run", failed)
    destination = tmp_path / "failure"
    with pytest.raises(RuntimeError, match="timeout witness"):
        perf.execute(manifest, destination, "aba", 1e10, "fake", 3)
    saved = json.loads((destination / "summary.json").read_text())
    assert saved["status"] == "failed" and "timeout witness" in saved["error"]


def test_validation_mode_never_starts_a_measurement(manifest, monkeypatch, tmp_path):
    def forbidden(*args):
        pytest.fail("validate must not measure")

    monkeypatch.setattr(perf, "child_run", forbidden)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    perf.main(["validate", str(path)])
    with pytest.raises(SystemExit) as error:
        perf.main(["aba", str(path)])
    assert error.value.code == 2


@pytest.mark.parametrize("outcome", ["ok", "failure", "timeout"])
def test_process_protocol_records_child_exit_and_timeout_with_success_control(
    manifest, monkeypatch, tmp_path, outcome
):
    row = manifest["rows"][0]
    monkeypatch.setattr(
        perf,
        "machine_state",
        lambda: {"load": [0, 0, 0], "power": "'AC Power'"},
    )
    monkeypatch.setattr(perf.time, "time", lambda: 100)
    clocks = iter((10.0, 11.0))
    monkeypatch.setattr(perf.time, "perf_counter", lambda: next(clocks))
    signals = []
    monkeypatch.setattr(perf.os, "killpg", lambda *args: signals.append(args))

    class Process:
        pid = 12345
        returncode = None

        def __init__(self, argv, **kwargs):
            self.waits = 0
            assert kwargs["start_new_session"] is True
            assert "PYTHONPATH" not in kwargs["env"]
            assert "PYTHONHOME" not in kwargs["env"]
            assert "{patterns}" not in argv and row["patterns"] in argv
            perf.save(argv[2], report(manifest))

        def wait(self, timeout):
            self.waits += 1
            if outcome == "timeout" and self.waits == 1:
                raise subprocess.TimeoutExpired("frozen child", timeout)
            self.returncode = (
                0 if outcome == "ok" else -15 if outcome == "timeout" else 7
            )
            return self.returncode

    monkeypatch.setattr(perf.subprocess, "Popen", Process)
    destination = tmp_path / outcome
    if outcome == "ok":
        value = perf.child_run(row, "new", destination, 1000)
        assert value["seconds"] == 0.25 and value["whole_process_seconds"] == 1
        assert not signals
    else:
        with pytest.raises(RuntimeError, match="Scenario child failed"):
            perf.child_run(row, "new", destination, 1000)
        assert bool(signals) == (outcome == "timeout")
    process = json.loads((destination / "process.json").read_text())
    assert process["exit_code"] == (
        0 if outcome == "ok" else -15 if outcome == "timeout" else 7
    )
    assert process.get("timeout", False) == (outcome == "timeout")


def test_window_deadline_refuses_before_starting_a_child(
    manifest, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        perf, "machine_state", lambda: {"load": [0, 0, 0], "power": "'AC Power'"}
    )
    monkeypatch.setattr(perf.time, "time", lambda: 100)

    def forbidden(*args, **kwargs):
        pytest.fail("expired window must not start a child")

    monkeypatch.setattr(perf.subprocess, "Popen", forbidden)
    with pytest.raises(RuntimeError, match="does not fit"):
        perf.child_run(manifest["rows"][0], "new", tmp_path / "deadline", 131)


def test_resume_reuses_only_completed_identical_rows(manifest, monkeypatch, tmp_path):
    calls = []

    def child(row, side, directory, deadline):
        calls.append(side)
        return {"side": side, "seconds": 1}

    monkeypatch.setattr(perf, "child_run", child)
    first = tmp_path / "first"
    expected = perf.execute(manifest, first, "aba", 1e10, "fake", 3)
    assert len(calls) == 9
    calls.clear()
    result = perf.execute(manifest, tmp_path / "resumed", "aba", 1e10, "fake", 3, first)
    assert not calls
    assert (
        result["rows"]["square-mesh"]["runs"] == expected["rows"]["square-mesh"]["runs"]
    )
    assert result["rows"]["square-mesh"]["reused_from"] == str(first)
    changed = deepcopy(manifest)
    changed["rows"][0]["output_selection"] = "minimal"
    with pytest.raises(ValueError, match="manifest differs"):
        perf.execute(changed, tmp_path / "drift", "aba", 1e10, "fake", 3, first)
    with pytest.raises(ValueError, match="mode differs"):
        perf.execute(manifest, tmp_path / "mode", "calibrate", 1e10, "fake", 3, first)


def test_parent_digest_preserves_numbers_and_sequence_order():
    base = {"metadata": {}, "steps": [{"result": {"amounts": [1, 2]}}]}
    expected = perf.stdout_digest(json.dumps(base), [])
    assert perf.stdout_digest(json.dumps(base, indent=2), []) == expected
    base["steps"][0]["result"]["amounts"].reverse()
    assert perf.stdout_digest(json.dumps(base), []) != expected
    with pytest.raises(ValueError):
        perf.stdout_digest("[]", [])
    with pytest.raises(ValueError):
        perf.stdout_digest("{}", ["erase-all"])


def test_historical_only_normalization_keeps_all_flow_values():
    a = {
        "steps": {
            "x": {
                "metadata": {"duration_sec": 1, "execution_time": 2},
                "data": {
                    "flow_results": [
                        {
                            "failure_state": {"excluded_links": ["b", "a"]},
                            "flows": [4, 7],
                        }
                    ]
                },
            }
        }
    }
    b = json.loads(json.dumps(a))
    b["steps"]["x"]["metadata"]["duration_sec"] = 3
    b["steps"]["x"]["data"]["flow_results"][0]["failure_state"][
        "excluded_links"
    ].reverse()
    rules = ["historical_step_times", "historical_failure_sets"]
    assert perf.stdout_digest(json.dumps(a), rules) == perf.stdout_digest(
        json.dumps(b), rules
    )
    b["steps"]["x"]["data"]["flow_results"][0]["flows"][0] += 1
    assert perf.stdout_digest(json.dumps(a), rules) != perf.stdout_digest(
        json.dumps(b), rules
    )
