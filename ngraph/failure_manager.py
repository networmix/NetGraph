"""FailureManager class for running Monte Carlo failure simulations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from ngraph.lib.flow_policy import FlowPolicyConfig
from ngraph.network import Network
from ngraph.network_view import NetworkView
from ngraph.results_artifacts import FailurePolicySet, TrafficMatrixSet
from ngraph.traffic_manager import TrafficManager, TrafficResult


class FailureManager:
    """Applies a FailurePolicy to a Network to determine exclusions, then uses a
    NetworkView to simulate the impact of those exclusions on traffic.

    This class is the orchestrator for failure analysis. It does not modify the
    base Network. Instead, it:
    1.  Uses a FailurePolicy to calculate which nodes/links should be excluded.
    2.  Creates a NetworkView with those exclusions.
    3.  Runs traffic placement against the view using a TrafficManager.

    The use of NetworkView ensures:
    - Base network remains unmodified during analysis
    - Concurrent Monte Carlo simulations can run safely in parallel
    - Clear separation between scenario-disabled elements (persistent) and
      analysis-excluded elements (temporary)

    For concurrent analysis, prefer using NetworkView directly rather than
    FailureManager when you need fine-grained control over exclusions.

    Attributes:
        network (Network): The underlying network (not modified).
        traffic_matrix_set (TrafficMatrixSet): Traffic matrices to place after exclusions.
        failure_policy_set (FailurePolicySet): Set of named failure policies.
        matrix_name (Optional[str]): The specific traffic matrix to use from the set.
        policy_name (Optional[str]): Name of specific failure policy to use, or None for default.
        default_flow_policy_config (Optional[FlowPolicyConfig]): Default flow placement
            policy if not specified elsewhere.
    """

    def __init__(
        self,
        network: Network,
        traffic_matrix_set: TrafficMatrixSet,
        failure_policy_set: FailurePolicySet,
        matrix_name: Optional[str] = None,
        policy_name: Optional[str] = None,
        default_flow_policy_config: Optional[FlowPolicyConfig] = None,
    ) -> None:
        """Initialize a FailureManager.

        Args:
            network: The Network to simulate failures on (not modified).
            traffic_matrix_set: Traffic matrices containing demands to place after failures.
            failure_policy_set: Set of named failure policies.
            matrix_name: Name of specific matrix to use. If None, uses default matrix.
            policy_name: Name of specific failure policy to use. If None, uses default policy.
            default_flow_policy_config: Default FlowPolicyConfig if demands do not specify one.
        """
        self.network = network
        self.traffic_matrix_set = traffic_matrix_set
        self.failure_policy_set = failure_policy_set
        self.matrix_name = matrix_name
        self.policy_name = policy_name
        self.default_flow_policy_config = default_flow_policy_config

    def get_failed_entities(self) -> Tuple[List[str], List[str]]:
        """Get the nodes and links that are designated for exclusion by the current policy.

        This method interprets the failure policy but does not create a NetworkView
        or run any analysis.

        Returns:
            Tuple of (failed_nodes, failed_links) where each is a list of IDs.
        """
        # If no policies are defined, there are no failures
        if len(self.failure_policy_set.policies) == 0:
            return [], []  # No policies, no failures

        # Get the failure policy to use
        if self.policy_name:
            # Use specific named policy
            try:
                failure_policy = self.failure_policy_set.get_policy(self.policy_name)
            except KeyError:
                return [], []  # Policy not found, no failures
        else:
            # Use default policy
            failure_policy = self.failure_policy_set.get_default_policy()
            if failure_policy is None:
                return [], []  # No default policy, no failures

        # Collect node/links as dicts {id: attrs}, matching FailurePolicy expectations
        node_map = {n_name: n.attrs for n_name, n in self.network.nodes.items()}
        link_map = {link_id: link.attrs for link_id, link in self.network.links.items()}

        failed_ids = failure_policy.apply_failures(
            node_map, link_map, self.network.risk_groups
        )

        # Separate failed nodes and links
        failed_nodes = []
        failed_links = []
        for f_id in failed_ids:
            if f_id in self.network.nodes:
                failed_nodes.append(f_id)
            elif f_id in self.network.links:
                failed_links.append(f_id)
            elif f_id in self.network.risk_groups:
                # Expand risk group to nodes/links
                # NOTE: This is a simplified expansion. A more robust implementation
                # might need to handle nested risk groups recursively.
                for node_name, node_obj in self.network.nodes.items():
                    if f_id in node_obj.risk_groups:
                        failed_nodes.append(node_name)
                for link_id, link_obj in self.network.links.items():
                    if f_id in link_obj.risk_groups:
                        failed_links.append(link_id)

        return failed_nodes, failed_links

    def run_single_failure_scenario(self) -> List[TrafficResult]:
        """Runs one iteration of a failure scenario.

        This method gets the set of failed entities from the policy, creates a
        NetworkView with those exclusions, places traffic, and returns the results.

        Returns:
            A list of traffic result objects under the applied exclusions.
        """
        # Get the entities that failed according to the policy
        failed_nodes, failed_links = self.get_failed_entities()

        # Create NetworkView by excluding the failed entities
        if failed_nodes or failed_links:
            network_view = NetworkView.from_excluded_sets(
                self.network,
                excluded_nodes=failed_nodes,
                excluded_links=failed_links,
            )
        else:
            # No failures, use base network
            network_view = self.network

        # Build TrafficManager and place demands
        traffic_mgr = TrafficManager(
            network=network_view,
            traffic_matrix_set=self.traffic_matrix_set,
            matrix_name=self.matrix_name,
            default_flow_policy_config=self.default_flow_policy_config
            or FlowPolicyConfig.SHORTEST_PATHS_ECMP,
        )
        traffic_mgr.build_graph()
        traffic_mgr.expand_demands()
        traffic_mgr.place_all_demands()

        # Return detailed traffic results
        return traffic_mgr.get_traffic_results(detailed=True)

    def run_monte_carlo_failures(
        self, iterations: int, parallelism: int = 1
    ) -> Dict[str, Any]:
        """Repeatedly runs failure scenarios and accumulates traffic placement results.

        This is used for Monte Carlo analysis where failure policies have a random
        component. Each trial is independent.

        Args:
            iterations (int): Number of times to run the failure scenario.
            parallelism (int): Number of parallel processes to use.

        Returns:
            A dictionary of aggregated results from all trials.
        """
        if parallelism > 1:
            # Parallel execution
            scenario_list: List[List[TrafficResult]] = []
            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                futures = [
                    executor.submit(self.run_single_failure_scenario)
                    for _ in range(iterations)
                ]
                for future in as_completed(futures):
                    scenario_list.append(future.result())
        else:
            # Serial execution
            scenario_list: List[List[TrafficResult]] = []
            for _ in range(iterations):
                scenario_list.append(self.run_single_failure_scenario())

        return self._aggregate_mc_results(scenario_list)

    def _aggregate_mc_results(
        self, results: List[List[TrafficResult]]
    ) -> Dict[str, Any]:
        """(Not implemented) Aggregates results from multiple Monte Carlo runs."""
        # TODO: Implement aggregation logic based on desired output format.
        # For now, just return the raw list of results.
        return {"raw_results": results}
