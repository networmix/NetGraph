from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from ngraph.failure_policy import FailurePolicy
from ngraph.network import Network
from ngraph.results import Results
from ngraph.scenario import Scenario
from ngraph.workflow.base import (
    WORKFLOW_STEP_REGISTRY,
    WorkflowStep,
    register_workflow_step,
)

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@dataclass
class DoSmth(WorkflowStep):
    """
    Example step that has an extra field 'some_param'.
    """

    some_param: int = 0

    def run(self, scenario: Scenario) -> None:
        """
        Perform a dummy operation for testing.
        Store something in scenario.results using the step name as a key.
        """
        scenario.results.put(self.name, "ran", True)


@dataclass
class DoSmthElse(WorkflowStep):
    """
    Example step that has an extra field 'factor'.
    """

    factor: float = 1.0

    def run(self, scenario: Scenario) -> None:
        scenario.results.put(self.name, "ran", True)


# Register the classes after definition to avoid decorator ordering issues
register_workflow_step("DoSmth")(DoSmth)
register_workflow_step("DoSmthElse")(DoSmthElse)


@pytest.fixture
def valid_scenario_yaml() -> str:
    """
    Returns a YAML string for constructing a Scenario with:
      - A small network of three nodes and two links
      - A multi-rule failure policy referencing 'type' in conditions
      - Two traffic demands
      - Two workflow steps
    """
    return """
network:
  nodes:
    NodeA:
      attrs:
        role: ingress
        location: somewhere
        type: node
    NodeB:
      attrs:
        role: transit
        type: node
    NodeC:
      attrs:
        role: egress
        type: node
  links:
    - source: NodeA
      target: NodeB
      link_params:
        capacity: 10
        cost: 5
        attrs:
          type: link
          some_attr: some_value
    - source: NodeB
      target: NodeC
      link_params:
        capacity: 20
        cost: 4
        attrs:
          type: link
failure_policy_set:
  default:
    attrs:
      name: "multi_rule_example"
      description: "Testing multi-rule approach."
    fail_shared_risk_groups: false
    fail_risk_group_children: false
    use_cache: false
    rules:
      - entity_scope: node
        logic: "any"
        rule_type: "choice"
        count: 1
      - entity_scope: link
        logic: "any"
        rule_type: "all"
traffic_matrix_set:
  default:
    - source_path: NodeA
      sink_path: NodeB
      demand: 15
    - source_path: NodeA
      sink_path: NodeC
      demand: 5
workflow:
  - step_type: DoSmth
    name: Step1
    some_param: 42
  - step_type: DoSmthElse
    name: Step2
    factor: 2.0
"""


@pytest.fixture
def missing_step_type_yaml() -> str:
    """
    Returns a YAML string missing the 'step_type' in the workflow,
    which should raise a ValueError.
    """
    return """
network:
  nodes:
    NodeA: {}
    NodeB: {}
  links:
    - source: NodeA
      target: NodeB
      link_params:
        capacity: 1
failure_policy_set:
  default:
    rules: []
traffic_matrix_set:
  default:
    - source_path: NodeA
      sink_path: NodeB
      demand: 10
workflow:
  - name: StepWithoutType
    some_param: 123
"""


@pytest.fixture
def unrecognized_step_type_yaml() -> str:
    """
    Returns a YAML string with an unrecognized step_type in the workflow,
    which should raise a ValueError.
    """
    return """
network:
  nodes:
    NodeA: {}
    NodeB: {}
  links:
    - source: NodeA
      target: NodeB
      link_params:
        capacity: 1
failure_policy_set:
  default:
    rules: []
traffic_matrix_set:
  default:
    - source_path: NodeA
      sink_path: NodeB
      demand: 10
workflow:
  - step_type: NonExistentStep
    name: BadStep
    some_param: 999
"""


@pytest.fixture
def extra_param_yaml() -> str:
    """
    Returns a YAML string that attempts to pass an unsupported 'extra_param'
    to a known workflow step type, which should raise a TypeError.
    """
    return """
network:
  nodes:
    NodeA: {}
    NodeB: {}
  links:
    - source: NodeA
      target: NodeB
      link_params:
        capacity: 1
traffic_matrix_set: {}
failure_policy_set:
  default:
    rules: []
workflow:
  - step_type: DoSmth
    name: StepWithExtra
    some_param: 42
    extra_param: 99
"""


@pytest.fixture
def minimal_scenario_yaml() -> str:
    """
    Returns a YAML string with only a single workflow step, no network,
    no failure_policy, and no traffic_matrix_set. Should be valid but minimal.
    """
    return """
workflow:
  - step_type: DoSmth
    name: JustStep
    some_param: 100
"""


@pytest.fixture
def empty_yaml() -> str:
    """
    Returns an empty YAML string; from_yaml should still construct
    a Scenario object but with none/empty fields if possible.
    """
    return ""


def test_scenario_from_yaml_valid(valid_scenario_yaml: str) -> None:
    """
    Tests that a Scenario can be constructed from a valid YAML string.
    Ensures that:
      - Network has correct nodes/links
      - FailurePolicy is set with multiple rules
      - TrafficDemands are parsed
      - Workflow steps are instantiated
      - Results object is present
    """
    scenario = Scenario.from_yaml(valid_scenario_yaml)

    # Check network
    assert isinstance(scenario.network, Network)
    assert len(scenario.network.nodes) == 3  # NodeA, NodeB, NodeC
    assert len(scenario.network.links) == 2  # NodeA->NodeB, NodeB->NodeC

    node_names = list(scenario.network.nodes.keys())
    assert "NodeA" in node_names
    assert "NodeB" in node_names
    assert "NodeC" in node_names

    link_names = list(scenario.network.links.keys())
    assert len(link_names) == 2

    # Link from NodeA -> NodeB
    link_ab = next(
        (lk for lk in scenario.network.links.values() if lk.source == "NodeA"), None
    )
    link_bc = next(
        (lk for lk in scenario.network.links.values() if lk.source == "NodeB"), None
    )
    assert link_ab is not None, "Could not find link NodeA->NodeB"
    assert link_ab.target == "NodeB"
    assert link_ab.capacity == 10
    assert link_ab.cost == 5
    assert link_ab.attrs.get("some_attr") == "some_value"

    assert link_bc is not None, "Could not find link NodeB->NodeC"
    assert link_bc.target == "NodeC"
    assert link_bc.capacity == 20
    assert link_bc.cost == 4

    # Check failure policy
    default_policy = scenario.failure_policy_set.get_default_policy()
    assert isinstance(default_policy, FailurePolicy)
    assert not default_policy.fail_shared_risk_groups
    assert not default_policy.fail_risk_group_children
    assert not default_policy.use_cache

    assert len(default_policy.rules) == 2
    assert default_policy.attrs.get("name") == "multi_rule_example"
    assert default_policy.attrs.get("description") == "Testing multi-rule approach."

    # Rule1 => entity_scope=node, rule_type=choice, count=1
    rule1 = default_policy.rules[0]
    assert rule1.entity_scope == "node"
    assert rule1.rule_type == "choice"
    assert rule1.count == 1

    # Rule2 => entity_scope=link, rule_type=all
    rule2 = default_policy.rules[1]
    assert rule2.entity_scope == "link"
    assert rule2.rule_type == "all"

    # Check traffic matrix set
    assert len(scenario.traffic_matrix_set.matrices) == 1
    assert "default" in scenario.traffic_matrix_set.matrices
    default_demands = scenario.traffic_matrix_set.matrices["default"]
    assert len(default_demands) == 2
    d1 = default_demands[0]
    d2 = default_demands[1]
    assert d1.source_path == "NodeA"
    assert d1.sink_path == "NodeB"
    assert d1.demand == 15
    assert d2.source_path == "NodeA"
    assert d2.sink_path == "NodeC"
    assert d2.demand == 5

    # Check workflow
    assert len(scenario.workflow) == 2
    step1, step2 = scenario.workflow
    assert step1.__class__ == WORKFLOW_STEP_REGISTRY["DoSmth"]
    assert step1.name == "Step1"
    assert step1.some_param == 42

    assert step2.__class__ == WORKFLOW_STEP_REGISTRY["DoSmthElse"]
    assert step2.name == "Step2"
    assert step2.factor == 2.0

    # Check results
    assert isinstance(scenario.results, Results)


def test_scenario_run(valid_scenario_yaml: str) -> None:
    """
    Tests scenario.run() => each workflow step is executed in order,
    storing data in scenario.results.
    """
    scenario = Scenario.from_yaml(valid_scenario_yaml)
    scenario.run()

    assert scenario.results.get("Step1", "ran", default=False) is True
    assert scenario.results.get("Step2", "ran", default=False) is True


def test_scenario_from_yaml_missing_step_type(missing_step_type_yaml: str) -> None:
    """
    Tests that Scenario.from_yaml raises a ValueError if a workflow step
    is missing the 'step_type' field.
    """
    with pytest.raises(ValueError) as excinfo:
        Scenario.from_yaml(missing_step_type_yaml)
    assert "must have a 'step_type' field" in str(excinfo.value)


def test_scenario_from_yaml_unrecognized_step_type(
    unrecognized_step_type_yaml: str,
) -> None:
    """
    Tests that Scenario.from_yaml raises a ValueError if the step_type
    is not found in the WORKFLOW_STEP_REGISTRY.
    """
    with pytest.raises(ValueError) as excinfo:
        Scenario.from_yaml(unrecognized_step_type_yaml)
    assert "Unrecognized 'step_type'" in str(excinfo.value)


def test_scenario_from_yaml_unsupported_param(extra_param_yaml: str) -> None:
    """
    Tests that Scenario.from_yaml raises TypeError if a workflow step
    has an unsupported parameter in the YAML.
    """
    with pytest.raises(TypeError) as excinfo:
        Scenario.from_yaml(extra_param_yaml)
    assert "extra_param" in str(excinfo.value)


def test_scenario_minimal(minimal_scenario_yaml: str) -> None:
    """
    A minimal scenario with only workflow steps => no network, no demands, no policy.
    Should still produce a valid Scenario object.
    """
    scenario = Scenario.from_yaml(minimal_scenario_yaml)
    assert scenario.network is not None
    assert len(scenario.network.nodes) == 0
    assert len(scenario.network.links) == 0

    # If no failure_policy_set block, scenario.failure_policy_set has no policies
    assert scenario.failure_policy_set.get_default_policy() is None

    assert len(scenario.traffic_matrix_set.matrices) == 0
    assert len(scenario.workflow) == 1
    step = scenario.workflow[0]
    assert step.name == "JustStep"
    assert step.some_param == 100


def test_scenario_empty_yaml(empty_yaml: str) -> None:
    """
    Constructing from an empty YAML => produce empty scenario
    with no network, no policy, no demands, no steps.
    """
    scenario = Scenario.from_yaml(empty_yaml)
    assert scenario.network is not None
    assert len(scenario.network.nodes) == 0
    assert len(scenario.network.links) == 0
    assert scenario.failure_policy_set.get_default_policy() is None
    assert len(scenario.traffic_matrix_set.matrices) == 0
    assert scenario.workflow == []


def test_scenario_risk_groups() -> None:
    """
    Tests that risk groups are parsed, and if 'disabled' is True,
    the group is disabled on load.
    """
    scenario_yaml = """
network:
  nodes:
    NodeA: {}
    NodeB: {}
  links: []
risk_groups:
  - name: "RG1"
    disabled: false
  - name: "RG2"
    disabled: true
"""
    scenario = Scenario.from_yaml(scenario_yaml)
    assert "RG1" in scenario.network.risk_groups
    assert "RG2" in scenario.network.risk_groups
    rg1 = scenario.network.risk_groups["RG1"]
    rg2 = scenario.network.risk_groups["RG2"]
    assert rg1.disabled is False
    assert rg2.disabled is True


def test_scenario_risk_group_missing_name() -> None:
    """
    If a risk group is missing 'name', raise ValueError.
    """
    scenario_yaml = """
network: {}
risk_groups:
  - name_missing: "RG1"
"""
    with pytest.raises(ValueError) as excinfo:
        Scenario.from_yaml(scenario_yaml)
    assert "RiskGroup entry missing 'name' field" in str(excinfo.value)


def test_failure_policy_docstring_yaml_integration():
    """Integration test: Parse the exact YAML from the FailurePolicy docstring and verify it works."""
    from unittest.mock import patch

    import yaml

    # Extract the exact YAML from the docstring
    yaml_content = """
failure_policy:
  attrs:
    name: "Texas Grid Outage Scenario"
    description: "Regional power grid failure affecting telecom infrastructure"
  fail_shared_risk_groups: true
  rules:
    # Fail all nodes in Texas electrical grid
    - entity_scope: "node"
      conditions:
        - attr: "electric_grid"
          operator: "=="
          value: "texas"
      logic: "and"
      rule_type: "all"

    # Randomly fail 40% of underground fiber links in affected region
    - entity_scope: "link"
      conditions:
        - attr: "region"
          operator: "=="
          value: "southwest"
        - attr: "type"
          operator: "=="
          value: "underground"
      logic: "and"
      rule_type: "random"
      probability: 0.4

    # Choose exactly 2 risk groups to fail (e.g., data centers)
    - entity_scope: "risk_group"
      logic: "any"
      rule_type: "choice"
      count: 2
"""

    # Parse the YAML
    parsed_data = yaml.safe_load(yaml_content)
    failure_policy_data = parsed_data["failure_policy"]

    # Use the internal _build_failure_policy method to create the policy
    policy = Scenario._build_failure_policy(failure_policy_data)

    # Verify the policy was created correctly
    assert policy.attrs["name"] == "Texas Grid Outage Scenario"
    assert (
        policy.attrs["description"]
        == "Regional power grid failure affecting telecom infrastructure"
    )
    assert policy.fail_shared_risk_groups is True
    assert len(policy.rules) == 3

    # Rule 1: Texas electrical grid nodes
    rule1 = policy.rules[0]
    assert rule1.entity_scope == "node"
    assert len(rule1.conditions) == 1
    assert rule1.conditions[0].attr == "electric_grid"
    assert rule1.conditions[0].operator == "=="
    assert rule1.conditions[0].value == "texas"
    assert rule1.logic == "and"
    assert rule1.rule_type == "all"

    # Rule 2: Random underground fiber links in southwest region
    rule2 = policy.rules[1]
    assert rule2.entity_scope == "link"
    assert len(rule2.conditions) == 2
    assert rule2.conditions[0].attr == "region"
    assert rule2.conditions[0].operator == "=="
    assert rule2.conditions[0].value == "southwest"
    assert rule2.conditions[1].attr == "type"
    assert rule2.conditions[1].operator == "=="
    assert rule2.conditions[1].value == "underground"
    assert rule2.logic == "and"
    assert rule2.rule_type == "random"
    assert rule2.probability == 0.4

    # Rule 3: Risk group choice
    rule3 = policy.rules[2]
    assert rule3.entity_scope == "risk_group"
    assert len(rule3.conditions) == 0
    assert rule3.logic == "any"
    assert rule3.rule_type == "choice"
    assert rule3.count == 2

    # Test that the policy actually works with real data
    nodes = {
        "N1": {
            "electric_grid": "texas",
            "region": "southwest",
        },  # Should fail from rule 1
        "N2": {
            "electric_grid": "california",
            "region": "west",
        },  # Should not fail from rule 1
        "N3": {
            "electric_grid": "pjm",
            "region": "northeast",
        },  # Should not fail from rule 1
    }

    links = {
        "L1": {"type": "underground", "region": "southwest"},  # Eligible for rule 2
        "L2": {"type": "opgw", "region": "southwest"},  # Not eligible (wrong type)
        "L3": {
            "type": "underground",
            "region": "northeast",
        },  # Not eligible (wrong region)
    }

    risk_groups = {
        "RG1": {"name": "DataCenter_Dallas"},
        "RG2": {"name": "DataCenter_Houston"},
        "RG3": {"name": "DataCenter_Austin"},
    }

    # Test with mocked randomness for deterministic results
    with (
        patch("ngraph.failure_policy.random", return_value=0.3),
        patch("ngraph.failure_policy.sample", return_value=["RG1", "RG2"]),
    ):
        failed = policy.apply_failures(nodes, links, risk_groups)

        # Verify expected failures
        assert "N1" in failed  # Texas grid node
        assert "N2" not in failed  # California grid node
        assert "N3" not in failed  # PJM grid node


def test_failure_policy_docstring_yaml_full_scenario_integration():
    """Test the docstring YAML example in a complete scenario context."""
    from unittest.mock import patch

    # Create a complete scenario with our failure policy
    scenario_yaml = """
network:
  nodes:
    N1:
      attrs:
        electric_grid: "texas"
        region: "southwest"
    N2:
      attrs:
        electric_grid: "california"
        region: "west"
    N3:
      attrs:
        electric_grid: "pjm"
        region: "northeast"
  links:
    - source: "N1"
      target: "N2"
      link_params:
        capacity: 1000
        attrs:
          type: "underground"
          region: "southwest"
    - source: "N2"
      target: "N3"
      link_params:
        capacity: 500
        attrs:
          type: "opgw"
          region: "west"

failure_policy_set:
  docstring_example:
    attrs:
      name: "Texas Grid Outage Scenario"
      description: "Regional power grid failure affecting telecom infrastructure"
    fail_shared_risk_groups: true
    rules:
      # Fail all nodes in Texas electrical grid
      - entity_scope: "node"
        conditions:
          - attr: "electric_grid"
            operator: "=="
            value: "texas"
        logic: "and"
        rule_type: "all"

      # Randomly fail 40% of underground fiber links in affected region
      - entity_scope: "link"
        conditions:
          - attr: "region"
            operator: "=="
            value: "southwest"
          - attr: "type"
            operator: "=="
            value: "underground"
        logic: "and"
        rule_type: "random"
        probability: 0.4

      # Choose exactly 2 risk groups to fail (e.g., data centers)
      - entity_scope: "risk_group"
        logic: "any"
        rule_type: "choice"
        count: 2

traffic_matrix_set:
  default: []
"""

    # Load the complete scenario
    scenario = Scenario.from_yaml(scenario_yaml)

    # Get the failure policy
    policy = scenario.failure_policy_set.get_policy("docstring_example")
    assert policy is not None

    # Verify it matches our expectations
    assert policy.attrs["name"] == "Texas Grid Outage Scenario"
    assert policy.fail_shared_risk_groups is True
    assert len(policy.rules) == 3

    # Verify it works with the scenario's network
    network = scenario.network
    nodes_dict = {name: node.attrs for name, node in network.nodes.items()}
    links_dict = {link_id: link.attrs for link_id, link in network.links.items()}

    with (
        patch("ngraph.failure_policy.random", return_value=0.3),
        patch("ngraph.failure_policy.sample", return_value=["RG1"]),
    ):
        failed = policy.apply_failures(nodes_dict, links_dict, {})

        # Texas grid node N1 should fail
        assert "N1" in failed
        assert "N2" not in failed  # California grid
        assert "N3" not in failed  # PJM grid
