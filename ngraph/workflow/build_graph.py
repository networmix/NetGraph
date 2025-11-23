"""Graph building workflow component.

Validates and exports network topology as a node-link representation using NetworkX.
After NetGraph-Core integration, actual graph building happens in analysis
functions. This step primarily validates the network and stores a serializable
representation for inspection.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: BuildGraph
        name: "build_network_graph"  # Optional: Custom name for this step
        add_reverse: true  # Optional: Add reverse edges (default: true)
    ```

The `add_reverse` parameter controls whether reverse edges are added for each link.
When `True` (default), each Link(A→B) gets both forward(A→B) and reverse(B→A) edges
for bidirectional connectivity. Set to `False` for directed-only graphs.

Results stored in `scenario.results` under the step name as two keys:
    - metadata: Step-level execution metadata (node/link counts)
    - data: { graph: node-link JSON dict, context: { add_reverse: bool } }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import networkx as nx

from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@dataclass
class BuildGraph(WorkflowStep):
    """Validates network topology and stores node-link representation.

    After NetGraph-Core integration, this step validates the network structure
    and stores a JSON-serializable node-link representation using NetworkX.
    Actual Core graph building happens in analysis functions as needed.

    Attributes:
        add_reverse: If True, adds reverse edges for bidirectional connectivity.
                     Defaults to True for backward compatibility.
    """

    add_reverse: bool = True

    def run(self, scenario: Scenario) -> None:
        """Validate network and store node-link representation.

        Args:
            scenario: Scenario containing the network model.

        Returns:
            None
        """
        network = scenario.network

        # Build NetworkX MultiDiGraph from Network
        graph = nx.MultiDiGraph()

        # Add nodes with attributes
        for node_name in sorted(network.nodes.keys()):
            node = network.nodes[node_name]
            graph.add_node(
                node_name,
                disabled=node.disabled,
                **node.attrs,
            )

        # Add edges (links) with attributes
        for link_id in sorted(network.links.keys()):
            link = network.links[link_id]
            # Add forward edge
            graph.add_edge(
                link.source,
                link.target,
                id=link_id,
                capacity=float(link.capacity),
                cost=float(link.cost),
                disabled=link.disabled,
                **link.attrs,
            )
            # Add reverse edge if configured (for bidirectional connectivity)
            if self.add_reverse:
                reverse_id = f"{link_id}_reverse"
                graph.add_edge(
                    link.target,
                    link.source,
                    id=reverse_id,
                    capacity=float(link.capacity),
                    cost=float(link.cost),
                    disabled=link.disabled,
                    **link.attrs,
                )

        # Convert to node-link format for serialization
        # Use edges="edges" for forward compatibility with NetworkX 3.6+
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


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("BuildGraph")(BuildGraph)
