from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ngraph.network import Network, RiskGroup
from ngraph.failure_policy import FailurePolicy, FailureRule, FailureCondition
from ngraph.traffic_demand import TrafficDemand
from ngraph.results import Results
from ngraph.workflow.base import WorkflowStep, WORKFLOW_STEP_REGISTRY
from ngraph.blueprints import expand_network_dsl
from ngraph.components import ComponentsLibrary


@dataclass(slots=True)
class Scenario:
    """
    Represents a complete scenario for building and executing network workflows.

    This scenario includes:
      - A network (nodes and links), constructed via blueprint expansion.
      - A failure policy (one or more rules).
      - A set of traffic demands.
      - A list of workflow steps to execute.
      - A results container for storing outputs.
      - A components_library for hardware/optics definitions.

    Typical usage example:

        scenario = Scenario.from_yaml(yaml_str, default_components=default_lib)
        scenario.run()
        # Inspect scenario.results

    Attributes:
        network: The network model containing nodes and links.
        failure_policy: Defines how and which entities fail.
        traffic_demands: Describes source/target flows.
        workflow: Steps to execute in sequence.
        results: Stores outputs from the workflow steps.
        components_library: Hardware/optics library definitions.
    """

    network: Network
    failure_policy: FailurePolicy
    traffic_demands: List[TrafficDemand]
    workflow: List[WorkflowStep]
    results: Results = field(default_factory=Results)
    components_library: ComponentsLibrary = field(default_factory=ComponentsLibrary)

    def run(self) -> None:
        """
        Executes the scenario's workflow steps in the defined order.

        Each step may access and modify scenario data, or store outputs
        in scenario.results.
        """
        for step in self.workflow:
            step.run(self)

    @classmethod
    def from_yaml(
        cls,
        yaml_str: str,
        default_components: Optional[ComponentsLibrary] = None,
    ) -> Scenario:
        """
        Constructs a Scenario from a YAML string, optionally merging
        with a default ComponentsLibrary if provided.

        Expected top-level YAML keys:
          - blueprints: Optional blueprint definitions.
          - network: Network DSL referencing blueprints or direct node/link definitions.
          - failure_policy: Multi-rule policy definition.
          - traffic_demands: A list of demands (source, target, amount).
          - workflow: Steps to execute in sequence.
          - components: Optional dictionary defining scenario-specific components.
          - risk_groups: Optional list of shared-risk group definitions (may specify "disabled").

        Args:
            yaml_str: The YAML string that defines the scenario.
            default_components: An optional default library to merge with
                scenario-specific components.

        Returns:
            Scenario: An initialized Scenario with expanded network.

        Raises:
            ValueError: If the YAML is malformed or missing required sections.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("The provided YAML must map to a dictionary at top-level.")

        # 1) Build the network using blueprint expansion logic
        network = expand_network_dsl(data)

        # 2) Build the multi-rule failure policy
        fp_data = data.get("failure_policy", {})
        failure_policy = cls._build_failure_policy(fp_data)

        # 3) Build traffic demands
        traffic_demands_data = data.get("traffic_demands", [])
        traffic_demands = [TrafficDemand(**td) for td in traffic_demands_data]

        # 4) Build workflow steps
        workflow_data = data.get("workflow", [])
        workflow_steps = cls._build_workflow_steps(workflow_data)

        # 5) Build/merge components library
        scenario_comps_data = data.get("components", {})
        scenario_comps_lib = (
            ComponentsLibrary.from_dict(scenario_comps_data)
            if scenario_comps_data
            else None
        )

        final_components = (
            default_components.clone() if default_components else ComponentsLibrary()
        )
        if scenario_comps_lib:
            final_components.merge(scenario_comps_lib)

        # 6) Parse optional risk_groups in the scenario, then add to the network
        risk_group_data = data.get("risk_groups", [])
        if risk_group_data:
            risk_groups = cls._build_risk_groups(risk_group_data)
            for rg in risk_groups:
                network.risk_groups[rg.name] = rg
                # Disable the entire group if rg.disabled is True
                if rg.disabled:
                    network.disable_risk_group(rg.name, recursive=True)

        return cls(
            network=network,
            failure_policy=failure_policy,
            traffic_demands=traffic_demands,
            workflow=workflow_steps,
            components_library=final_components,
        )

    @staticmethod
    def _build_risk_groups(rg_data: List[Dict[str, Any]]) -> List[RiskGroup]:
        """
        Recursively build a list of RiskGroups from YAML data. Each dict
        may have keys: "name", "children", "disabled" (bool).

        Args:
            rg_data: Top-level list of risk-group definitions.

        Returns:
            A list of top-level RiskGroup objects, each possibly containing children.
        """

        def build_one(d: Dict[str, Any]) -> RiskGroup:
            name: str = d["name"]
            children_data = d.get("children", [])
            disabled = d.get("disabled", False)  # optional; default to False
            child_groups = [build_one(child) for child in children_data]
            return RiskGroup(name=name, children=child_groups, disabled=disabled)

        return [build_one(entry) for entry in rg_data]

    @staticmethod
    def _build_failure_policy(fp_data: Dict[str, Any]) -> FailurePolicy:
        """
        Constructs a FailurePolicy from data that may specify multiple rules.

        Example structure:
            failure_policy:
              name: "anySingleLink"
              description: "Test single-link failures."
              rules:
                - conditions:
                    - attr: "type"
                      operator: "=="
                      value: "link"
                  logic: "and"
                  rule_type: "choice"
                  count: 1

        Args:
            fp_data: Dictionary from the 'failure_policy' section.

        Returns:
            A FailurePolicy containing a list of FailureRule objects.

        Raises:
            ValueError: If 'rules' is not a list when provided.
        """
        rules_data = fp_data.get("rules", [])
        if not isinstance(rules_data, list):
            raise ValueError("failure_policy 'rules' must be a list if present.")

        rules: List[FailureRule] = []
        for rule_dict in rules_data:
            conditions_data = rule_dict.get("conditions", [])
            conditions: List[FailureCondition] = []
            for cond_dict in conditions_data:
                condition = FailureCondition(
                    attr=cond_dict["attr"],
                    operator=cond_dict["operator"],
                    value=cond_dict["value"],
                )
                conditions.append(condition)

            rule = FailureRule(
                conditions=conditions,
                logic=rule_dict.get("logic", "and"),
                rule_type=rule_dict.get("rule_type", "all"),
                probability=rule_dict.get("probability", 1.0),
                count=rule_dict.get("count", 1),
            )
            rules.append(rule)

        # Put any extra keys (like "name", "description", etc.) into policy.attrs
        attrs = {k: v for k, v in fp_data.items() if k != "rules"}

        return FailurePolicy(rules=rules, attrs=attrs)

    @staticmethod
    def _build_workflow_steps(
        workflow_data: List[Dict[str, Any]],
    ) -> List[WorkflowStep]:
        """
        Converts workflow step dictionaries into instantiated WorkflowStep objects.

        Each step dict must have a "step_type" referencing a registered workflow
        step in WORKFLOW_STEP_REGISTRY. Additional keys are passed to that step's init.

        Example:
            workflow:
              - step_type: BuildGraph
                name: build_graph
              - step_type: ComputeRoutes
                name: compute_routes

        Args:
            workflow_data: A list of dictionaries, each describing a workflow step.

        Returns:
            A list of WorkflowStep instances.

        Raises:
            ValueError: If workflow_data is not a list, or if any entry
                lacks "step_type" or references an unknown step type.
        """
        if not isinstance(workflow_data, list):
            raise ValueError("'workflow' must be a list if present.")

        steps: List[WorkflowStep] = []
        for step_info in workflow_data:
            step_type = step_info.get("step_type")
            if not step_type:
                raise ValueError(
                    "Each workflow entry must have a 'step_type' field "
                    "to indicate the WorkflowStep subclass to use."
                )
            step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
            if not step_cls:
                raise ValueError(f"Unrecognized 'step_type': {step_type}")

            step_args = {k: v for k, v in step_info.items() if k != "step_type"}
            steps.append(step_cls(**step_args))
        return steps
