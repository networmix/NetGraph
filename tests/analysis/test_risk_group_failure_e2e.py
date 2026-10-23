"""YAML risk-group rules reach native placement with typed converged results."""

from __future__ import annotations

from ngraph.scenario import Scenario, prepare, run

SCENARIO_YAML = """\
seed: 42
units: {resolution: 1}
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      capacity: 100
      cost: 1
      risk_groups: [rg_fiber]

risk_groups:
  - name: rg_fiber
    attrs: {type: fiber_path}

failures:
  fail_fiber:
    modes:
      - weight: 1.0
        rules:
          - scope: risk_group
            mode: choice
            count: 1
            match:
              conditions:
                - attr: type
                  op: "=="
                  value: fiber_path

demands:
  tm:
    - source: ^A$
      target: ^B$
      volume: 10
      mode: combine
      preset: SHORTEST_PATHS_ECMP

workflow:
  - type: TrafficMatrixPlacement
    name: tm_test
    demand_set: tm
    failure_policy: fail_fiber
    iterations: 5
    workers: 1
    seed: 42
"""


def test_risk_group_failure_excludes_member_links() -> None:
    """Failing a risk group must exclude its member links.

    Setup: single link A→B in risk group 'rg_fiber'. Failure policy
    selects risk groups with attrs.type == 'fiber_path'. Only match is
    rg_fiber, so every iteration must exclude the A→B link.

    With the only link removed, no traffic can be placed.
    """
    scenario = Scenario.from_yaml(SCENARIO_YAML)
    value = run(prepare(scenario)).steps[0].result
    baseline, failed = value.cases
    assert baseline.states["converged"].totals.delivered_units == 10
    assert failed.case.occurrences == 5
    assert failed.case.pattern.excluded_links == ("A|B|0",)
    assert failed.states["converged"].totals.delivered_units == 0


DUAL_PATH_YAML = """\
seed: 42
units: {resolution: 1}
network:
  nodes:
    S: {}
    D: {}
  links:
    - source: S
      target: D
      capacity: 100
      cost: 1
      risk_groups: [path_a]
    - source: S
      target: D
      capacity: 50
      cost: 2
      risk_groups: [path_b]

risk_groups:
  - name: path_a
    attrs: {type: lh_path, label: primary}
  - name: path_b
    attrs: {type: lh_path, label: secondary}

failures:
  fail_lh:
    modes:
      - weight: 1.0
        rules:
          - scope: risk_group
            mode: choice
            count: 1
            match:
              conditions:
                - attr: type
                  op: "=="
                  value: lh_path

demands:
  tm:
    - source: ^S$
      target: ^D$
      volume: 50
      mode: combine
      preset: SHORTEST_PATHS_ECMP

workflow:
  - type: TrafficMatrixPlacement
    name: tm_lh
    demand_set: tm
    failure_policy: fail_lh
    iterations: 20
    workers: 1
    outputs: {cost_distribution: true}
    seed: 42
"""


def test_dual_path_risk_group_failure_produces_asymmetric_results() -> None:
    """Two risk groups with different capacity links produce different outcomes.

    path_a: cap=100, cost=1 (primary, shortest)
    path_b: cap=50, cost=2 (secondary)
    demand: 50 Gbps

    Under ECMP, baseline uses path_a (shortest). demand=50, placed=50.

    Fail path_a → only path_b (cap=50, cost=2). placed=50, full delivery.
    Fail path_b → only path_a (cap=100, cost=1). placed=50, full delivery.

    Both survive, but cost_distribution differs:
    - fail path_a: all traffic at cost 2
    - fail path_b: all traffic at cost 1
    """
    scenario = Scenario.from_yaml(DUAL_PATH_YAML)
    value = run(prepare(scenario)).steps[0].result
    baseline, *failed = value.cases
    assert baseline.states["converged"].totals.delivered_units == 50
    assert len(failed) == 2
    for case in failed:
        assert len(case.case.pattern.excluded_links) == 1
        state = case.states["converged"]
        assert state.totals.delivered_units == 50
        expected_cost = 2 if case.case.pattern.excluded_links == ("S|D|0",) else 1
        assert [
            (bin.cost, bin.delivered_units)
            for bin in state.rows[0].cost_distribution.bins
        ] == [(expected_cost, 50)]
    assert sum(case.case.occurrences for case in failed) == 20
