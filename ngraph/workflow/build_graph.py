from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

import networkx as nx

from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@register_workflow_step("BuildGraph")
@dataclass
class BuildGraph(WorkflowStep):
    """
    A workflow step that uses Scenario.network to build a NetworkX MultiDiGraph.

    Since links in Network are conceptually bidirectional but we need unique identifiers
    for each direction, we add two directed edges per link:
      - forward edge: key = link.id
      - reverse edge: key = link.id + "_rev"

    The constructed graph is stored in scenario.results under (self.name, "graph").
    """

    def run(self, scenario: Scenario) -> None:
        # Create a MultiDiGraph to hold bidirectional edges
        graph = nx.MultiDiGraph()

        # 1) Add nodes
        for node_name, node in scenario.network.nodes.items():
            graph.add_node(node_name, **node.attrs)

        # 2) For each physical Link, add forward and reverse edges with unique keys
        for link_id, link in scenario.network.links.items():
            # Forward edge uses link.id
            graph.add_edge(
                link.source,
                link.target,
                key=link.id,
                capacity=link.capacity,
                cost=link.cost,
                latency=link.latency,
                **link.attrs,
            )
            # Reverse edge uses link.id + "_rev"
            reverse_id = f"{link.id}_rev"
            graph.add_edge(
                link.target,
                link.source,
                key=reverse_id,
                capacity=link.capacity,
                cost=link.cost,
                latency=link.latency,
                **link.attrs,
            )

        # 3) Store the resulting graph
        scenario.results.put(self.name, "graph", graph)
