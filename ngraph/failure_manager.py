"""FailureManager class for running Monte Carlo failure simulations."""

from __future__ import annotations

import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from ngraph.lib.flow_policy import FlowPolicyConfig
from ngraph.network import Network
from ngraph.results_artifacts import FailurePolicySet, TrafficMatrixSet
from ngraph.traffic_manager import TrafficManager, TrafficResult


class FailureManager:
    """Applies FailurePolicy to a Network, runs traffic placement, and (optionally)
    repeats multiple times for Monte Carlo experiments.

    Attributes:
        network (Network): The underlying network to mutate (enable/disable nodes/links).
        traffic_matrix_set (TrafficMatrixSet): Traffic matrices to place after failures.
        failure_policy_set (FailurePolicySet): Set of named failure policies.
        matrix_name (Optional[str]): Name of specific matrix to use, or None for default.
        policy_name (Optional[str]): Name of specific failure policy to use, or None for default.
        default_flow_policy_config: The default flow policy for any demands lacking one.
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
            network: The Network to be modified by failures.
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

    def apply_failures(self) -> None:
        """Apply the current failure policy to self.network (in-place).

        If failure_policy_set is empty or no valid policy is found, this method does nothing.
        """
        # Check if we have any policies
        if len(self.failure_policy_set.policies) == 0:
            return  # No policies, do nothing

        # Get the failure policy to use
        if self.policy_name:
            # Use specific named policy
            try:
                failure_policy = self.failure_policy_set.get_policy(self.policy_name)
            except KeyError:
                return  # Policy not found, do nothing
        else:
            # Use default policy
            failure_policy = self.failure_policy_set.get_default_policy()
            if failure_policy is None:
                return  # No default policy, do nothing

        # Collect node/links as dicts {id: attrs}, matching FailurePolicy expectations
        node_map = {n_name: n.attrs for n_name, n in self.network.nodes.items()}
        link_map = {link_id: link.attrs for link_id, link in self.network.links.items()}

        failed_ids = failure_policy.apply_failures(node_map, link_map)

        # Disable the failed entities
        for f_id in failed_ids:
            if f_id in self.network.nodes:
                self.network.disable_node(f_id)
            elif f_id in self.network.links:
                self.network.disable_link(f_id)

    def run_single_failure_scenario(self) -> List[TrafficResult]:
        """Applies failures to the network, places the demands, and returns per-demand results.

        Returns:
            List[TrafficResult]: A list of traffic result objects under the applied failures.
        """
        # Ensure we start with a fully enabled network (in case of reuse)
        self.network.enable_all()

        # Apply the current failure policy
        self.apply_failures()

        # Build TrafficManager and place demands
        tmgr = TrafficManager(
            network=self.network,
            traffic_matrix_set=self.traffic_matrix_set,
            matrix_name=self.matrix_name,
            default_flow_policy_config=self.default_flow_policy_config
            or FlowPolicyConfig.SHORTEST_PATHS_ECMP,
        )
        tmgr.build_graph()
        tmgr.expand_demands()
        tmgr.place_all_demands()

        # Return detailed traffic results
        return tmgr.get_traffic_results(detailed=True)

    def run_monte_carlo_failures(
        self,
        iterations: int,
        parallelism: int = 1,
    ) -> Dict[str, Any]:
        """Repeatedly applies (randomized) failures to the network and accumulates
        per-run traffic data. Returns both overall volume statistics and a
        breakdown of results for each (src, dst, priority).

        Args:
            iterations (int): Number of times to run the failure scenario.
            parallelism (int): Max number of worker threads to use (for parallel runs).

        Returns:
            Dict[str, Any]: A dictionary containing:
                {
                    "overall_stats": {
                        "mean": <float>,
                        "stdev": <float>,
                        "min": <float>,
                        "max": <float>
                    },
                    "by_src_dst": {
                        (src, dst, priority): [
                            {
                                "iteration": <int>,
                                "total_volume": <float>,
                                "placed_volume": <float>,
                                "unplaced_volume": <float>
                            },
                            ...
                        ],
                        ...
                    }
                }
        """
        # scenario_list will hold the list of traffic-results (List[TrafficResult]) per iteration
        scenario_list: List[List[TrafficResult]] = []

        # Run in parallel or synchronously
        if parallelism > 1:
            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                futures = [
                    executor.submit(self.run_single_failure_scenario)
                    for _ in range(iterations)
                ]
                for f in as_completed(futures):
                    scenario_list.append(f.result())
        else:
            for _ in range(iterations):
                scenario_list.append(self.run_single_failure_scenario())

        # If no scenarios were run, return zeroed stats
        if not scenario_list:
            return {
                "overall_stats": {"mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0},
                "by_src_dst": {},
            }

        # Accumulate total placed volumes for each iteration (for top-level summary)
        placed_totals: List[float] = []

        # Dictionary mapping (src, dst, priority) -> list of run-by-run results
        by_src_dst: Dict[Tuple[str, str, int], List[Dict[str, float]]] = defaultdict(
            list
        )

        for i, traffic_results in enumerate(scenario_list):
            # Compute total placed volume for this iteration
            scenario_placed_total = sum(r.placed_volume for r in traffic_results)
            placed_totals.append(scenario_placed_total)

            # Accumulate detailed data for each (src, dst, priority)
            for r in traffic_results:
                key = (r.src, r.dst, r.priority)
                by_src_dst[key].append(
                    {
                        "iteration": i,
                        "total_volume": r.total_volume,
                        "placed_volume": r.placed_volume,
                        "unplaced_volume": r.unplaced_volume,
                    }
                )

        # Compute overall statistics on the total placed volumes
        overall_stats = {
            "mean": statistics.mean(placed_totals),
            "stdev": statistics.pstdev(placed_totals),
            "min": min(placed_totals),
            "max": max(placed_totals),
        }

        return {
            "overall_stats": overall_stats,
            "by_src_dst": dict(by_src_dst),
        }
