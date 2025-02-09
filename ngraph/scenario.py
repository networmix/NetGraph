from __future__ import annotations
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ngraph.network import Network, Node, Link
from ngraph.failure_policy import FailurePolicy
from ngraph.traffic_demand import TrafficDemand
from ngraph.results import Results
from ngraph.workflow.base import WorkflowStep, WORKFLOW_STEP_REGISTRY


@dataclass(slots=True)
class Scenario:
    """
    Represents a complete scenario, including the network, failure policy,
    traffic demands, workflow steps, and a results store.

    Usage:
        scenario = Scenario.from_yaml(yaml_str)
        scenario.run()
        # Access scenario.results for workflow outputs

    Example YAML structure:

        network:
          nodes:
            JFK:
              coords: [40.64, -73.78]
            LAX:
              coords: [33.94, -118.41]
          links:
            - source: JFK
              target: LAX
              capacity: 100
              latency: 50
              cost: 50
              attrs: { distance_km: 4000 }

        failure_policy:
          failure_probabilities:
            node: 0.001
            link: 0.002

        traffic_demands:
          - source: JFK
            target: LAX
            demand: 50

        workflow:
          - step_type: BuildGraph
            name: build_graph

    :param network: The network model.
    :param failure_policy: The policy for element failures.
    :param traffic_demands: A list of traffic demands.
    :param workflow: A list of WorkflowStep objects to be executed in order.
    :param results: A Results object to store step outputs, summary, etc.
    """

    network: Network
    failure_policy: FailurePolicy
    traffic_demands: List[TrafficDemand]
    workflow: List[WorkflowStep]
    results: Results = field(default_factory=Results)

    def run(self) -> None:
        """
        Execute the scenario's workflow steps in the given order.
        Each WorkflowStep has access to this Scenario object and
        can store output in scenario.results.
        """
        for step in self.workflow:
            step.run(self)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> Scenario:
        """
        Construct a Scenario from a YAML string.

        This looks for top-level sections:
          'network', 'failure_policy', 'traffic_demands', and 'workflow'.

        See the class docstring for a short example of the expected structure.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("The provided YAML must map to a dictionary at top-level.")

        # 1) Build the network
        network_data = data.get("network", {})
        network = cls._build_network(network_data)

        # 2) Build the failure policy
        fp_data = data.get("failure_policy", {})
        failure_policy = FailurePolicy(
            failure_probabilities=fp_data.get("failure_probabilities", {})
        )

        # 3) Build traffic demands
        traffic_demands_data = data.get("traffic_demands", [])
        traffic_demands = [TrafficDemand(**td) for td in traffic_demands_data]

        # 4) Build workflow steps using the registry
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
        Construct a Network object from a dictionary containing 'nodes' and 'links'.
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
    def _build_workflow_steps(
        workflow_data: List[Dict[str, Any]]
    ) -> List[WorkflowStep]:
        """
        Instantiate workflow steps listed in 'workflow_data' using WORKFLOW_STEP_REGISTRY.
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

            # Remove 'step_type' so it doesn't clash with the step_class __init__
            step_args = {k: v for k, v in step_info.items() if k != "step_type"}
            steps.append(step_cls(**step_args))

        return steps
