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
      capacity: 100
      cost: 10

failures:
  weighted_modes:
    modes:
      - weight: 0.6
        rules:
          - scope: "link"
            mode: "choice"
            count: 1
            weight_by: "cost"
      - weight: 0.4
        rules:
          - scope: "node"
            mode: "choice"
            count: 1

workflow:
  - type: BuildGraph
    name: build
"""

    scenario = Scenario.from_yaml(scenario_yaml)
    policy = scenario.failure_policy_set.get_policy("weighted_modes")
    # Ensure modes parsed and stored
    assert policy.modes and len(policy.modes) == 2
    # Ensure weight_by propagated into rule
    assert policy.modes[0].rules[0].weight_by == "cost"
