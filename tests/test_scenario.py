import pytest
import yaml
from typing import TYPE_CHECKING
from dataclasses import dataclass

from ngraph.scenario import Scenario
from ngraph.network import Network
from ngraph.failure_policy import FailurePolicy, FailureRule, FailureCondition
from ngraph.traffic_demand import TrafficDemand
from ngraph.results import Results
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    WORKFLOW_STEP_REGISTRY,
)

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@register_workflow_step("DoSmth")
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


@register_workflow_step("DoSmthElse")
@dataclass
class DoSmthElse(WorkflowStep):
    """
    Example step that has an extra field 'factor'.
    """

    factor: float = 1.0

    def run(self, scenario: Scenario) -> None:
        scenario.results.put(self.name, "ran", True)


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
failure_policy:
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
traffic_demands:
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
failure_policy:
  rules: []
traffic_demands:
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
failure_policy:
  rules: []
traffic_demands:
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
traffic_demands: []
failure_policy:
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
    no failure_policy, and no traffic_demands. Should be valid but minimal.
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
    assert isinstance(scenario.failure_policy, FailurePolicy)
    assert not scenario.failure_policy.fail_shared_risk_groups
    assert not scenario.failure_policy.fail_risk_group_children
    assert not scenario.failure_policy.use_cache

    assert len(scenario.failure_policy.rules) == 2
    assert scenario.failure_policy.attrs.get("name") == "multi_rule_example"
    assert (
        scenario.failure_policy.attrs.get("description")
        == "Testing multi-rule approach."
    )

    # Rule1 => entity_scope=node, rule_type=choice, count=1
    rule1 = scenario.failure_policy.rules[0]
    assert rule1.entity_scope == "node"
    assert rule1.rule_type == "choice"
    assert rule1.count == 1

    # Rule2 => entity_scope=link, rule_type=all
    rule2 = scenario.failure_policy.rules[1]
    assert rule2.entity_scope == "link"
    assert rule2.rule_type == "all"

    # Check traffic demands
    assert len(scenario.traffic_demands) == 2
    d1 = scenario.traffic_demands[0]
    d2 = scenario.traffic_demands[1]
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

    # If no failure_policy block, scenario.failure_policy => None
    assert scenario.failure_policy is None

    assert scenario.traffic_demands == []
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
    assert scenario.failure_policy is None
    assert scenario.traffic_demands == []
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
