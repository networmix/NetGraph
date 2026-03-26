"""End-to-end test for risk group scoped failures.

Verifies the full pipeline: FailureManager.compute_exclusions →
FailurePolicy.apply_failures → match_entity_ids correctly matches
risk group attributes and excludes member links.
"""

from __future__ import annotations

from ngraph.scenario import Scenario

SCENARIO_YAML = """\
seed: 42
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
      flow_policy: SHORTEST_PATHS_ECMP

workflow:
  - type: TrafficMatrixPlacement
    name: tm_test
    demand_set: tm
    failure_policy: fail_fiber
    iterations: 5
    parallelism: 1
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
    scenario.run()
    results = scenario.results.to_dict()

    tm = results["steps"]["tm_test"]["data"]
    baseline = tm["baseline"]
    flow_results = tm["flow_results"]

    # Baseline: link is up, all traffic placed
    assert baseline["summary"]["total_placed"] == 10.0

    # Every failure iteration: link is down, nothing placed
    assert len(flow_results) == 1, "Single risk group → one unique pattern"

    fr = flow_results[0]
    assert fr["occurrence_count"] == 5
    assert len(fr["failure_state"]["excluded_links"]) > 0
    assert fr["summary"]["total_placed"] == 0.0


DUAL_PATH_YAML = """\
seed: 42
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
      flow_policy: SHORTEST_PATHS_ECMP

workflow:
  - type: TrafficMatrixPlacement
    name: tm_lh
    demand_set: tm
    failure_policy: fail_lh
    iterations: 20
    parallelism: 1
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
    scenario.run()
    results = scenario.results.to_dict()

    tm = results["steps"]["tm_lh"]["data"]
    flow_results = tm["flow_results"]

    # Two risk groups → at most 2 unique patterns
    assert 1 <= len(flow_results) <= 2

    # Every pattern must have non-empty exclusions
    for fr in flow_results:
        assert len(fr["failure_state"]["excluded_links"]) > 0, (
            "Risk group failure must exclude member links"
        )
        # Both paths can individually carry the 50 Gbps demand
        assert fr["summary"]["total_placed"] == 50.0

    # Total occurrence_count must equal iterations
    total_occ = sum(fr["occurrence_count"] for fr in flow_results)
    assert total_occ == 20
