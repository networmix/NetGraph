"""`ngraph inspect`: selector previews through the selector engine, one entry per
whole selector, one meaning of an enabled link, step names and step parameters.

A preview line reads `<label>: G groups, N nodes (E enabled)`: the label is the
selector's path (`*` without one) followed by its other parts; N counts every node
the selector matches with its active filter lifted, E the enabled ones among them.
"""

from __future__ import annotations

import contextlib
import io
from enum import Enum
from pathlib import Path

import pytest

from ngraph import cli
from ngraph.model.demand import FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Condition, MatchSpec, Selector
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.network_stats import NetworkStats
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement

ROOT = Path(__file__).resolve().parents[2]


def _cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cli.main(argv)
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def _inspect(tmp_path, text, *flags):
    path = tmp_path / "s.yaml"
    path.write_text(text)
    code, out, _ = _cli(["--quiet", "inspect", str(path), *flags])
    assert code == 0
    return [line.strip() for line in out.splitlines()]


def _table_row(lines, first_cell, width):
    """Rows of the tables with ``width`` columns whose first cell is ``first_cell``."""
    rows = [[c.strip() for c in line.split("|")] for line in lines if "|" in line]
    return [row for row in rows if row[0] == first_cell and len(row) == width]


W7 = """
seed: 1
network:
  nodes:
    A1: {attrs: {role: edge}}
    A2: {attrs: {role: core}}
    B1: {attrs: {role: edge}}
    B2: {attrs: {role: core}, disabled: true}
  links:
    - {source: A1, target: B1, capacity: 10}
    - {source: A2, target: B2, capacity: 10}
demands:
  d:
    - source: {path: "^A", match: {conditions: [{attr: role, op: "==", value: edge}]}}
      target: {group_by: role}
      volume: 1
workflow:
  - type: NetworkStats
  - type: MaxFlow
    name: mf
    source: {path: "^A", match: {conditions: [{attr: role, op: "==", value: edge}]}}
    target: "^B"
"""


def test_previews_apply_conditions_and_group_by(tmp_path):
    """L3: the engine counts what an analysis selects (path-only matching counted 2 and 0)."""
    lines = _inspect(tmp_path, W7)
    assert "source ^A [match: role == edge]: 1 groups, 1 nodes (1 enabled)" in lines
    assert "target * [group_by: role]: 2 groups, 4 nodes (3 enabled)" in lines
    assert (
        "2. mf: source: 1 groups, 1 nodes (1 enabled); "
        "target: 1 groups, 2 nodes (1 enabled)"
    ) in lines


SHARED_PATH = """
network:
  nodes:
    A1: {attrs: {role: edge, tier: 1}}
    A2: {attrs: {role: core, tier: 2}}
    A3: {attrs: {role: core, tier: 1}, disabled: true}
    B1: {}
demands:
  d:
"""


def _demands(*matches):
    entries = "".join(
        f'    - {{source: {{path: "^A", match: {m}}}, target: "^B", volume: 1}}\n'
        for m in matches
    )
    return SHARED_PATH + entries


def _cond(attr, op, value):
    return f'{{attr: {attr}, op: "{op}", value: {value}}}'


def test_selectors_sharing_a_path_stay_apart(tmp_path):
    """L3b (i): one entry per whole selector."""
    text = _demands(
        f"{{conditions: [{_cond('role', '==', 'edge')}]}}",
        f"{{conditions: [{_cond('role', '==', 'core')}]}}",
    )
    lines = _inspect(tmp_path, text)
    assert "source ^A [match: role == edge]: 1 groups, 1 nodes (1 enabled)" in lines
    assert "source ^A [match: role == core]: 1 groups, 2 nodes (1 enabled)" in lines
    assert "target ^B: 1 groups, 1 nodes (1 enabled)" in lines
    detail = _inspect(tmp_path, text, "--detail")
    assert "unique source patterns: 2; unique target patterns: 1" in detail
    assert _table_row(detail, "^A [match: role == edge]", 7) == [
        ["^A [match: role == edge]", "^B", "1", "1", "1g/1n (1e)", "1g/1n (1e)", "^A"]
    ]
    assert _table_row(detail, "^A [match: role == core]", 7) == [
        ["^A [match: role == core]", "^B", "1", "1", "1g/2n (1e)", "1g/1n (1e)", "^A"]
    ]


def test_list_values_and_two_conditions(tmp_path):
    """L3b (ii): `in` lists (unhashable) and two-condition specs keep five entries."""
    text = _demands(
        f"{{conditions: [{_cond('role', '==', 'edge')}]}}",
        f"{{conditions: [{_cond('role', 'in', '[edge, core]')}]}}",
        f"{{conditions: [{_cond('role', 'in', '[edge]')}]}}",
        f"{{logic: or, conditions: [{_cond('role', '==', 'edge')}, {_cond('tier', '==', 1)}]}}",
        f"{{logic: and, conditions: [{_cond('role', '==', 'core')}, {_cond('tier', '==', 1)}]}}",
    )
    lines = _inspect(tmp_path, text)
    sources = [line for line in lines if line.startswith("source ")]
    assert sources == [
        "source ^A [match: role == edge]: 1 groups, 1 nodes (1 enabled)",
        "source ^A [match: role in [edge, core]]: 1 groups, 3 nodes (2 enabled)",
    ]
    detail = _inspect(tmp_path, text, "--detail")
    assert "unique source patterns: 5; unique target patterns: 1" in detail
    expected = {
        "^A [match: role == edge]": "1g/1n (1e)",
        "^A [match: role in [edge, core]]": "1g/3n (2e)",
        "^A [match: role in [edge]]": "1g/1n (1e)",
        "^A [match: role == edge or tier == 1]": "1g/2n (1e)",
        "^A [match: role == core and tier == 1]": "1g/1n (0e)",
    }
    for label, match in expected.items():
        (row,) = _table_row(detail, label, 7)
        assert row[2:5] == ["1", "1", match]


def test_an_explicit_active_only_false_is_labelled(tmp_path):
    """L3c: all matches and the enabled ones, the flag in the label."""
    text = (
        SHARED_PATH
        + '    - {source: {path: "^A", active_only: false}, target: "^B", volume: 1}\n'
    )
    lines = _inspect(tmp_path, text)
    assert "source ^A [active_only: false]: 1 groups, 3 nodes (2 enabled)" in lines
    assert not any("selected" in line for line in lines)


def test_every_selector_valued_step_field_is_previewed():
    """L4: Selector fields of any name; plain strings are not selectors."""

    class Custom:
        def __init__(self):
            self.name = "c"
            self.via = Selector("^A")
            self.x_path = "^A"
            self._hidden = Selector("^A")

    net = Network()
    net.add_node(Node("A1"))
    net.add_node(Node("A2", disabled=True))
    summary = cli._summarize_node_matches(Custom(), net)
    assert summary == {
        "via": {
            "label": "^A",
            "groups": 1,
            "nodes": 2,
            "enabled_nodes": 1,
            "labels": ["^A"],
        }
    }


@pytest.mark.parametrize("flags", [(), ("--detail",)])
def test_an_invalid_regex_is_refused_where_it_is_declared(tmp_path, flags):
    """A pattern is checked where it is given: the load names it; exit 1."""
    text = (
        "network:\n  nodes: {A: {}, B: {}}\n  links: [{source: A, target: B, capacity: 1}]\n"
        'demands:\n  d: [{source: "[", target: "^B", volume: 1}]\n'
        "workflow: [{type: NetworkStats, name: s}]\n"
    )
    path = tmp_path / "s.yaml"
    path.write_text(text)
    code, out, err = _cli(["--quiet", "inspect", str(path), *flags])
    assert code == 1
    assert "demands.d[0].source.path: invalid pattern '['" in out + err
    # Control: a valid pattern inspects.
    _inspect(tmp_path, text.replace('source: "["', 'source: "^A"'), *flags)


def test_a_selection_failure_other_than_a_regex_is_reported(tmp_path):
    """A group key too long to write as text (16,001 bits) is an ERROR preview; exit 0."""
    try:
        str(1 << 16000)
    except ValueError as exc:
        reason = f"ValueError: {exc}"
    text = (
        f"network:\n  nodes:\n    A: {{attrs: {{role: 0x1{'0' * 4000}}}}}\n    B: {{}}\n"
        'demands:\n  d: [{source: {group_by: role}, target: "^B", volume: 1}]\n'
    )
    lines = _inspect(tmp_path, text)
    assert f"source * [group_by: role]: ERROR {reason}" in lines
    detail = _inspect(tmp_path, text, "--detail")
    assert _table_row(detail, "* [group_by: role]", 7) == [
        ["* [group_by: role]", "^B", "1", "1", f"ERROR {reason}", "1g/1n (1e)", "-"]
    ]


def test_a_wide_json_integer_is_compared_exactly_in_the_preview(tmp_path):
    """A positive wide integer selects its node without a float conversion."""
    text = (
        f"network:\n  nodes:\n    A: {{attrs: {{size: 1{'0' * 309}}}}}\n    B: {{}}\n"
        "demands:\n  d:\n"
        '    - {source: {path: "^A", match: {conditions: [{attr: size, op: ">", value: 5}]}}, '
        'target: "^B", volume: 1}\n'
    )
    label = "^A [match: size > 5]"
    lines = _inspect(tmp_path, text)
    assert f"source {label}: 1 groups, 1 nodes (1 enabled)" in lines
    detail = _inspect(tmp_path, text, "--detail")
    assert _table_row(detail, label, 7) == [
        [label, "^B", "1", "1", "1g/1n (1e)", "1g/1n (1e)", "^A"]
    ]


def test_unnamed_steps_run_and_print_under_one_name(tmp_path):
    """L6: YAML names an unnamed step `<type>_<index>`; --keys and inspect use it."""
    lines = _inspect(tmp_path, W7)
    assert _table_row(lines, "1", 4) == [
        ["1", "NetworkStats_0", "NetworkStats", "deterministic"]
    ]
    path = tmp_path / "s.yaml"
    code, _, _ = _cli(
        ["--quiet", "run", str(path), "--no-results", "--keys", "NetworkStats_0"]
    )
    assert code == 0
    code, _, err = _cli(
        ["--quiet", "run", str(path), "--no-results", "--keys", "NetworkStats"]
    )
    assert code == 1 and "Unknown step name(s) in --keys: NetworkStats" in err


def test_a_python_built_subclass_is_labelled_by_its_class():
    """L6: an unnamed step's refusal names its own class."""

    class MyTMP(TrafficMatrixPlacement):
        pass

    with pytest.raises(ValueError) as exc:
        MyTMP(demand_set="d", interaction="x")  # type: ignore[arg-type]
    assert str(exc.value) == (
        "workflow.MyTMP.interaction: expected ordered or simultaneous, got 'x'"
    )


@pytest.mark.parametrize(("source", "target"), [("a", "b"), ("b", "a")])
def test_enabled_links_need_both_end_nodes(tmp_path, source, target):
    """L10: a flag-enabled capacity-7 link to or from disabled b is not enabled, in
    the overview, the link and node tables and statistics, and the demand figures."""
    text = (
        "network:\n  nodes: {a: {}, b: {disabled: true}}\n"
        f"  links: [{{source: {source}, target: {target}, capacity: 7}}]\n"
        'demands:\n  d: [{source: "^a", target: "^b", volume: 1}]\n'
    )
    lines = _inspect(tmp_path, text, "--detail")
    assert _table_row(lines, "Enabled", 2) == [
        ["Enabled", "1 nodes (50.0%), 0 links (0.0%)"]
    ]
    assert _table_row(lines, "Capacity (enabled)", 2) == [["Capacity (enabled)", "0.0"]]
    assert _table_row(lines, "Utilization", 2) == [["Utilization", "0.00%"]]
    assert "Enabled Links: 0 (0.0%)" in lines and "Disabled Links: 1" in lines
    assert _table_row(lines, source, 5) == [[source, target, "disabled", "7", "1"]]
    assert _table_row(lines, "a", 4) == [["a", "enabled", "0", "0"]]
    assert _table_row(lines, "b", 4) == [["b", "disabled", "0", "0"]]
    assert "Link Capacity Statistics:" not in lines
    assert _table_row(lines, "Total", 2) == []  # no node capacity statistics either
    assert "enabled link capacity: 0.0" in lines
    assert "ratio: N/A (zero capacity or zero demand)" in lines
    net = Network()
    net.add_node(Node("a"))
    net.add_node(Node("b", disabled=True))
    net.add_link(Link(source, target, 7))
    stats = run(prepare(Scenario(net, (NetworkStats(name="s"),)))).steps[0].result
    assert stats.total_capacity == 0


def test_step_parameters_print_output_options_by_fields_reproducibly():
    """Native OutputOptions print by their fields, so two runs print the same text."""
    texts = []
    for _ in range(2):
        code, out, _ = _cli(
            ["--quiet", "inspect", str(ROOT / "scenarios/square_mesh.yaml"), "--detail"]
        )
        assert code == 0
        texts.append(out)
    assert texts[0] == texts[1]
    assert " object at 0x" not in texts[0]
    assert (
        "| OutputOptions(edge_flows=False, residual=False, edge_reservations=False, "
        "saturated_boundary_edges=False, min_cut=False)"
    ) in texts[0]


FLAGS = (
    "edge_flows",
    "residual",
    "edge_reservations",
    "saturated_boundary_edges",
    "min_cut",
)


def test_step_parameters_print_the_given_output_options(tmp_path):
    """Each flag set on its own, and a mixed set, print as given."""
    sets = [{flag} for flag in FLAGS] + [{"edge_flows", "min_cut"}]
    steps = "".join(
        f"  - {{type: MaxFlow, name: m{i}, source: ^A, target: ^B, "
        f"outputs: {{{', '.join(f'{flag}: true' for flag in sorted(on))}}}}}\n"
        for i, on in enumerate(sets)
    )
    text = (
        "network:\n  nodes: {A: {}, B: {}}\n  links: [{source: A, target: B, capacity: 1}]\n"
        "workflow:\n" + steps
    )
    lines = _inspect(tmp_path, text, "--detail")
    rows = [row[1] for row in _table_row(lines, "outputs", 2)]
    assert rows == [
        "OutputOptions(" + ", ".join(f"{flag}={flag in on}" for flag in FLAGS) + ")"
        for on in sets
    ]


def _demand_lines(*entries):
    """A scenario with nodes A, B, C, D and one demand set of (source, target, volume)."""
    demands = "".join(
        f'    - {{source: "{src}", target: "{tgt}", volume: {vol}}}\n'
        for src, tgt, vol in entries
    )
    return "network:\n  nodes: {A: {}, B: {}, C: {}, D: {}}\ndemands:\n  d:\n" + demands


def test_previews_rank_the_most_frequent_sources_and_targets(tmp_path):
    """A->D once, B->A twice, C->B three times: sources C, B; targets B, A."""
    entries = [("^A", "^D", 1)] + [("^B", "^A", 1)] * 2 + [("^C", "^B", 1)] * 3
    lines = _inspect(tmp_path, _demand_lines(*entries))
    previews = [
        line.split(":")[0] for line in lines if line.startswith(("source ", "target "))
    ]
    assert previews == ["source ^C", "source ^B", "target ^B", "target ^A"]


def test_a_repeated_pair_adds_its_count_and_volume(tmp_path):
    lines = _inspect(
        tmp_path, _demand_lines(("^A", "^B", 2), ("^A", "^B", 3)), "--detail"
    )
    assert _table_row(lines, "^A", 7) == [
        ["^A", "^B", "2", "5", "1g/1n (1e)", "1g/1n (1e)", "^A"]
    ]


def test_selectors_with_one_label_keep_their_own_entries(tmp_path):
    """A list value and the string `[edge, core]` print alike but select differently."""
    text = (
        "network:\n  nodes: {A: {attrs: {role: [edge, core]}}, B: {}}\n"
        "demands:\n  d:\n"
        + "".join(
            f'    - {{source: {{path: "^A", match: {{conditions: '
            f'[{{attr: role, op: "==", value: {value}}}]}}}}, target: "^B", volume: 1}}\n'
            for value in ("[edge, core]", '"[edge, core]"')
        )
    )
    lines = _inspect(tmp_path, text, "--detail")
    assert "unique source patterns: 2; unique target patterns: 1" in lines
    rows = _table_row(lines, "^A [match: role == [edge, core]]", 7)
    assert [row[2:5] for row in rows] == [
        ["1", "1", "1g/1n (1e)"],
        ["1", "1", "0g/0n (0e)"],
    ]


def test_an_exists_condition_is_labelled_without_a_value():
    for op in ("exists", "not_exists"):
        selector = Selector("^A", match=MatchSpec([Condition("role", op)]))
        assert cli._selector_label(selector) == f"^A [match: role {op}]"


def test_top_demands_and_detail_rows_use_selector_labels(tmp_path):
    """Top demands and the first-demands list print labels; a step's bad pattern is
    refused where it is declared."""
    detail = _inspect(tmp_path, W7, "--detail")
    assert _table_row(detail, "^A [match: role == edge]", 4) == [
        ["^A [match: role == edge]", "* [group_by: role]", "1.0", "0"]
    ]
    assert "1. ^A [match: role == edge] -> * [group_by: role] (1.0)" in detail
    path = tmp_path / "bad.yaml"
    path.write_text(W7.replace('target: "^B"', 'target: "["'))
    code, out, err = _cli(["--quiet", "inspect", str(path), "--detail"])
    assert code == 1
    assert "workflow[1] (name 'mf').target.path = '[': invalid pattern '['" in out + err


def test_a_summary_lists_the_first_five_group_labels():
    net = Network()
    for i in range(6):
        net.add_node(Node(f"n{i}"))
    info = cli._summarize_selector(Selector(r"^(n\d)"), net)
    assert (info["groups"], info["labels"]) == (6, ["n0", "n1", "n2", "n3", "n4"])


def test_parameters_print_enums_by_name():
    """An enum prints its name (a plain Enum's str() would add the class)."""

    class Pace(Enum):
        FAST = 1

    assert cli._parameter_text(Pace.FAST) == "FAST"
    assert cli._parameter_text(FlowPolicyPreset.TE_MAXFLOW_UNLIM) == "TE_MAXFLOW_UNLIM"
    assert cli._parameter_text(3) == "3"
