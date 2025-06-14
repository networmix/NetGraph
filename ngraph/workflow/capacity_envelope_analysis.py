from __future__ import annotations

import copy
import os
import random
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.results_artifacts import CapacityEnvelope
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.failure_policy import FailurePolicy
    from ngraph.network import Network
    from ngraph.scenario import Scenario


def _worker(args: tuple[Any, ...]) -> list[tuple[str, str, float]]:
    """Worker function for parallel capacity envelope analysis.

    Args:
        args: Tuple containing (base_network, base_policy, source_regex, sink_regex,
              mode, shortest_path, flow_placement, seed_offset)

    Returns:
        List of (src_label, dst_label, flow_value) tuples from max_flow results.
    """
    (
        base_network,
        base_policy,
        source_regex,
        sink_regex,
        mode,
        shortest_path,
        flow_placement,
        seed_offset,
    ) = args

    # Set up unique random seed for this worker iteration
    if seed_offset is not None:
        random.seed(seed_offset)
    else:
        # Use pid ^ time_ns for statistical independence when no seed provided
        random.seed(os.getpid() ^ time.time_ns())

    # Work on deep copies to avoid modifying shared data
    net = copy.deepcopy(base_network)
    pol = copy.deepcopy(base_policy) if base_policy else None

    if pol:
        pol.use_cache = False  # Local run, no benefit to caching

        # Apply failures to the network
        node_map = {n_name: n.attrs for n_name, n in net.nodes.items()}
        link_map = {link_name: link.attrs for link_name, link in net.links.items()}

        failed_ids = pol.apply_failures(node_map, link_map, net.risk_groups)

        # Disable the failed entities
        for f_id in failed_ids:
            if f_id in net.nodes:
                net.disable_node(f_id)
            elif f_id in net.links:
                net.disable_link(f_id)
            elif f_id in net.risk_groups:
                net.disable_risk_group(f_id, recursive=True)

    # Compute max flow using the configured parameters
    flows = net.max_flow(
        source_regex,
        sink_regex,
        mode=mode,
        shortest_path=shortest_path,
        flow_placement=flow_placement,
    )

    # Flatten to a pickle-friendly list
    return [(src, dst, val) for (src, dst), val in flows.items()]


def _run_single_iteration(
    base_network: "Network",
    base_policy: "FailurePolicy | None",
    source: str,
    sink: str,
    mode: str,
    shortest_path: bool,
    flow_placement: FlowPlacement,
    samples: dict[tuple[str, str], list[float]],
    seed_offset: int | None = None,
) -> None:
    """Run a single iteration of capacity analysis (for serial execution).

    Args:
        base_network: Network to analyze
        base_policy: Failure policy to apply (if any)
        source: Source regex pattern
        sink: Sink regex pattern
        mode: Flow analysis mode ("combine" or "pairwise")
        shortest_path: Whether to use shortest path only
        flow_placement: Flow placement strategy
        samples: Dictionary to accumulate results into
        seed_offset: Optional seed offset for deterministic results
    """
    res = _worker(
        (
            base_network,
            base_policy,
            source,
            sink,
            mode,
            shortest_path,
            flow_placement,
            seed_offset,
        )
    )
    for src, dst, val in res:
        if (src, dst) not in samples:
            samples[(src, dst)] = []
        samples[(src, dst)].append(val)


@dataclass
class CapacityEnvelopeAnalysis(WorkflowStep):
    """A workflow step that samples maximum capacity between node groups across random failures.

    Performs Monte-Carlo analysis by repeatedly applying failures and measuring capacity
    to build statistical envelopes of network resilience.

    YAML Configuration:
        ```yaml
        workflow:
          - step_type: CapacityEnvelopeAnalysis
            name: "capacity_envelope_monte_carlo"     # Optional: Custom name for this step
            source_path: "^datacenter/.*"             # Regex pattern for source node groups
            sink_path: "^edge/.*"                     # Regex pattern for sink node groups
            mode: "combine"                           # "combine" or "pairwise" flow analysis
            failure_policy: "random_failures"        # Optional: Named failure policy to use
            iterations: 1000                          # Number of Monte-Carlo trials
            parallelism: 4                            # Number of parallel worker processes
            shortest_path: false                      # Use shortest paths only
            flow_placement: "PROPORTIONAL"            # Flow placement strategy
            seed: 42                                  # Optional: Seed for reproducible results
        ```

    Attributes:
        source_path: Regex pattern to select source node groups.
        sink_path: Regex pattern to select sink node groups.
        mode: "combine" or "pairwise" flow analysis mode (default: "combine").
        failure_policy: Name of failure policy in scenario.failure_policy_set (optional).
        iterations: Number of Monte-Carlo trials (default: 1).
        parallelism: Number of parallel worker processes (default: 1).
        shortest_path: If True, use shortest paths only (default: False).
        flow_placement: Flow placement strategy (default: PROPORTIONAL).
        seed: Optional seed for deterministic results (for debugging).
    """

    source_path: str = ""
    sink_path: str = ""
    mode: str = "combine"
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int = 1
    shortest_path: bool = False
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL
    seed: int | None = None

    def __post_init__(self):
        """Validate parameters and convert string flow_placement to enum."""
        if self.iterations < 1:
            raise ValueError("iterations must be >= 1")
        if self.parallelism < 1:
            raise ValueError("parallelism must be >= 1")
        if self.mode not in {"combine", "pairwise"}:
            raise ValueError("mode must be 'combine' or 'pairwise'")

        # Convert string flow_placement to enum if needed (like CapacityProbe)
        if isinstance(self.flow_placement, str):
            try:
                self.flow_placement = FlowPlacement[self.flow_placement.upper()]
            except KeyError:
                valid_values = ", ".join([e.name for e in FlowPlacement])
                raise ValueError(
                    f"Invalid flow_placement '{self.flow_placement}'. "
                    f"Valid values are: {valid_values}"
                ) from None

    def run(self, scenario: "Scenario") -> None:
        """Execute the capacity envelope analysis workflow step.

        Args:
            scenario: The scenario containing network, failure policies, and results.
        """
        # Get the failure policy to use
        base_policy = self._get_failure_policy(scenario)

        # Validate iterations parameter based on failure policy
        self._validate_iterations_parameter(base_policy)

        # Determine actual number of iterations to run
        mc_iters = self._get_monte_carlo_iterations(base_policy)

        # Run analysis (serial or parallel)
        samples = self._run_capacity_analysis(scenario.network, base_policy, mc_iters)

        # Build capacity envelopes from samples
        envelopes = self._build_capacity_envelopes(samples)

        # Store results in scenario
        scenario.results.put(self.name, "capacity_envelopes", envelopes)

    def _get_failure_policy(self, scenario: "Scenario") -> "FailurePolicy | None":
        """Get the failure policy to use for this analysis.

        Args:
            scenario: The scenario containing failure policy set.

        Returns:
            FailurePolicy instance or None if no failures should be applied.
        """
        if self.failure_policy is not None:
            # Use specific named policy
            try:
                return scenario.failure_policy_set.get_policy(self.failure_policy)
            except KeyError:
                raise ValueError(
                    f"Failure policy '{self.failure_policy}' not found in scenario"
                ) from None
        else:
            # Use default policy (may return None)
            return scenario.failure_policy_set.get_default_policy()

    def _get_monte_carlo_iterations(self, policy: "FailurePolicy | None") -> int:
        """Determine how many Monte-Carlo iterations to run.

        Args:
            policy: The failure policy to use (if any).

        Returns:
            Number of iterations (1 if no policy has rules, otherwise self.iterations).
        """
        if policy is None or not policy.rules:
            return 1  # Baseline only, no failures
        return self.iterations

    def _validate_iterations_parameter(self, policy: "FailurePolicy | None") -> None:
        """Validate that iterations parameter is appropriate for the failure policy.

        Args:
            policy: The failure policy to use (if any).

        Raises:
            ValueError: If iterations > 1 when no failure policy is provided.
        """
        if (policy is None or not policy.rules) and self.iterations > 1:
            raise ValueError(
                f"iterations={self.iterations} is meaningless without a failure policy. "
                f"Without failures, all iterations produce identical results. "
                f"Either set iterations=1 or provide a failure_policy with rules."
            )

    def _run_capacity_analysis(
        self, network: "Network", policy: "FailurePolicy | None", mc_iters: int
    ) -> dict[tuple[str, str], list[float]]:
        """Run the capacity analysis iterations.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations

        Returns:
            Dictionary mapping (src_label, dst_label) to list of capacity samples.
        """
        samples: dict[tuple[str, str], list[float]] = defaultdict(list)

        # Determine if we should run in parallel
        use_parallel = self.parallelism > 1 and mc_iters > 1

        if use_parallel:
            self._run_parallel_analysis(network, policy, mc_iters, samples)
        else:
            self._run_serial_analysis(network, policy, mc_iters, samples)

        return samples

    def _run_parallel_analysis(
        self,
        network: "Network",
        policy: "FailurePolicy | None",
        mc_iters: int,
        samples: dict[tuple[str, str], list[float]],
    ) -> None:
        """Run capacity analysis in parallel using ProcessPoolExecutor.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations
            samples: Dictionary to accumulate results into
        """
        # Limit workers to available iterations
        workers = min(self.parallelism, mc_iters)

        # Build worker arguments
        worker_args = []
        for i in range(mc_iters):
            seed_offset = None
            if self.seed is not None:
                seed_offset = self.seed + i

            worker_args.append(
                (
                    network,
                    policy,
                    self.source_path,
                    self.sink_path,
                    self.mode,
                    self.shortest_path,
                    self.flow_placement,
                    seed_offset,
                )
            )

        # Execute in parallel
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(_worker, worker_args, chunksize=1):
                for src, dst, val in result:
                    samples[(src, dst)].append(val)

    def _run_serial_analysis(
        self,
        network: "Network",
        policy: "FailurePolicy | None",
        mc_iters: int,
        samples: dict[tuple[str, str], list[float]],
    ) -> None:
        """Run capacity analysis serially.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations
            samples: Dictionary to accumulate results into
        """
        for i in range(mc_iters):
            seed_offset = None
            if self.seed is not None:
                seed_offset = self.seed + i

            _run_single_iteration(
                network,
                policy,
                self.source_path,
                self.sink_path,
                self.mode,
                self.shortest_path,
                self.flow_placement,
                samples,
                seed_offset,
            )

    def _build_capacity_envelopes(
        self, samples: dict[tuple[str, str], list[float]]
    ) -> dict[str, dict[str, Any]]:
        """Build CapacityEnvelope objects from collected samples.

        Args:
            samples: Dictionary mapping (src_label, dst_label) to capacity values.

        Returns:
            Dictionary mapping flow keys to serialized CapacityEnvelope data.
        """
        envelopes = {}

        for (src_label, dst_label), capacity_values in samples.items():
            # Create capacity envelope
            envelope = CapacityEnvelope(
                source_pattern=self.source_path,
                sink_pattern=self.sink_path,
                mode=self.mode,
                capacity_values=capacity_values,
            )

            # Use flow key as the result key
            flow_key = f"{src_label}->{dst_label}"
            envelopes[flow_key] = envelope.to_dict()

        return envelopes


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("CapacityEnvelopeAnalysis")(CapacityEnvelopeAnalysis)
