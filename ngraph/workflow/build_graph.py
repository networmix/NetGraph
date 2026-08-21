"""Graph building workflow component.

Validates the network topology and exports it as a NetworkX node-link
representation for inspection. Graph building for analysis happens in the
analysis functions, not here.

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
    - metadata: Step-level execution metadata (node/link counts)
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
    """Validates network topology and stores node-link representation.

    The stored representation is JSON-serializable NetworkX node-link data.
    Core graph building for analysis happens in analysis functions as needed.

    Attributes:
        add_reverse: If True, adds reverse edges for bidirectional connectivity.
                     Defaults to True.
    """

    add_reverse: bool = True

    def run(self, scenario: Scenario) -> None:
        """Validate network and store node-link representation.

        Args:
            scenario: Scenario containing the network model.

        Returns:
            None
        """
        logger.info("Starting BuildGraph: name=%s", self.name)
        network = scenario.network

        # Build NetworkX MultiDiGraph from Network
        graph = nx.MultiDiGraph()

        # Add nodes with attributes. Reserved keys win over user attrs to
        # avoid kwarg collisions when attrs contain e.g. "disabled".
        for node_name in sorted(network.nodes.keys()):
            node = network.nodes[node_name]
            graph.add_node(node_name, **{**node.attrs, "disabled": node.disabled})

        # Add edges (links) with attributes. Reserved keys (id, capacity,
        # cost, disabled) win over user attrs with the same names.
        for link_id in sorted(network.links.keys()):
            link = network.links[link_id]
            # Add forward edge
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
            # Add reverse edge if configured (for bidirectional connectivity)
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

        # Convert to node-link format for serialization
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


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("BuildGraph")(BuildGraph)
