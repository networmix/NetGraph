"""Workflow step for basic node and link statistics.

Computes and stores network statistics including node/link counts,
capacity distributions, cost distributions, and degree distributions. Excluded
entities are filtered out without modifying the base network; disabled nodes
and links are excluded too unless `include_disabled` is set.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: NetworkStats
        name: "network_statistics"           # Optional: Custom name for this step
        include_disabled: false              # Include disabled nodes/links in stats
        excluded_nodes: ["node1", "node2"]   # Optional: Temporary node exclusions
        excluded_links: ["link1", "link3"]   # Optional: Temporary link exclusions
    ```

Results stored in `scenario.results`:
    - Node statistics: node_count
    - Link statistics: link_count, total_capacity, mean_capacity, median_capacity,
      min_capacity, max_capacity, mean_cost, median_cost, min_cost, max_cost
    - Degree statistics: mean_degree, median_degree, min_degree, max_degree
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import TYPE_CHECKING, Dict, Iterable

from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class NetworkStats(WorkflowStep):
    """Compute basic node and link statistics for the network.

    Supports optional exclusion simulation without modifying the base network.

    Attributes:
        include_disabled: If True, include disabled nodes and links in statistics.
            If False, only consider enabled entities.
        excluded_nodes: Optional list of node names to exclude (temporary exclusion).
        excluded_links: Optional list of link IDs to exclude (temporary exclusion).
    """

    include_disabled: bool = False
    excluded_nodes: Iterable[str] = ()
    excluded_links: Iterable[str] = ()

    def run(self, scenario: Scenario) -> None:
        """Compute and store network statistics.

        If `excluded_nodes` or `excluded_links` are specified, filters them out
        without modifying the base network.

        Args:
            scenario: The scenario containing the network to analyze.

        Returns:
            None
        """
        logger.info("Starting NetworkStats: name=%s", self.name)

        # Sets, so the per-node/per-link membership tests below stay O(1)
        excluded_nodes_set = set(self.excluded_nodes) if self.excluded_nodes else set()
        excluded_links_set = set(self.excluded_links) if self.excluded_links else set()

        # Filter nodes based on disabled status and exclusions
        if self.include_disabled:
            nodes = {
                name: node
                for name, node in scenario.network.nodes.items()
                if name not in excluded_nodes_set
            }
        else:
            nodes = {
                name: node
                for name, node in scenario.network.nodes.items()
                if not node.disabled and name not in excluded_nodes_set
            }

        # Filter links based on disabled status, exclusions, and node availability
        if self.include_disabled:
            links = {
                link_id: link
                for link_id, link in scenario.network.links.items()
                if link_id not in excluded_links_set
                and link.source in nodes
                and link.target in nodes
            }
        else:
            links = {
                link_id: link
                for link_id, link in scenario.network.links.items()
                if not link.disabled
                and link_id not in excluded_links_set
                and link.source in nodes
                and link.target in nodes
            }

        node_count = len(nodes)
        link_count = len(links)

        total_capacity_val = mean_capacity_val = median_capacity_val = 0.0
        min_capacity_val = max_capacity_val = 0.0
        mean_cost_val = median_cost_val = min_cost_val = max_cost_val = 0.0
        if links:
            capacities = [link.capacity for link in links.values()]
            costs = [link.cost for link in links.values()]

            total_capacity_val = sum(capacities)
            mean_capacity_val = mean(capacities)
            median_capacity_val = median(capacities)
            min_capacity_val = min(capacities)
            max_capacity_val = max(capacities)

            mean_cost_val = mean(costs)
            median_cost_val = median(costs)
            min_cost_val = min(costs)
            max_cost_val = max(costs)

        # Compute degree statistics over the selected node set
        mean_degree_val = median_degree_val = min_degree_val = max_degree_val = 0.0
        if nodes:
            degrees: Dict[str, int] = {name: 0 for name in nodes}

            for link in links.values():
                if link.source in degrees:
                    degrees[link.source] += 1
                if link.target in degrees:
                    degrees[link.target] += 1

            degree_values = list(degrees.values())
            mean_degree_val = mean(degree_values)
            median_degree_val = median(degree_values)
            min_degree_val = min(degree_values)
            max_degree_val = max(degree_values)

        # Store results
        scenario.results.put("metadata", {})
        scenario.results.put(
            "data",
            {
                "node_count": int(node_count),
                "link_count": int(link_count),
                "total_capacity": float(total_capacity_val),
                "mean_capacity": float(mean_capacity_val),
                "median_capacity": float(median_capacity_val),
                "min_capacity": float(min_capacity_val),
                "max_capacity": float(max_capacity_val),
                "mean_cost": float(mean_cost_val),
                "median_cost": float(median_cost_val),
                "min_cost": float(min_cost_val),
                "max_cost": float(max_cost_val),
                "mean_degree": float(mean_degree_val),
                "median_degree": float(median_degree_val),
                "min_degree": float(min_degree_val),
                "max_degree": float(max_degree_val),
            },
        )

        logger.info(
            "NetworkStats completed: name=%s nodes=%d links=%d total_capacity=%.1f",
            self.name,
            node_count,
            link_count,
            float(total_capacity_val),
        )


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("NetworkStats")(NetworkStats)
