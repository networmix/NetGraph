"""Qualified scenario comparisons with immutable inputs and replayed failures.

The manifest supplies independent old/new command lines and frozen artifacts.
Each command writes the measurement protocol documented in dev/dev.md.
Run through the machine's heavy slot only during an owner-granted window.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def save(path, value):
    with Path(path).open("x") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def verify_artifacts(artifacts):
    if not artifacts:
        raise ValueError(
            "At least one frozen source/native/dependency artifact is required"
        )
    for name, expected in artifacts.items():
        path = Path(name)
        if not path.is_absolute() or digest(path) != expected:
            raise ValueError(f"Artifact hash mismatch: {name}")


def validate_manifest(manifest):
    if manifest.get("schema_version") != 1:
        raise ValueError("Expected manifest schema_version 1")
    verify_artifacts(manifest["artifacts"])
    names = set()
    for row in manifest["rows"]:
        name = row["name"]
        if (
            not isinstance(name, str)
            or not name
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name)
            or name in names
        ):
            raise ValueError("Rows require unique safe names")
        names.add(name)
        if row["boundary"] not in ("product_cli", "whole_process"):
            raise ValueError("Unknown measurement boundary")
        patterns = str(Path(row["patterns"]).resolve())
        if patterns not in manifest["artifacts"]:
            raise ValueError("Replay patterns must be frozen artifacts")
        if not finite_positive(row["timeout_seconds"]):
            raise ValueError("Expected positive finite timeout")
        if not row["output_selection"]:
            raise ValueError("Record the actual output selection")
        sides = row["sides"]
        if set(sides) not in ({"old", "new"}, {"new"}):
            raise ValueError(
                "A row needs old/new, or a separately budgeted new question"
            )
        if set(sides) == {"new"} and not finite_positive(row.get("budget_seconds")):
            raise ValueError("A new question requires an explicit budget")
        for side in sides.values():
            argv = side["argv"]
            if (
                not argv
                or not all(isinstance(arg, str) for arg in argv)
                or not Path(argv[0]).is_absolute()
                or "{report}" not in argv
                or "{patterns}" not in argv
                or not Path(side["cwd"]).is_absolute()
            ):
                raise ValueError(
                    "Use absolute executable/cwd and report/patterns arguments"
                )
            if not side["origins"] or not all(
                str(Path(path).resolve()) in manifest["artifacts"]
                for path in side["origins"].values()
            ):
                raise ValueError("Imported origins must be recorded and hash pinned")
            if not side.get("dependencies_sha256"):
                raise ValueError("Freeze the dependency inventory digest")
    if not names:
        raise ValueError("No scenario rows")


def machine_state():
    power = subprocess.check_output(
        ["/usr/bin/pmset", "-g", "batt"], text=True, timeout=5
    )
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "load": list(os.getloadavg()),
        "power": power,
    }


def qualify(state):
    loads = state["load"]
    if len(loads) != 3 or not all(
        type(value) in (int, float) and math.isfinite(value) and 0 <= value < 4
        for value in loads
    ):
        raise RuntimeError("All three load averages must be below 4")
    if "'AC Power'" not in state["power"]:
        raise RuntimeError("AC power required")


def validate_report(report, side, row, patterns_sha256):
    if type(report.get("exit_code")) is not int or report["exit_code"] != 0:
        raise ValueError("Child did not report normal completion")
    if not finite_positive(report.get("product_cli_seconds")):
        raise ValueError("Missing finite product CLI duration")
    if type(report.get("iterations")) is not int or report["iterations"] != 1:
        raise ValueError("Each child must execute exactly one complete scenario")
    if report.get("patterns_sha256") != patterns_sha256:
        raise ValueError("Failure replay differs")
    if report.get("origins") != side["origins"]:
        raise ValueError("Imported package/native origins differ")
    if report.get("dependencies_sha256") != side["dependencies_sha256"]:
        raise ValueError("Dependency inventory differs")
    if report.get("output_selection") != row["output_selection"]:
        raise ValueError("Output selection differs")
    if report.get("output_sha256") != side["output_sha256"]:
        raise ValueError("Result digest differs from the correctness-qualified output")


def stdout_digest(text, rules):
    """Validate exported JSON outside the measured child process."""
    if set(rules) - {"historical_step_times", "historical_failure_sets"}:
        raise ValueError("Unknown output digest normalization rule")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Scenario stdout must be a JSON object")
    if rules:
        steps = value.get("steps")
        if not isinstance(steps, dict):
            raise ValueError(
                "Historical digest rules require the historical steps mapping"
            )
        for step in steps.values():
            if "historical_step_times" in rules:
                for key in ("execution_time", "duration_sec"):
                    if key in step.get("metadata", {}):
                        step["metadata"][key] = "<volatile-duration>"
            if "historical_failure_sets" in rules:
                for case in step.get("data", {}).get("flow_results", []):
                    state = case.get("failure_state", {})
                    for key in ("excluded_nodes", "excluded_links"):
                        if key in state:
                            state[key] = sorted(state[key])
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def child_run(row, side_name, directory, deadline):
    side = row["sides"][side_name]
    directory.mkdir()
    before = machine_state()
    qualify(before)
    # A full declared timeout must fit. A deadline is never an implicit extension.
    if time.time() + row["timeout_seconds"] + 2 >= deadline:
        raise RuntimeError("Another complete child does not fit the granted window")
    report_path = directory / "measurement.json"
    argv = [
        arg.replace("{report}", str(report_path)).replace("{patterns}", row["patterns"])
        for arg in side["argv"]
    ]
    environment = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    record = {"argv": argv, "cwd": side["cwd"], "before": before, "side": side_name}
    with (
        (directory / "stdout.log").open("x") as stdout,
        (directory / "stderr.log").open("x") as stderr,
    ):
        started = time.perf_counter()
        process = subprocess.Popen(
            argv,
            cwd=side["cwd"],
            env=environment,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        record["pid"] = process.pid
        try:
            code = process.wait(timeout=row["timeout_seconds"])
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            record["timeout"] = True
            code = process.returncode
        record["whole_process_seconds"] = time.perf_counter() - started
        record["exit_code"] = code
        stdout.write(
            f"\nSUMMARY: child exit={code}; timeout={record.get('timeout', False)}\n"
        )
    record["after"] = machine_state()
    save(directory / "process.json", record)
    if code != 0 or record.get("timeout"):
        raise RuntimeError(f"Scenario child failed; evidence: {directory}")
    qualify(record["after"])
    report = json.loads(report_path.read_text())
    if side.get("stdout_json", False):
        report["output_sha256"] = stdout_digest(
            (directory / "stdout.log")
            .read_text()
            .split("\nSUMMARY: child exit=", 1)[0],
            side.get("output_digest_rules", []),
        )
    validate_report(report, side, row, digest(row["patterns"]))
    if report["product_cli_seconds"] > record["whole_process_seconds"]:
        raise ValueError("CLI duration exceeds the containing process duration")
    record["measurement"] = report
    record["seconds"] = (
        report["product_cli_seconds"]
        if row["boundary"] == "product_cli"
        else record["whole_process_seconds"]
    )
    return record


def compare(runs):
    old = [r["seconds"] for r in runs if r["side"] == "old"]
    new = [r["seconds"] for r in runs if r["side"] == "new"]
    result = {"new_median_seconds": statistics.median(new)}
    if old:
        result["old_median_seconds"] = statistics.median(old)
        result["ratio"] = result["new_median_seconds"] / result["old_median_seconds"]
        result["profile_required"] = result["ratio"] > 1.03
    return result


def execute(manifest, directory, mode, deadline, grant, repetitions, resume=None):
    validate_manifest(manifest)
    directory.mkdir()
    save(directory / "manifest.json", manifest)
    summary = {"grant": grant, "deadline_utc": deadline, "mode": mode, "rows": {}}
    try:
        completed = {}
        if resume is not None:
            if json.loads((resume / "manifest.json").read_text()) != manifest:
                raise ValueError("Resume manifest differs from the frozen input")
            previous = json.loads((resume / "summary.json").read_text())
            if previous["mode"] != mode:
                raise ValueError("Resume mode differs")
            completed = previous["rows"]
        for row in manifest["rows"]:
            if row["name"] in completed:
                summary["rows"][row["name"]] = {
                    **completed[row["name"]],
                    "reused_from": str(resume.resolve()),
                }
                continue
            runs = []
            if mode == "calibrate":
                # Two seconds of measured work per side; even a slow row runs once.
                for side in row["sides"]:
                    total, count = 0.0, 0
                    while total < 2:
                        record = child_run(
                            row,
                            side,
                            directory / f"{row['name']}-{side}-{count}",
                            deadline,
                        )
                        runs.append(record)
                        total += record["seconds"]
                        count += 1
            else:
                order = ("old", "new", "old") if "old" in row["sides"] else ("new",)
                for repetition in range(repetitions):
                    for index, side in enumerate(order):
                        runs.append(
                            child_run(
                                row,
                                side,
                                directory
                                / f"{row['name']}-{repetition}-{index}-{side}",
                                deadline,
                            )
                        )
            result = {"runs": runs, **compare(runs)}
            if mode == "calibrate":
                result["iteration_counts"] = {
                    side: sum(run["side"] == side for run in runs)
                    for side in row["sides"]
                }
            if "budget_seconds" in row:
                result["budget_met"] = (
                    result["new_median_seconds"] <= row["budget_seconds"]
                )
            summary["rows"][row["name"]] = result
            save(directory / f"{row['name']}-summary.json", result)
            verify_artifacts(manifest["artifacts"])
        summary["status"] = "measured"
    except BaseException as error:
        summary["status"] = "failed"
        summary["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        save(directory / "summary.json", summary)
        print(f"SUMMARY: {summary['status']}; evidence={directory}", flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate", "calibrate", "aba"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--grant", help="Owner's explicit quiet-window authorization")
    parser.add_argument(
        "--deadline", help="Granted window end, ISO8601 with UTC offset"
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--resume", type=Path, help="Reuse completed rows with identical manifest/mode"
    )
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    validate_manifest(manifest)
    if args.mode == "validate":
        print("SUMMARY: manifest and artifact hashes valid; no timing executed")
        return
    if not args.output or not args.grant or not args.deadline:
        parser.error("Timing requires --output, --grant and --deadline")
    deadline = datetime.fromisoformat(args.deadline)
    if deadline.tzinfo is None or deadline.timestamp() <= time.time():
        parser.error("Window deadline must be in the future with a UTC offset")
    if args.repetitions < 3:
        parser.error("At least three A/B/A repetitions are required")
    execute(
        manifest,
        args.output.resolve(),
        args.mode,
        deadline.timestamp(),
        args.grant,
        args.repetitions,
        args.resume,
    )


if __name__ == "__main__":
    main()
