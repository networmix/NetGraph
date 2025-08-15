"""Workflow step for basic node and link statistics.

Computes and stores network statistics including node/link counts,
capacity distributions, cost distributions, and degree distributions. Supports
optional exclusion simulation and disabled entity handling.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: NetworkStats
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
from typing import TYPE_CHECKING, Dict, Iterable, List

from ngraph.logging import get_logger
from ngraph.model.view import NetworkView
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@dataclass
class NetworkStats(WorkflowStep):
    """Compute basic node and link statistics for the network.

    Supports optional exclusion simulation using NetworkView without modifying the base network.

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

        If `excluded_nodes` or `excluded_links` are specified, uses `NetworkView` to
        simulate exclusions without modifying the base network.

        Args:
            scenario: The scenario containing the network to analyze.

        Returns:
            None
        """
        # Create view if we have exclusions, otherwise use base network
        if self.excluded_nodes or self.excluded_links:
            network_or_view = NetworkView.from_excluded_sets(
                scenario.network,
                excluded_nodes=self.excluded_nodes,
                excluded_links=self.excluded_links,
            )
            nodes = network_or_view.nodes
            links = network_or_view.links
        else:
            # Use base network, optionally filtering disabled
            if self.include_disabled:
                nodes = scenario.network.nodes
                links = scenario.network.links
            else:
                nodes = {
                    name: node
                    for name, node in scenario.network.nodes.items()
                    if not node.disabled
                }
                links = {
                    link_id: link
                    for link_id, link in scenario.network.links.items()
                    if not link.disabled
                    and link.source in nodes  # Source node must be enabled
                    and link.target in nodes  # Target node must be enabled
                }

        # Compute node statistics
        node_count = len(nodes)

        # Compute link statistics
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

        # Compute degree statistics (only for enabled nodes)
        degree_values: List[int] = []
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

        # INFO summary for workflow users (avoid expensive work unless needed)
        total_capacity = 0.0
        if links:
            total_capacity = float(sum(link.capacity for link in links.values()))
        mean_deg = float(mean(degree_values)) if degree_values else 0.0
        get_logger(__name__).info(
            "NetworkStats summary: name=%s nodes=%d links=%d total_capacity=%.1f mean_degree=%.2f",
            self.name,
            node_count,
            link_count,
            total_capacity,
            mean_deg,
        )
        # Store results in new schema
        scenario.results.put("metadata", {})
        # Ensure locals exist even when sets are empty
        if not links:
            total_capacity_val = mean_capacity_val = median_capacity_val = 0.0
            min_capacity_val = max_capacity_val = 0.0
            mean_cost_val = median_cost_val = min_cost_val = max_cost_val = 0.0
        if not nodes:
            mean_degree_val = median_degree_val = min_degree_val = max_degree_val = 0.0

        scenario.results.put(
            "data",
            {
                "node_count": int(node_count),
                "link_count": int(link_count),
                "total_capacity": float(total_capacity_val) if links else 0.0,
                "mean_capacity": float(mean_capacity_val) if links else 0.0,
                "median_capacity": float(median_capacity_val) if links else 0.0,
                "min_capacity": float(min_capacity_val) if links else 0.0,
                "max_capacity": float(max_capacity_val) if links else 0.0,
                "mean_cost": float(mean_cost_val) if links else 0.0,
                "median_cost": float(median_cost_val) if links else 0.0,
                "min_cost": float(min_cost_val) if links else 0.0,
                "max_cost": float(max_cost_val) if links else 0.0,
                "mean_degree": float(mean_degree_val) if nodes else 0.0,
                "median_degree": float(median_degree_val) if nodes else 0.0,
                "min_degree": float(min_degree_val) if nodes else 0.0,
                "max_degree": float(max_degree_val) if nodes else 0.0,
            },
        )


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("NetworkStats")(NetworkStats)
