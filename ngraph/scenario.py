from __future__ import annotations
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ngraph.network import Network, Node, Link
from ngraph.failure_policy import FailurePolicy, FailureRule, FailureCondition
from ngraph.traffic_demand import TrafficDemand
from ngraph.results import Results
from ngraph.workflow.base import WorkflowStep, WORKFLOW_STEP_REGISTRY


@dataclass(slots=True)
class Scenario:
    """
    Represents a complete scenario, including:
      - The network (nodes and links).
      - A failure policy (with one or more rules).
      - Traffic demands.
      - A workflow of steps to execute.
      - A results container for storing outputs.

    Typical usage:
      1. Create a Scenario from YAML: ::

           scenario = Scenario.from_yaml(yaml_str)

      2. Run it: ::

           scenario.run()

      3. Check scenario.results for step outputs.

    :param network:
        The network model containing nodes and links.
    :param failure_policy:
        The multi-rule failure policy describing how and which entities fail.
    :param traffic_demands:
        A list of traffic demands describing source/target flows.
    :param workflow:
        A list of workflow steps defining the scenario pipeline.
    :param results:
        A Results object to store outputs from workflow steps.
    """

    network: Network
    failure_policy: FailurePolicy
    traffic_demands: List[TrafficDemand]
    workflow: List[WorkflowStep]
    results: Results = field(default_factory=Results)

    def run(self) -> None:
        """
        Execute the scenario's workflow steps in the defined order.

        Each step has access to :attr:`Scenario.network`,
        :attr:`Scenario.failure_policy`, etc. Steps may store outputs in
        :attr:`Scenario.results`.
        """
        for step in self.workflow:
            step.run(self)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> Scenario:
        """
        Construct a :class:`Scenario` from a YAML string.

        Expected top-level YAML keys:
          - ``network``: Node/Link definitions
          - ``failure_policy``: A multi-rule policy
          - ``traffic_demands``: List of demands
          - ``workflow``: Steps to run

        Example:

        .. code-block:: yaml

            network:
              nodes:
                SEA: { coords: [47.6062, -122.3321] }
                SFO: { coords: [37.7749, -122.4194] }
              links:
                - source: SEA
                  target: SFO
                  capacity: 100
                  attrs: { distance_km: 1300 }

            failure_policy:
              name: "multi_rule_example"
              rules:
                - conditions:
                    - attr: "type"
                      operator: "=="
                      value: "node"
                  logic: "and"
                  rule_type: "choice"
                  count: 1

            traffic_demands:
              - source: SEA
                target: SFO
                demand: 50

            workflow:
              - step_type: BuildGraph
                name: build_graph

        :param yaml_str:
            The YAML string defining a scenario.
        :returns:
            A fully constructed :class:`Scenario` instance.
        :raises ValueError:
            If the YAML is malformed or missing required sections.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("The provided YAML must map to a dictionary at top-level.")

        # 1) Build the network
        network_data = data.get("network", {})
        network = cls._build_network(network_data)

        # 2) Build the (new) multi-rule failure policy
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
    def _build_network(network_data: Dict[str, Any]) -> Network:
        """
        Construct a :class:`Network` object from a dictionary containing 'nodes' and 'links'.
        The dictionary is expected to look like:

        .. code-block:: yaml

            nodes:
              SEA: { coords: [47.6062, -122.3321] }
              SFO: { coords: [37.7749, -122.4194] }

            links:
              - source: SEA
                target: SFO
                capacity: 100
                latency: 5
                cost: 10
                attrs:
                  distance_km: 1300

        :param network_data:
            Dictionary with optional keys 'nodes' and 'links'.
        :returns:
            A :class:`Network` containing the parsed nodes and links.
        :raises ValueError:
            If a link references nodes not defined in the network.
        """
        net = Network()

        # Add nodes
        nodes = network_data.get("nodes", {})
        for node_name, node_attrs in nodes.items():
            net.add_node(Node(name=node_name, attrs=node_attrs or {}))

        # Add links
        links = network_data.get("links", [])
        for link_info in links:
            link = Link(
                source=link_info["source"],
                target=link_info["target"],
                capacity=link_info.get("capacity", 1.0),
                latency=link_info.get("latency", 1.0),
                cost=link_info.get("cost", 1.0),
                attrs=link_info.get("attrs", {}),
            )
            net.add_link(link)

        return net

    @staticmethod
    def _build_failure_policy(fp_data: Dict[str, Any]) -> FailurePolicy:
        """
        Construct a :class:`FailurePolicy` from YAML data that may look like:

        .. code-block:: yaml

            failure_policy:
              name: "multi_rule_example"
              description: "Example of multi-rule approach"
              rules:
                - conditions:
                    - attr: "type"
                      operator: "=="
                      value: "link"
                  logic: "and"
                  rule_type: "random"
                  probability: 0.1

        :param fp_data:
            Dictionary from the 'failure_policy' section of YAML.
        :returns:
            A :class:`FailurePolicy` object with a list of :class:`FailureRule`.
        """
        # Extract the list of rules
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

        # All other key-value pairs go into policy.attrs (e.g. "name", "description")
        attrs = {k: v for k, v in fp_data.items() if k != "rules"}

        return FailurePolicy(rules=rules, attrs=attrs)

    @staticmethod
    def _build_workflow_steps(
        workflow_data: List[Dict[str, Any]]
    ) -> List[WorkflowStep]:
        """
        Convert a list of workflow step dictionaries into instantiated
        :class:`WorkflowStep` objects.

        Each step dict must have a ``step_type`` referencing a registered
        workflow step in :attr:`WORKFLOW_STEP_REGISTRY`. Any additional
        keys are passed as init arguments.

        Example:

        .. code-block:: yaml

            workflow:
              - step_type: BuildGraph
                name: build_graph
              - step_type: ComputeRoutes
                name: compute_routes

        :param workflow_data:
            A list of dictionaries, each describing a workflow step.
        :returns:
            A list of instantiated :class:`WorkflowStep` objects in the same order.
        :raises ValueError:
            If any dict lacks "step_type" or references an unknown type.
        """
        steps: List[WorkflowStep] = []
        for step_info in workflow_data:
            step_type = step_info.get("step_type")
            if not step_type:
                raise ValueError(
                    "Each workflow entry must have a 'step_type' field "
                    "indicating which WorkflowStep subclass to use."
                )
            step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
            if not step_cls:
                raise ValueError(f"Unrecognized 'step_type': {step_type}")

            # Remove 'step_type' so it doesn't clash with step_cls.__init__
            step_args = {k: v for k, v in step_info.items() if k != "step_type"}
            steps.append(step_cls(**step_args))
        return steps
