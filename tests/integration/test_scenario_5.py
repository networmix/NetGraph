"""Scenario 5: every owner-required feature in one run, each step as if run alone."""

import json
from fractions import Fraction
from io import StringIO
from pathlib import Path

import pytest
import yaml

from ngraph.export import write_json
from ngraph.scenario import Scenario, prepare, run

PATH = Path(__file__).with_name("scenario_5.yaml")


@pytest.fixture(scope="module")
def result():
    return run(prepare(Scenario.from_yaml(PATH.read_text())))


def delivered(step, pattern):
    """Delivered units per state of the case whose failed links are ``pattern``."""
    (case,) = [c for c in step.result.cases if c.case.pattern.excluded_links == pattern]
    return {
        name: [r.result.delivered for r in s.rows] for name, s in case.states.items()
    }


def steps(result):
    return {step.name: step for step in result.steps}


def test_the_controller_states_and_simultaneous_figures(result):
    named = steps(result)
    # Four branches of 100, two root groups of equal share: lossless MSD alpha stays
    # below 4/3 (each member carries 300 alpha / 4 <= 100); the search tests 85/64.
    alpha = named["supported"].result.alpha_feasible
    assert Fraction(alpha.numerator, alpha.denominator) == Fraction(85, 64)
    # At 300 x 85/64 = 398.4375 -> 398 units. One member down: converged keeps the group
    # cap (half), the survivor carries x/2 <= 100, so 200; stale replays the program and
    # loses the failed member's quarter (100 of 398 by whole units: 298); repair = 200.
    states = named["states"]
    assert delivered(states, ()) == {
        "converged": [398],
        "stale": [398],
        "repair": [398],
    }
    assert delivered(states, ("S|A1|0",)) == {
        "converged": [200],
        "stale": [298],
        "repair": [200],
    }
    # A whole group dead: lossless stops at the first unit sent into it; stale loses the
    # group's half (200 of 398 by whole units: 198 delivered).
    assert delivered(states, ("S|A1|0", "S|A2|0")) == {
        "converged": [0],
        "stale": [198],
        "repair": [0],
    }
    # Simultaneous (fixed programs, LOSSY) at 300: 250 / 225 / 250, a dead group 150.
    together = named["simultaneous"]
    assert delivered(together, ("S|A1|0",)) == {
        "converged": [250],
        "stale": [225],
        "repair": [250],
    }
    assert delivered(together, ("S|A1|0", "S|A2|0")) == {
        "converged": [150],
        "stale": [150],
        "repair": [150],
    }


def test_the_other_features_beside_the_controller(result):
    named = steps(result)
    # The explicit route S-A1-T carries the whole 10.
    assert delivered(named["pinned_route"], ()) == {"converged": [10]}
    # Two tunnels on two of the four 100 routes deliver 200 of the offer 400; up to 4
    # chooses one tunnel, which already carries the design 100.
    assert [
        (r.count, r.up_to, r.result.plan.tunnels_per_head, r.result.delivered)
        for r in named["counts"].result.rows
    ] == [(2, False, 2, 200), (4, True, 1, 100)]
    # Maximum flow 400, 300 with S-A1 failed, 200 with S-A1 and S-A2 failed; the cut of
    # the baseline is S's four uplinks.
    capacity = named["capacity"]
    assert delivered(capacity, ()) == {"converged": [400]}
    assert delivered(capacity, ("S|A1|0",)) == {"converged": [300]}
    assert delivered(capacity, ("S|A1|0", "S|A2|0")) == {"converged": [200]}
    (row,) = capacity.result.cases[0].states["converged"].rows
    refs = result.topology.edge_refs
    assert sorted(refs[e].link for e in row.result.min_cut) == [
        "S|A1|0",
        "S|A2|0",
        "S|A3|0",
        "S|A4|0",
    ]
    assert (
        named["stats"].result.node_count == 6 and named["stats"].result.link_count == 8
    )
    assert named["build_graph"].result.node_count == 6
    (level,) = named["cost_power"].result.levels[0]
    # Two chassis (1000 and 100 W each) and S's optic end of S-A1 (10 and 1 W); the A1
    # end does not count, A1 having no hardware of its own.
    assert (level.capex_total, level.power_total_watts) == (2010.0, 201.0)


def exported(value):
    output = StringIO()
    write_json(value, output)
    data = json.loads(output.getvalue())
    return {s["name"]: {k: s[k] for k in ("question", "result")} for s in data["steps"]}


def test_each_step_equals_the_same_step_run_alone(result):
    # Steps share nothing but the prepared scenario: each one beside only the MSD step
    # (which the controller needs, the controlled set being prepared only for a step
    # that names it, and which one placement reads alpha from) exports the same
    # question and result.
    together = exported(result)
    data = yaml.safe_load(PATH.read_text())
    for step in data["workflow"]:
        alone = dict(data)
        msd = data["workflow"][3]
        alone["workflow"] = [msd] if step is msd else [msd, step]
        single = exported(run(prepare(Scenario.from_yaml(yaml.safe_dump(alone)))))
        assert single[step["name"]] == together[step["name"]], step["name"]
