from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ngraph.network import Network, RiskGroup
from ngraph.failure_policy import (
    FailurePolicy,
    FailureRule,
    FailureCondition,
)
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
      - A network (nodes/links), constructed via blueprint expansion.
      - A failure policy (one or more rules).
      - A set of traffic demands.
      - A list of workflow steps to execute.
      - A results container for storing outputs.
      - A components_library for hardware/optics definitions.

    Typical usage example:

        scenario = Scenario.from_yaml(yaml_str, default_components=default_lib)
        scenario.run()
        # Inspect scenario.results
    """

    network: Network
    failure_policy: Optional[FailurePolicy]
    traffic_demands: List[TrafficDemand]
    workflow: List[WorkflowStep]
    results: Results = field(default_factory=Results)
    components_library: ComponentsLibrary = field(default_factory=ComponentsLibrary)

    def run(self) -> None:
        """
        Executes the scenario's workflow steps in order.

        Each step may modify scenario data or store outputs
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

        Top-level YAML keys can include:
          - blueprints
          - network
          - failure_policy
          - traffic_demands
          - workflow
          - components
          - risk_groups

        If no 'workflow' key is provided, the scenario has no steps to run.
        If 'failure_policy' is omitted, scenario.failure_policy is None.
        If 'components' is provided, it is merged with default_components.
        If any unrecognized top-level key is found, a ValueError is raised.

        Args:
            yaml_str (str): The YAML string that defines the scenario.
            default_components (ComponentsLibrary, optional):
                A default library to merge with scenario-specific components.

        Returns:
            Scenario: An initialized Scenario with expanded network.

        Raises:
            ValueError: If the YAML is malformed or missing required sections,
                or if there are any unrecognized top-level keys.
            TypeError: If a workflow step's arguments are invalid for the step class.
        """
        data = yaml.safe_load(yaml_str)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("The provided YAML must map to a dictionary at top-level.")

        # Ensure only recognized top-level keys are present.
        recognized_keys = {
            "blueprints",
            "network",
            "failure_policy",
            "traffic_demands",
            "workflow",
            "components",
            "risk_groups",
        }
        extra_keys = set(data.keys()) - recognized_keys
        if extra_keys:
            raise ValueError(
                f"Unrecognized top-level key(s) in scenario: {', '.join(sorted(extra_keys))}. "
                f"Allowed keys are {sorted(recognized_keys)}"
            )

        # 1) Build the network using blueprint expansion logic
        network_obj = expand_network_dsl(data)
        if network_obj is None:
            network_obj = Network()

        # 2) Build the multi-rule failure policy (may be empty or None)
        fp_data = data.get("failure_policy", {})
        failure_policy = cls._build_failure_policy(fp_data) if fp_data else None

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

        # 6) Parse optional risk_groups, then attach them to the network
        rg_data = data.get("risk_groups", [])
        if rg_data:
            risk_groups = cls._build_risk_groups(rg_data)
            for rg in risk_groups:
                network_obj.risk_groups[rg.name] = rg
                if rg.disabled:
                    network_obj.disable_risk_group(rg.name, recursive=True)

        return cls(
            network=network_obj,
            failure_policy=failure_policy,
            traffic_demands=traffic_demands,
            workflow=workflow_steps,
            components_library=final_components,
        )

    @staticmethod
    def _build_risk_groups(rg_data: List[Dict[str, Any]]) -> List[RiskGroup]:
        """
        Recursively builds a list of RiskGroup objects from YAML data.

        Each entry may have keys: "name", "children", "disabled", and "attrs" (dict).

        Args:
            rg_data (List[Dict[str, Any]]): The list of risk-group definitions.

        Returns:
            List[RiskGroup]: Possibly nested risk groups.

        Raises:
            ValueError: If any group is missing 'name'.
        """

        def build_one(d: Dict[str, Any]) -> RiskGroup:
            name = d.get("name")
            if not name:
                raise ValueError("RiskGroup entry missing 'name' field.")
            disabled = d.get("disabled", False)
            children_list = d.get("children", [])
            child_objs = [build_one(cd) for cd in children_list]
            attrs = d.get("attrs", {})
            return RiskGroup(
                name=name, disabled=disabled, children=child_objs, attrs=attrs
            )

        return [build_one(entry) for entry in rg_data]

    @staticmethod
    def _build_failure_policy(fp_data: Dict[str, Any]) -> FailurePolicy:
        """
        Constructs a FailurePolicy from data that may specify multiple rules plus
        optional top-level fields like fail_shared_risk_groups, fail_risk_group_children,
        use_cache, and attrs.

        Example:
            failure_policy:
              name: "test"  # (Currently unused if present)
              fail_shared_risk_groups: true
              fail_risk_group_children: false
              use_cache: true
              attrs:
                custom_key: custom_val
              rules:
                - entity_scope: "node"
                  conditions:
                    - attr: "capacity"
                      operator: ">"
                      value: 100
                  logic: "and"
                  rule_type: "choice"
                  count: 2

        Args:
            fp_data (Dict[str, Any]): Dictionary from the 'failure_policy' section of the YAML.

        Returns:
            FailurePolicy: The constructed policy. If no rules exist, it's an empty policy.

        Raises:
            ValueError: If 'rules' is present but not a list, or if conditions are not lists.
        """
        fail_srg = fp_data.get("fail_shared_risk_groups", False)
        fail_rg_children = fp_data.get("fail_risk_group_children", False)
        use_cache = fp_data.get("use_cache", False)
        attrs = fp_data.get("attrs", {})

        # Extract rules
        rules_data = fp_data.get("rules", [])
        if not isinstance(rules_data, list):
            raise ValueError("failure_policy 'rules' must be a list if present.")

        rules: List[FailureRule] = []
        for rule_dict in rules_data:
            entity_scope = rule_dict.get("entity_scope", "node")
            conditions_data = rule_dict.get("conditions", [])
            if not isinstance(conditions_data, list):
                raise ValueError("Each rule's 'conditions' must be a list if present.")
            conditions: List[FailureCondition] = []
            for cond_dict in conditions_data:
                conditions.append(
                    FailureCondition(
                        attr=cond_dict["attr"],
                        operator=cond_dict["operator"],
                        value=cond_dict["value"],
                    )
                )

            rule = FailureRule(
                entity_scope=entity_scope,
                conditions=conditions,
                logic=rule_dict.get("logic", "and"),
                rule_type=rule_dict.get("rule_type", "all"),
                probability=rule_dict.get("probability", 1.0),
                count=rule_dict.get("count", 1),
            )
            rules.append(rule)

        return FailurePolicy(
            rules=rules,
            attrs=attrs,
            fail_shared_risk_groups=fail_srg,
            fail_risk_group_children=fail_rg_children,
            use_cache=use_cache,
        )

    @staticmethod
    def _build_workflow_steps(
        workflow_data: List[Dict[str, Any]],
    ) -> List[WorkflowStep]:
        """
        Converts workflow step dictionaries into WorkflowStep objects.

        Each step dict must have a "step_type" referencing a registered workflow
        step in WORKFLOW_STEP_REGISTRY. All other keys in the dict are passed
        to that step's constructor as keyword arguments.

        Args:
            workflow_data (List[Dict[str, Any]]): A list of dictionaries describing
                each workflow step, for example:
                [
                  {
                    "step_type": "MyStep",
                    "arg1": "value1",
                    "arg2": "value2",
                  },
                  ...
                ]

        Returns:
            List[WorkflowStep]: A list of instantiated WorkflowStep objects.

        Raises:
            ValueError: If any step lacks "step_type" or references an unknown type.
            TypeError: If step initialization fails due to invalid arguments.
        """
        if not isinstance(workflow_data, list):
            raise ValueError("'workflow' must be a list if present.")

        steps: List[WorkflowStep] = []
        for step_info in workflow_data:
            step_type = step_info.get("step_type")
            if not step_type:
                raise ValueError(
                    "Each workflow entry must have a 'step_type' field "
                    "indicating the WorkflowStep subclass to use."
                )

            step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
            if not step_cls:
                raise ValueError(f"Unrecognized 'step_type': {step_type}")

            ctor_args = {k: v for k, v in step_info.items() if k != "step_type"}
            step_obj = step_cls(**ctor_args)
            steps.append(step_obj)

        return steps
