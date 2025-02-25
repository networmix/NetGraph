from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@register_workflow_step("BuildGraph")
@dataclass
class BuildGraph(WorkflowStep):
    """
    A workflow step that builds a StrictMultiDiGraph from scenario.network.
    """

    def run(self, scenario: Scenario) -> None:
        graph = scenario.network.to_strict_multidigraph(add_reverse=True)
        scenario.results.put(self.name, "graph", graph)
