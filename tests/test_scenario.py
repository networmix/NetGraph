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


# -------------------------------------------------------------------
# Dummy workflow steps for testing
# -------------------------------------------------------------------
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
      - A multi-rule failure policy
      - Two traffic demands
      - Two workflow steps
    """
    return """
network:
  nodes:
    NodeA:
      role: ingress
      location: somewhere
    NodeB:
      role: transit
    NodeC:
      role: egress
  links:
    - source: NodeA
      target: NodeB
      link_params:
        capacity: 10
        cost: 5
        attrs:
          some_attr: some_value
    - source: NodeB
      target: NodeC
      link_params:
        capacity: 20
        cost: 4
        attrs: {}
failure_policy:
  name: "multi_rule_example"
  description: "Testing multi-rule approach."
  rules:
    - conditions:
        - attr: "type"
          operator: "=="
          value: "node"
      logic: "and"
      rule_type: "choice"
      count: 1
    - conditions:
        - attr: "type"
          operator: "=="
          value: "link"
      logic: "and"
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


def test_scenario_from_yaml_valid(valid_scenario_yaml: str) -> None:
    """
    Tests that a Scenario can be correctly constructed from a valid YAML string.
    Ensures that:
      - Network has correct nodes and links
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

    node_names = [node.name for node in scenario.network.nodes.values()]
    assert "NodeA" in node_names
    assert "NodeB" in node_names
    assert "NodeC" in node_names

    links = list(scenario.network.links.values())
    assert len(links) == 2

    link_ab = next((lk for lk in links if lk.source == "NodeA"), None)
    link_bc = next((lk for lk in links if lk.source == "NodeB"), None)

    assert link_ab is not None, "Link from NodeA to NodeB was not found."
    assert link_ab.target == "NodeB"
    assert link_ab.capacity == 10
    assert link_ab.cost == 5
    assert link_ab.attrs.get("some_attr") == "some_value"

    assert link_bc is not None, "Link from NodeB to NodeC was not found."
    assert link_bc.target == "NodeC"
    assert link_bc.capacity == 20
    assert link_bc.cost == 4

    # Check failure policy
    assert isinstance(scenario.failure_policy, FailurePolicy)
    assert len(scenario.failure_policy.rules) == 2, "Expected 2 rules in the policy."
    # leftover fields (e.g., name, description) in policy.attrs
    assert scenario.failure_policy.attrs.get("name") == "multi_rule_example"
    assert (
        scenario.failure_policy.attrs.get("description")
        == "Testing multi-rule approach."
    )

    # Rule1 => "choice", count=1, conditions => type == "node"
    rule1 = scenario.failure_policy.rules[0]
    assert rule1.rule_type == "choice"
    assert rule1.count == 1
    assert len(rule1.conditions) == 1
    cond1 = rule1.conditions[0]
    assert cond1.attr == "type"
    assert cond1.operator == "=="
    assert cond1.value == "node"

    # Rule2 => "all", conditions => type == "link"
    rule2 = scenario.failure_policy.rules[1]
    assert rule2.rule_type == "all"
    assert len(rule2.conditions) == 1
    cond2 = rule2.conditions[0]
    assert cond2.attr == "type"
    assert cond2.operator == "=="
    assert cond2.value == "link"

    # Check traffic demands
    assert len(scenario.traffic_demands) == 2
    demand_ab = next(
        (
            d
            for d in scenario.traffic_demands
            if d.source_path == "NodeA" and d.sink_path == "NodeB"
        ),
        None,
    )
    demand_ac = next(
        (
            d
            for d in scenario.traffic_demands
            if d.source_path == "NodeA" and d.sink_path == "NodeC"
        ),
        None,
    )
    assert demand_ab is not None, "Demand from NodeA to NodeB not found."
    assert demand_ab.demand == 15

    assert demand_ac is not None, "Demand from NodeA to NodeC not found."
    assert demand_ac.demand == 5

    # Check workflow
    assert len(scenario.workflow) == 2
    step1 = scenario.workflow[0]
    step2 = scenario.workflow[1]

    # Verify the step types come from the registry
    assert step1.__class__ == WORKFLOW_STEP_REGISTRY["DoSmth"]
    assert step1.name == "Step1"
    assert step1.some_param == 42

    assert step2.__class__ == WORKFLOW_STEP_REGISTRY["DoSmthElse"]
    assert step2.name == "Step2"
    assert step2.factor == 2.0

    # Check the scenario results store
    assert isinstance(scenario.results, Results)


def test_scenario_run(valid_scenario_yaml: str) -> None:
    """
    Tests that calling scenario.run() executes each workflow step in order
    without errors. Steps may store data in scenario.results.
    """
    scenario = Scenario.from_yaml(valid_scenario_yaml)
    scenario.run()

    # The first step's name is "Step1" in the YAML:
    assert scenario.results.get("Step1", "ran", default=False) is True
    # The second step's name is "Step2" in the YAML:
    assert scenario.results.get("Step2", "ran", default=False) is True


def test_scenario_from_yaml_missing_step_type(missing_step_type_yaml: str) -> None:
    """
    Tests that Scenario.from_yaml raises a ValueError if a workflow step
    is missing the 'step_type' field.
    """
    with pytest.raises(ValueError) as excinfo:
        _ = Scenario.from_yaml(missing_step_type_yaml)
    assert "must have a 'step_type' field" in str(excinfo.value)


def test_scenario_from_yaml_unrecognized_step_type(
    unrecognized_step_type_yaml: str,
) -> None:
    """
    Tests that Scenario.from_yaml raises a ValueError if the step_type
    is not found in the WORKFLOW_STEP_REGISTRY.
    """
    with pytest.raises(ValueError) as excinfo:
        _ = Scenario.from_yaml(unrecognized_step_type_yaml)
    assert "Unrecognized 'step_type'" in str(excinfo.value)


def test_scenario_from_yaml_unsupported_param(extra_param_yaml: str) -> None:
    """
    Tests that Scenario.from_yaml raises a TypeError if a workflow step
    in the YAML has an unsupported parameter.
    """
    with pytest.raises(TypeError) as excinfo:
        _ = Scenario.from_yaml(extra_param_yaml)

    # Typically the error message is something like:
    # "DoSmth.__init__() got an unexpected keyword argument 'extra_param'"
    assert "extra_param" in str(excinfo.value)
