import pytest
import yaml

from typing import TYPE_CHECKING
from dataclasses import dataclass

from ngraph.scenario import Scenario
from ngraph.network import Network
from ngraph.failure_policy import FailurePolicy
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
        You might store something in scenario.results here if desired.
        """
        pass


@register_workflow_step("DoSmthElse")
@dataclass
class DoSmthElse(WorkflowStep):
    """
    Example step that has an extra field 'factor'.
    """

    factor: float = 1.0

    def run(self, scenario: Scenario) -> None:
        """
        Perform another dummy operation for testing.
        """
        pass


@pytest.fixture
def valid_scenario_yaml() -> str:
    """
    Returns a valid YAML string for constructing a Scenario with a small
    realistic network of three nodes and two links, plus two traffic demands.
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
      capacity: 10
      latency: 2
      cost: 5
      attrs: {some_attr: some_value}
    - source: NodeB
      target: NodeC
      capacity: 20
      latency: 3
      cost: 4
      attrs: {}
failure_policy:
  failure_probabilities:
    node: 0.01
    link: 0.02
traffic_demands:
  - source: NodeA
    target: NodeB
    demand: 15
  - source: NodeA
    target: NodeC
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
      capacity: 1
failure_policy:
  failure_probabilities:
    node: 0.01
    link: 0.02
traffic_demands:
  - source: NodeA
    target: NodeB
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
      capacity: 1
failure_policy:
  failure_probabilities:
    node: 0.01
    link: 0.02
traffic_demands:
  - source: NodeA
    target: NodeB
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
      capacity: 1
traffic_demands: []
failure_policy:
  failure_probabilities:
    node: 0.01
    link: 0.02
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
      - FailurePolicy is set
      - TrafficDemands are parsed
      - Workflow steps are instantiated
      - Results object is present
    """
    scenario = Scenario.from_yaml(valid_scenario_yaml)

    # Check network
    assert isinstance(scenario.network, Network)
    assert len(scenario.network.nodes) == 3  # We defined NodeA, NodeB, NodeC
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
    assert link_ab.latency == 2
    assert link_ab.cost == 5
    assert link_ab.attrs.get("some_attr") == "some_value"

    assert link_bc is not None, "Link from NodeB to NodeC was not found."
    assert link_bc.target == "NodeC"
    assert link_bc.capacity == 20
    assert link_bc.latency == 3
    assert link_bc.cost == 4

    # Check failure policy
    assert isinstance(scenario.failure_policy, FailurePolicy)
    assert scenario.failure_policy.failure_probabilities["node"] == 0.01
    assert scenario.failure_policy.failure_probabilities["link"] == 0.02

    # Check traffic demands
    assert len(scenario.traffic_demands) == 2
    demand_ab = next(
        (
            d
            for d in scenario.traffic_demands
            if d.source == "NodeA" and d.target == "NodeB"
        ),
        None,
    )
    demand_ac = next(
        (
            d
            for d in scenario.traffic_demands
            if d.source == "NodeA" and d.target == "NodeC"
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
    assert step2.__class__ == WORKFLOW_STEP_REGISTRY["DoSmthElse"]

    # Check the scenario results store
    assert isinstance(scenario.results, Results)


def test_scenario_run(valid_scenario_yaml: str) -> None:
    """
    Tests that calling scenario.run() executes each workflow step in order
    without errors. This verifies the new .run() method introduced in the Scenario class.
    """
    scenario = Scenario.from_yaml(valid_scenario_yaml)

    # Just ensure it runs without raising exceptions
    scenario.run()

    # For a thorough test, one might check scenario.results or other side effects
    # inside the steps themselves. Here, we just verify the workflow runs successfully.
    assert True


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
