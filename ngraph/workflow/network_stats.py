"""Workflow step for basic node and link statistics."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import TYPE_CHECKING, Dict, List

from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@dataclass
class NetworkStats(WorkflowStep):
    """Compute basic node and link statistics for the network.

    Attributes:
        include_disabled (bool): If True, include disabled nodes and links in statistics.
                                 If False, only consider enabled entities. Defaults to False.
    """

    include_disabled: bool = False

    def run(self, scenario: Scenario) -> None:
        """Collect capacity and degree statistics.

        Args:
            scenario: Scenario containing the network and results container.
        """

        network = scenario.network

        # Collect link capacity statistics - filter based on include_disabled setting
        if self.include_disabled:
            link_caps = [link.capacity for link in network.links.values()]
        else:
            link_caps = [
                link.capacity for link in network.links.values() if not link.disabled
            ]

        link_caps_sorted = sorted(link_caps)
        link_stats = {
            "values": link_caps_sorted,
            "min": min(link_caps_sorted) if link_caps_sorted else 0.0,
            "max": max(link_caps_sorted) if link_caps_sorted else 0.0,
            "mean": mean(link_caps_sorted) if link_caps_sorted else 0.0,
            "median": median(link_caps_sorted) if link_caps_sorted else 0.0,
        }

        # Collect per-node statistics and aggregate data for distributions
        node_stats: Dict[str, Dict[str, List[float] | float]] = {}
        node_capacities = []
        node_degrees = []
        for node_name, node in network.nodes.items():
            # Skip disabled nodes unless include_disabled is True
            if not self.include_disabled and node.disabled:
                continue

            # Calculate node degree and capacity - filter links based on include_disabled setting
            if self.include_disabled:
                outgoing = [
                    link.capacity
                    for link in network.links.values()
                    if link.source == node_name
                ]
            else:
                outgoing = [
                    link.capacity
                    for link in network.links.values()
                    if link.source == node_name and not link.disabled
                ]

            degree = len(outgoing)
            cap_sum = sum(outgoing)

            node_degrees.append(degree)
            node_capacities.append(cap_sum)

            node_stats[node_name] = {
                "degree": degree,
                "capacity_sum": cap_sum,
                "capacities": sorted(outgoing),
            }

        # Create aggregate distributions for network-wide analysis
        node_caps_sorted = sorted(node_capacities)
        node_degrees_sorted = sorted(node_degrees)

        node_capacity_dist = {
            "values": node_caps_sorted,
            "min": min(node_caps_sorted) if node_caps_sorted else 0.0,
            "max": max(node_caps_sorted) if node_caps_sorted else 0.0,
            "mean": mean(node_caps_sorted) if node_caps_sorted else 0.0,
            "median": median(node_caps_sorted) if node_caps_sorted else 0.0,
        }

        node_degree_dist = {
            "values": node_degrees_sorted,
            "min": min(node_degrees_sorted) if node_degrees_sorted else 0.0,
            "max": max(node_degrees_sorted) if node_degrees_sorted else 0.0,
            "mean": mean(node_degrees_sorted) if node_degrees_sorted else 0.0,
            "median": median(node_degrees_sorted) if node_degrees_sorted else 0.0,
        }

        scenario.results.put(self.name, "link_capacity", link_stats)
        scenario.results.put(self.name, "node_capacity", node_capacity_dist)
        scenario.results.put(self.name, "node_degree", node_degree_dist)
        scenario.results.put(self.name, "per_node", node_stats)


register_workflow_step("NetworkStats")(NetworkStats)
