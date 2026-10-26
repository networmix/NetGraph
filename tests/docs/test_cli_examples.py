"""Every documented shell command runs as shown and gives what its page says.

The commands of each page run in order in one reader's working directory (the bundled
scenarios and the files the pages ask to save). `ngraph` runs in this process, and
`python -m ngraph` as this interpreter's module; `jq` and `grep` run as programs and read
the output piped into them. A shell fence followed by an output fence prints that output
with its last command. The commands that set up an environment (install, clone, change
directory) and `make` are not run here.
"""

import contextlib
import io
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ngraph import Scenario
from ngraph.cli import main
from tests.docs.pages import ROOT, fences, pages, stated, workspace

NOT_RUN = {
    "pip": "installs packages",
    "python": "creates a virtual environment",
    "source": "activates a virtual environment",
    "git": "clones the repositories",
    "cd": "changes directory between the clones",
    "make": "runs the repository's validation, a gate of its own",
}


def commands(page):
    """(where, text, programs, fence line) per command of a page's bash fences:
    continuation lines joined, comments dropped, a pipeline split into its programs."""
    found = []
    for block in fences(page):
        if block.lang != "bash":
            continue
        lines, index = block.text.splitlines(), 0
        while index < len(lines):
            start, text = index, lines[index]
            while text.endswith("\\") or not quotes_closed(text):
                index += 1
                text = (
                    text[:-1] + " " + lines[index].strip()
                    if text.endswith("\\")
                    else text + "\n" + lines[index]
                )
            index += 1
            text = text.split("  #")[0].strip()
            if not text or text.startswith("#"):
                continue
            lexer = shlex.shlex(text, posix=True, punctuation_chars="|")
            lexer.whitespace_split = True
            programs = [[]]
            for token in lexer:
                if token == "|":
                    programs.append([])
                else:
                    programs[-1].append(token)
            found.append(
                (f"{page}:{block.line + 1 + start}", text, programs, block.line)
            )
    return found


def shown_outputs(page):
    """{bash fence line: the output fence after it}, for each bash fence the page follows
    with what its last command prints."""
    found = fences(page)
    return {
        block.line: after.text
        for block, after in zip(found, found[1:], strict=False)
        if block.lang == "bash" and after.marker == "output"
    }


def program(argv):
    """The program a command runs; `python -m ngraph` is the ngraph command line."""
    return "python -m ngraph" if argv[:3] == ["python", "-m", "ngraph"] else argv[0]


def quotes_closed(text):
    try:
        shlex.split(text, comments=True)
    except ValueError:
        return False
    return True


def run_command(programs, cwd):
    """Run one pipeline; returns the last program's stdout and the exit status."""
    data, status = None, 0
    for argv in programs:
        if program(argv) == "python -m ngraph":
            done = subprocess.run(
                [sys.executable, "-m", "ngraph", *argv[3:]],
                capture_output=True,
                text=True,
                cwd=cwd,
                check=False,
            )
            data, status = done.stdout, done.returncode
        elif argv[0] == "ngraph":
            out, err = io.StringIO(), io.StringIO()
            level = logging.getLogger("ngraph").level
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    main(argv[1:])
            except SystemExit as stop:
                status = stop.code or 0
            finally:
                logging.getLogger("ngraph").setLevel(level)
            data = out.getvalue()
        else:
            if shutil.which(argv[0]) is None:
                if os.environ.get("CI"):
                    pytest.fail(f"{argv[0]} is not installed")
                pytest.skip(f"{argv[0]} is not installed")
            done = subprocess.run(
                argv, input=data, capture_output=True, text=True, cwd=cwd, check=False
            )
            data, status = done.stdout, done.returncode
        if status:
            break
    return data, status


TUTORIAL = "docs/getting-started/tutorial.md"
INSTALL = "docs/getting-started/installation.md"
CLOS = "docs/examples/clos-fabric.md"
BUNDLED = "docs/examples/bundled-scenarios.md"
CLI = "docs/reference/cli.md"
PAGES = tuple(page for page in pages() if commands(page))


def scenario_step(name, step):
    text = (Path(__file__).resolve().parents[2] / "scenarios" / name).read_text()
    return next(s for s in yaml.safe_load(text)["workflow"] if s["name"] == step)


def metros(name):
    text = (Path(__file__).resolve().parents[2] / "scenarios" / name).read_text()
    nodes = Scenario.from_yaml(text).network.nodes
    return sorted({node.split("/")[0] for node in nodes})


def step_names(out):
    return [step["name"] for step in json.loads(out)["steps"]]


def lines(out):
    return [json.loads(line) for line in out.splitlines()]


def filtered_order(out, d):
    (order,) = stated(CLOS, r"execution order, (\d+)")
    steps = json.loads(out)["steps"]
    return [(s["name"], s["execution_order"]) for s in steps] == [
        ("equal_shortest_capacity", int(order))
    ]


def matrix_rows(out, d):
    (rows,) = stated(BUNDLED, r"capacity matrix: (\d+) rows")
    return out == rows + "\n"


# What the pages say a command gives: (page, command text) -> check(stdout, directory).
STATED = {
    ("README.md", 'select(.name == "max_demand")'): lambda out, d: (
        type(json.loads(out)) in (int, float) and json.loads(out) > 0
    ),
    (INSTALL, "python -m ngraph --help"): lambda out, d: out.startswith(
        "usage: ngraph "
    ),
    (TUTORIAL, "ngraph run example.yaml --output results/"): lambda out, d: (
        (d / "results/example.results.json").is_file()
    ),
    (TUTORIAL, "ngraph run example.yaml --stdout --no-results"): lambda out, d: (
        step_names(out) == ["ideal_capacity", "supported_load", "under_failures"]
    ),
    (CLOS, "--keys equal_shortest_capacity --stdout"): filtered_order,
    (BUNDLED, "--keys network_statistics tm_placement --results clos_filtered.json"): (
        lambda out, d: step_names((d / "clos_filtered.json").read_text())
        == ["network_statistics", "tm_placement"]
    ),
    (BUNDLED, "{alpha_feasible, search_status, history}"): lambda out, d: (
        set(json.loads(out)) == {"alpha_feasible", "search_status", "history"}
    ),
    (BUNDLED, "ratio: .states.converged.totals.delivery_ratio}"): lambda out, d: (
        all(set(line) == {"links", "n", "ratio"} for line in lines(out))
        and sum(line["n"] for line in lines(out))
        == scenario_step("square_mesh.yaml", "tm_placement")["iterations"]
    ),
    (BUNDLED, ".rows | length"): matrix_rows,
    (BUNDLED, "{path, capex_total, power_total_watts}"): lambda out, d: (
        [line["path"] for line in lines(out)] == metros("backbone_clos.yml")
    ),
    (CLI, "ngraph run scenarios/square_mesh.yaml"): lambda out, d: (
        (d / stated(CLI, r"# Run a scenario \(creates (\S+) by default\)")[0]).is_file()
    ),
    (CLI, "--results analysis.json --stdout"): lambda out, d: (
        json.loads(out) == json.loads((d / "analysis.json").read_text())
    ),
    (CLI, "ngraph run scenarios/nsfnet.yaml --no-results"): lambda out, d: (
        not (d / "nsfnet.results.json").exists()
    ),
    (CLI, "--keys msd_baseline --stdout"): lambda out, d: (
        step_names(out) == ["msd_baseline"]
    ),
    (CLI, '| grep -A 5 "WORKFLOW STEPS"'): lambda out, d: (
        out.splitlines()[0].endswith(". WORKFLOW STEPS")
    ),
}


def test_every_command_is_run_or_named_as_not_run():
    seen = set()
    for page in pages():
        for where, _, programs, _ in commands(page):
            name = program(programs[0])
            assert name in {"ngraph", "python -m ngraph", "jq"} | set(NOT_RUN), where
            seen.add(name)
    assert seen >= {"ngraph", "python -m ngraph", "jq", *NOT_RUN}
    assert {page for page, _ in STATED} <= set(PAGES)


@pytest.mark.timeout(120)
@pytest.mark.parametrize("page", PAGES)
def test_documented_commands_run_and_give_what_the_page_states(page, tmp_path):
    directory = workspace(tmp_path)
    previous = Path.cwd()
    os.chdir(directory)
    try:
        checked, printed = set(), {}
        for where, text, programs, line in commands(page):
            if program(programs[0]) in NOT_RUN:
                continue
            out, status = run_command(programs, directory)
            assert status == 0, f"{where}: {text}"
            printed[line] = out
            for (stated_page, excerpt), check in STATED.items():
                if stated_page == page and excerpt in text:
                    assert check(out, directory), f"{where}: {text}"
                    checked.add(excerpt)
        assert checked == {excerpt for p, excerpt in STATED if p == page}
        for line, shown in shown_outputs(page).items():
            assert printed[line] == shown, f"{page}:{line}"
    finally:
        os.chdir(previous)


def test_every_shown_shell_output_is_compared():
    """Every output fence that follows a bash fence is one the command test compares."""
    shown = sum(len(shown_outputs(page)) for page in pages())
    text = "".join((ROOT / page).read_text() for page in pages())
    written = re.findall(
        r"```bash\n(?:(?!```).*\n)*```\n\n<!-- example: output -->", text
    )
    assert shown == len(written) > 0


def test_a_filtered_export_keeps_the_execution_order(tmp_path, monkeypatch):
    """Tutorial: `--keys under_failures` keeps the step's stated execution order."""
    (order,) = stated(TUTORIAL, r"`--keys under_failures`.* execution order (\d+)")
    monkeypatch.chdir(workspace(tmp_path))
    command = "ngraph run example.yaml --keys under_failures --stdout --no-results"
    out, status = run_command([command.split()], tmp_path)
    assert status == 0
    steps = json.loads(out)["steps"]
    assert [(s["name"], s["execution_order"]) for s in steps] == [
        ("under_failures", int(order))
    ]
