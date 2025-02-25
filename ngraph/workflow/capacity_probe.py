from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ngraph.workflow.base import WorkflowStep, register_workflow_step
from ngraph.lib.algorithms.max_flow import calc_max_flow

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@register_workflow_step("CapacityProbe")
@dataclass
class CapacityProbe(WorkflowStep):
    """
    A workflow step that probes capacity between selected nodes.

    Attributes:
        source_path (str): A path/prefix to match source nodes.
        sink_path (str): A path/prefix to match sink nodes.
    """

    source_path: str = ""
    sink_path: str = ""

    def run(self, scenario: Scenario) -> None:
        # 1) Select source and sink nodes
        sources = scenario.network.select_nodes_by_path(self.source_path)
        sinks = scenario.network.select_nodes_by_path(self.sink_path)

        # 2) Build the graph
        graph = scenario.network.to_strict_multidigraph()

        # 3) Attach pseudo-nodes the source and sink groups, then use max flow
        #    to calculate max flow between them
        results = {}
        graph.add_node("source")
        graph.add_node("sink")
        for source in sources:
            graph.add_edge("source", source.name, capacity=float("inf"), cost=0)
        for sink in sinks:
            graph.add_edge(sink.name, "sink", capacity=float("inf"), cost=0)
        flow = calc_max_flow(graph, "source", "sink")

        # 4) Store results in scenario
        scenario.results.put(self.name, "max_flow", flow)
