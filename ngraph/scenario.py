from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ngraph.network import Network
from ngraph.failure_policy import FailurePolicy, FailureRule, FailureCondition
from ngraph.traffic_demand import TrafficDemand
from ngraph.results import Results
from ngraph.workflow.base import WorkflowStep, WORKFLOW_STEP_REGISTRY
from ngraph.blueprints import expand_network_dsl


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

    Typical usage example:
        scenario = Scenario.from_yaml(yaml_str)
        scenario.run()
        # Inspect scenario.results

    Attributes:
        network (Network): The network model containing nodes and links.
        failure_policy (FailurePolicy): Defines how and which entities fail.
        traffic_demands (List[TrafficDemand]): Describes source/target flows.
        workflow (List[WorkflowStep]): Defines the execution pipeline.
        results (Results): Stores outputs from the workflow steps.
    """

    network: Network
    failure_policy: FailurePolicy
    traffic_demands: List[TrafficDemand]
    workflow: List[WorkflowStep]
    results: Results = field(default_factory=Results)

    def run(self) -> None:
        """
        Executes the scenario's workflow steps in the defined order.

        Each step may access and modify scenario data, or store outputs in
        scenario.results.
        """
        for step in self.workflow:
            step.run(self)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> Scenario:
        """
        Constructs a Scenario from a YAML string, including blueprint expansion.

        Expected top-level YAML keys:
          - blueprints: Optional set of blueprint definitions
          - network: Network DSL that references blueprints and/or direct nodes/links
          - failure_policy: Multi-rule policy definition
          - traffic_demands: List of demands (source, target, amount)
          - workflow: Steps to execute

        Args:
            yaml_str (str): The YAML string that defines the scenario.

        Returns:
            Scenario: An initialized Scenario instance with expanded network.

        Raises:
            ValueError: If the YAML is malformed or missing required sections.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("The provided YAML must map to a dictionary at top-level.")

        # 1) Build the network using blueprint expansion logic
        #    This handles both "blueprints" and "network" sections if present.
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

        return cls(
            network=network,
            failure_policy=failure_policy,
            traffic_demands=traffic_demands,
            workflow=workflow_steps,
        )

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
            fp_data (Dict[str, Any]): Dictionary for the 'failure_policy' section.

        Returns:
            FailurePolicy: A policy containing a list of FailureRule objects.
        """
        rules_data = fp_data.get("rules", [])
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

        # Put any extra keys (like "name" or "description") into policy.attrs
        attrs = {k: v for k, v in fp_data.items() if k != "rules"}

        return FailurePolicy(rules=rules, attrs=attrs)

    @staticmethod
    def _build_workflow_steps(
        workflow_data: List[Dict[str, Any]]
    ) -> List[WorkflowStep]:
        """
        Converts workflow step dictionaries into instantiated WorkflowStep objects.

        Each step dict must have a "step_type" referencing a registered workflow
        step in WORKFLOW_STEP_REGISTRY. Any additional keys are passed as init
        arguments to that WorkflowStep subclass.

        Example:
            workflow:
              - step_type: BuildGraph
                name: build_graph
              - step_type: ComputeRoutes
                name: compute_routes

        Args:
            workflow_data (List[Dict[str, Any]]): A list of dictionaries, each
                describing a workflow step.

        Returns:
            List[WorkflowStep]: A list of WorkflowStep instances, constructed
            in the order provided.

        Raises:
            ValueError: If a dict lacks "step_type" or references an unknown type.
        """
        steps: List[WorkflowStep] = []
        for step_info in workflow_data:
            step_type = step_info.get("step_type")
            if not step_type:
                raise ValueError(
                    "Each workflow entry must have a 'step_type' field indicating "
                    "which WorkflowStep subclass to use."
                )
            step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
            if not step_cls:
                raise ValueError(f"Unrecognized 'step_type': {step_type}")

            # Remove 'step_type' so it doesn't conflict with step_cls.__init__
            step_args = {k: v for k, v in step_info.items() if k != "step_type"}
            steps.append(step_cls(**step_args))
        return steps
