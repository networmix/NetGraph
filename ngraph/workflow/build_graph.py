"""Graph building workflow component.

Converts scenario network definitions into StrictMultiDiGraph structures suitable
for analysis algorithms. No additional parameters required beyond basic workflow step options.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: BuildGraph
        name: "build_network_graph"  # Optional: Custom name for this step
    ```

Results stored in `scenario.results` under the step name as two keys:
    - metadata: Step-level execution metadata (empty dict)
    - data: { graph: node-link JSON dict, context: { add_reverse: bool } }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@dataclass
class BuildGraph(WorkflowStep):
    """A workflow step that builds a StrictMultiDiGraph from scenario.network.

    This step converts the scenario's network definition into a graph structure
    suitable for analysis algorithms. No additional parameters are required.
    """

    def run(self, scenario: Scenario) -> None:
        """Build the network graph and store it in results.

        Args:
            scenario: Scenario containing the network model.

        Returns:
            None
        """
        graph = scenario.network.to_strict_multidigraph(add_reverse=True)
        scenario.results.put("metadata", {})
        scenario.results.put(
            "data",
            {
                # Store as JSON-safe node-link dict rather than raw graph object
                "graph": graph.to_dict(),
                "context": {"add_reverse": True},
            },
        )


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("BuildGraph")(BuildGraph)
