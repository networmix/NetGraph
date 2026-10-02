"""BuildGraph workflow step.

Exports the network topology as a NetworkX node-link representation for
inspection. Analysis functions build their own graphs and do not read this
one.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: BuildGraph
        name: "build_network_graph"  # Optional: Custom name for this step
        add_reverse: true  # Optional: Add reverse edges (default: true)
    ```

With `add_reverse: true` (the default), each Link(A→B) gets both a forward
(A→B) and a reverse (B→A) edge for bidirectional connectivity. Set it to
`false` for directed-only graphs.

Results stored in `scenario.results` under the step name as two keys:
    - metadata: node_count and link_count (graph edges, including reverse edges)
    - data: { graph: node-link JSON dict, context: { add_reverse: bool } }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import networkx as nx

from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class BuildGraph(WorkflowStep):
    """Stores the network as JSON-serializable NetworkX node-link data.

    Attributes:
        add_reverse: If True, adds a reverse edge (id "<link_id>_reverse") for
            every link. Defaults to True.
    """

    add_reverse: bool = True

    def run(self, scenario: Scenario) -> None:
        """Store the network's node-link representation.

        Args:
            scenario: Scenario containing the network model.
        """
        logger.info("Starting BuildGraph: name=%s", self.name)
        network = scenario.network

        graph = nx.MultiDiGraph()

        # Reserved keys win over user attrs to avoid kwarg collisions when
        # attrs contain e.g. "disabled".
        for node_name in sorted(network.nodes.keys()):
            node = network.nodes[node_name]
            graph.add_node(node_name, **{**node.attrs, "disabled": node.disabled})

        # Reserved keys (id, capacity, cost, disabled) win over user attrs
        # with the same names.
        for link_id in sorted(network.links.keys()):
            link = network.links[link_id]
            graph.add_edge(
                link.source,
                link.target,
                **{
                    **link.attrs,
                    "id": link_id,
                    "capacity": float(link.capacity),
                    "cost": float(link.cost),
                    "disabled": link.disabled,
                },
            )
            if self.add_reverse:
                reverse_id = f"{link_id}_reverse"
                graph.add_edge(
                    link.target,
                    link.source,
                    **{
                        **link.attrs,
                        "id": reverse_id,
                        "capacity": float(link.capacity),
                        "cost": float(link.cost),
                        "disabled": link.disabled,
                    },
                )

        graph_dict = nx.node_link_data(graph, edges="edges")

        scenario.results.put(
            "metadata",
            {
                "node_count": len(graph.nodes),
                "link_count": len(graph.edges),
            },
        )
        scenario.results.put(
            "data",
            {
                "graph": graph_dict,
                "context": {"add_reverse": self.add_reverse},
            },
        )

        logger.info(
            "BuildGraph completed: name=%s nodes=%d edges=%d",
            self.name,
            len(graph.nodes),
            len(graph.edges),
        )


register_workflow_step("BuildGraph")(BuildGraph)
