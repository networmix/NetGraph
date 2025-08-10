from ngraph.scenario import Scenario


def test_scenario_parses_modes_and_weight_by() -> None:
    scenario_yaml = """
seed: 4242
network:
  name: simple
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
        cost: 10

failure_policy_set:
  mc_baseline_v1:
    modes:
      - weight: 0.6
        rules:
          - entity_scope: "link"
            rule_type: "choice"
            count: 1
            weight_by: "cost"
      - weight: 0.4
        rules:
          - entity_scope: "node"
            rule_type: "choice"
            count: 1

workflow:
  - step_type: BuildGraph
    name: build
"""

    scenario = Scenario.from_yaml(scenario_yaml)
    policy = scenario.failure_policy_set.get_policy("mc_baseline_v1")
    # Ensure modes parsed and stored
    assert policy.modes and len(policy.modes) == 2
    # Ensure weight_by propagated into rule
    assert policy.modes[0].rules[0].weight_by == "cost"
