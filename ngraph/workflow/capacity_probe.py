from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ngraph.workflow.base import WorkflowStep, register_workflow_step
from ngraph.lib.algorithms.base import FlowPlacement

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@register_workflow_step("CapacityProbe")
@dataclass
class CapacityProbe(WorkflowStep):
    """
    A workflow step that probes capacity between selected nodes.

    Attributes:
        source_path (str): Path/prefix to select source nodes.
        sink_path (str): Path/prefix to select sink nodes.
        shortest_path (bool): If True, uses only the shortest paths (default False).
        flow_placement (FlowPlacement): Load balancing across parallel edges.
    """

    source_path: str = ""
    sink_path: str = ""
    shortest_path: bool = False
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL

    def run(self, scenario: Scenario) -> None:
        """
        Executes the capacity probe by computing the max flow between
        nodes selected by source_path and sink_path, then storing the
        result in the scenario's results container.

        Args:
            scenario (Scenario): The scenario object containing the network and results.
        """
        flow = scenario.network.max_flow(
            self.source_path,
            self.sink_path,
            shortest_path=self.shortest_path,
            flow_placement=self.flow_placement,
        )

        result_label = f"max_flow:[{self.source_path} -> {self.sink_path}]"
        scenario.results.put(self.name, result_label, flow)
