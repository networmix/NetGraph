"""Capacity envelope analysis workflow component."""

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
from ngraph.logging import get_logger
from ngraph.results_artifacts import CapacityEnvelope
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.failure_policy import FailurePolicy
    from ngraph.network import Network
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


def _worker(args: tuple[Any, ...]) -> tuple[list[tuple[str, str, float]], float]:
    """Worker function for parallel capacity envelope analysis.

    Args:
        args: Tuple containing (base_network, base_policy, source_regex, sink_regex,
              mode, shortest_path, flow_placement, seed_offset, is_baseline, step_name)

    Returns:
        Tuple of (flow_results, total_capacity) where:
        - flow_results: List of (src_label, dst_label, flow_value) tuples
        - total_capacity: Sum of all flow values for this iteration
    """
    # Set up worker-specific logger
    worker_logger = get_logger(f"{__name__}.worker")

    (
        base_network,
        base_policy,
        source_regex,
        sink_regex,
        mode,
        shortest_path,
        flow_placement,
        seed_offset,
        is_baseline,
        step_name,
    ) = args

    # Optional per-worker profiling -------------------------------------------------
    profile_dir_env = os.getenv("NGRAPH_PROFILE_DIR")
    collect_profile: bool = bool(profile_dir_env)

    profiler: "cProfile.Profile | None" = None  # Lazy init to avoid overhead
    if collect_profile:
        import cProfile  # Local import to avoid cost when profiling disabled

        profiler = cProfile.Profile()
        profiler.enable()

    worker_pid = os.getpid()
    worker_logger.debug(f"Worker {worker_pid} started with seed_offset={seed_offset}")

    # Set up unique random seed for this worker iteration
    if seed_offset is not None:
        random.seed(seed_offset)
        worker_logger.debug(
            f"Worker {worker_pid} using provided seed offset: {seed_offset}"
        )
    else:
        # Use pid ^ time_ns for statistical independence when no seed provided
        actual_seed = worker_pid ^ time.time_ns()
        random.seed(actual_seed)
        worker_logger.debug(f"Worker {worker_pid} generated seed: {actual_seed}")

    # Work on deep copies to avoid modifying shared data
    worker_logger.debug(
        f"Worker {worker_pid} creating deep copies of network and policy"
    )
    net = copy.deepcopy(base_network)
    pol = copy.deepcopy(base_policy) if base_policy else None

    # Apply failures unless this is a baseline iteration
    if pol and not is_baseline:
        pol.use_cache = False  # Local run, no benefit to caching
        worker_logger.debug(f"Worker {worker_pid} applying failure policy")

        # Apply failures to the network
        node_map = {n_name: n.attrs for n_name, n in net.nodes.items()}
        link_map = {link_name: link.attrs for link_name, link in net.links.items()}

        failed_ids = pol.apply_failures(node_map, link_map, net.risk_groups)
        worker_logger.debug(
            f"Worker {worker_pid} applied failures: {len(failed_ids)} entities failed"
        )

        # Disable the failed entities
        for f_id in failed_ids:
            if f_id in net.nodes:
                net.disable_node(f_id)
            elif f_id in net.links:
                net.disable_link(f_id)
            elif f_id in net.risk_groups:
                net.disable_risk_group(f_id, recursive=True)

        if failed_ids:
            worker_logger.debug(
                f"Worker {worker_pid} disabled failed entities: {failed_ids}"
            )
    elif is_baseline:
        worker_logger.debug(
            f"Worker {worker_pid} running baseline iteration (no failures)"
        )
    else:
        worker_logger.debug(f"Worker {worker_pid} no failure policy provided")

    # Compute max flow using the configured parameters
    worker_logger.debug(
        f"Worker {worker_pid} computing max flow: source={source_regex}, sink={sink_regex}, mode={mode}"
    )
    flows = net.max_flow(
        source_regex,
        sink_regex,
        mode=mode,
        shortest_path=shortest_path,
        flow_placement=flow_placement,
    )

    # Flatten to a pickle-friendly list and calculate total capacity
    result = [(src, dst, val) for (src, dst), val in flows.items()]
    total_capacity = sum(val for _, _, val in result)

    worker_logger.debug(f"Worker {worker_pid} computed {len(result)} flow results")
    worker_logger.debug(f"Worker {worker_pid} total capacity: {total_capacity:.2f}")

    # Dump profile if enabled ------------------------------------------------------
    if profiler is not None:
        profiler.disable()
        try:
            import pstats
            import uuid
            from pathlib import Path

            profile_dir = Path(profile_dir_env) if profile_dir_env else None
            if profile_dir is not None:
                profile_dir.mkdir(parents=True, exist_ok=True)
                unique_id = uuid.uuid4().hex[:8]
                profile_path = (
                    profile_dir / f"{step_name}_worker_{worker_pid}_{unique_id}.pstats"
                )
                pstats.Stats(profiler).dump_stats(profile_path)
                worker_logger.debug("Saved worker profile to %s", profile_path.name)
        except Exception as exc:  # pragma: no cover – best-effort profiling
            worker_logger.warning(
                "Failed to save worker profile: %s: %s", type(exc).__name__, exc
            )

    return result, total_capacity


def _run_single_iteration(
    base_network: "Network",
    base_policy: "FailurePolicy | None",
    source: str,
    sink: str,
    mode: str,
    shortest_path: bool,
    flow_placement: FlowPlacement,
    samples: dict[tuple[str, str], list[float]],
    total_capacity_samples: list[float],
    seed_offset: int | None = None,
    is_baseline: bool = False,
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
        samples: Dictionary to accumulate flow results into
        total_capacity_samples: List to accumulate total capacity values into
        seed_offset: Optional seed offset for deterministic results
        is_baseline: Whether this is a baseline iteration (no failures)
    """
    baseline_msg = " (baseline)" if is_baseline else ""
    logger.debug(
        f"Running single iteration{baseline_msg} with seed_offset={seed_offset}"
    )
    flow_results, total_capacity = _worker(
        (
            base_network,
            base_policy,
            source,
            sink,
            mode,
            shortest_path,
            flow_placement,
            seed_offset,
            is_baseline,
            "",  # step_name not available in serial execution
        )
    )
    logger.debug(
        f"Single iteration{baseline_msg} produced {len(flow_results)} flow results, total capacity: {total_capacity:.2f}"
    )

    # Store individual flow results
    for src, dst, val in flow_results:
        if (src, dst) not in samples:
            samples[(src, dst)] = []
        samples[(src, dst)].append(val)

    # Store total capacity for this iteration
    total_capacity_samples.append(total_capacity)


@dataclass
class CapacityEnvelopeAnalysis(WorkflowStep):
    """A workflow step that samples maximum capacity between node groups across random failures.

    Performs Monte-Carlo analysis by repeatedly applying failures and measuring capacity
    to build statistical envelopes of network resilience. Results include both individual
    flow capacity envelopes and total capacity samples per iteration.

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
            baseline: true                            # Optional: Run first iteration without failures
            seed: 42                                  # Optional: Seed for reproducible results
        ```

    Results stored in scenario.results:
        - `capacity_envelopes`: Dictionary mapping flow keys to CapacityEnvelope data
        - `total_capacity_samples`: List of total capacity values per iteration

    Attributes:
        source_path: Regex pattern to select source node groups.
        sink_path: Regex pattern to select sink node groups.
        mode: "combine" or "pairwise" flow analysis mode (default: "combine").
        failure_policy: Name of failure policy in scenario.failure_policy_set (optional).
        iterations: Number of Monte-Carlo trials (default: 1).
        parallelism: Number of parallel worker processes (default: 1).
        shortest_path: If True, use shortest paths only (default: False).
        flow_placement: Flow placement strategy (default: PROPORTIONAL).
        baseline: If True, run first iteration without failures as baseline (default: False).
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
    baseline: bool = False
    seed: int | None = None

    def __post_init__(self):
        """Validate parameters and convert string flow_placement to enum."""
        if self.iterations < 1:
            raise ValueError("iterations must be >= 1")
        if self.parallelism < 1:
            raise ValueError("parallelism must be >= 1")
        if self.mode not in {"combine", "pairwise"}:
            raise ValueError("mode must be 'combine' or 'pairwise'")
        if self.baseline and self.iterations < 2:
            raise ValueError(
                "baseline=True requires iterations >= 2 "
                "(first iteration is baseline, remaining are with failures)"
            )

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
        # Log analysis parameters (base class handles start/end timing)
        logger.debug(
            f"Analysis parameters: source_path={self.source_path}, sink_path={self.sink_path}, "
            f"mode={self.mode}, iterations={self.iterations}, parallelism={self.parallelism}, "
            f"failure_policy={self.failure_policy}, baseline={self.baseline}"
        )

        # Get the failure policy to use
        base_policy = self._get_failure_policy(scenario)
        if base_policy:
            logger.debug(
                f"Using failure policy: {self.failure_policy} with {len(base_policy.rules)} rules"
            )
        else:
            logger.debug("No failure policy specified - running baseline analysis only")

        if self.baseline:
            logger.info(
                "Baseline mode enabled: first iteration will run without failures"
            )

        # Validate iterations parameter based on failure policy
        self._validate_iterations_parameter(base_policy)

        # Determine actual number of iterations to run
        mc_iters = self._get_monte_carlo_iterations(base_policy)
        logger.info(f"Running {mc_iters} Monte-Carlo iterations")

        # Run analysis (serial or parallel)
        samples, total_capacity_samples = self._run_capacity_analysis(
            scenario.network, base_policy, mc_iters
        )

        # Build capacity envelopes from samples
        envelopes = self._build_capacity_envelopes(samples)
        logger.info(f"Generated {len(envelopes)} capacity envelopes")

        # Store results in scenario
        scenario.results.put(self.name, "capacity_envelopes", envelopes)
        scenario.results.put(
            self.name, "total_capacity_samples", total_capacity_samples
        )

        # Log summary statistics for total capacity
        if total_capacity_samples:
            min_capacity = min(total_capacity_samples)
            max_capacity = max(total_capacity_samples)
            mean_capacity = sum(total_capacity_samples) / len(total_capacity_samples)
            logger.info(
                f"Total capacity statistics: min={min_capacity:.2f}, max={max_capacity:.2f}, "
                f"mean={mean_capacity:.2f} (from {len(total_capacity_samples)} samples)"
            )

        logger.info(f"Capacity envelope analysis completed: {self.name}")

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
            ValueError: If iterations > 1 when no failure policy is provided and baseline=False.
        """
        if (
            (policy is None or not policy.rules)
            and self.iterations > 1
            and not self.baseline
        ):
            raise ValueError(
                f"iterations={self.iterations} is meaningless without a failure policy. "
                f"Without failures, all iterations produce identical results. "
                f"Either set iterations=1, provide a failure_policy with rules, or set baseline=True."
            )

    def _run_capacity_analysis(
        self, network: "Network", policy: "FailurePolicy | None", mc_iters: int
    ) -> tuple[dict[tuple[str, str], list[float]], list[float]]:
        """Run the capacity analysis iterations.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations

        Returns:
            Tuple of (samples, total_capacity_samples) where:
            - samples: Dictionary mapping (src_label, dst_label) to list of capacity samples
            - total_capacity_samples: List of total capacity values per iteration
        """
        samples: dict[tuple[str, str], list[float]] = defaultdict(list)
        total_capacity_samples: list[float] = []

        # Determine if we should run in parallel
        use_parallel = self.parallelism > 1 and mc_iters > 1

        if use_parallel:
            logger.info(
                f"Running capacity analysis in parallel with {self.parallelism} workers"
            )
            self._run_parallel_analysis(
                network, policy, mc_iters, samples, total_capacity_samples
            )
        else:
            logger.info("Running capacity analysis serially")
            self._run_serial_analysis(
                network, policy, mc_iters, samples, total_capacity_samples
            )

        logger.debug(f"Collected samples for {len(samples)} flow pairs")
        logger.debug(f"Collected {len(total_capacity_samples)} total capacity samples")
        return samples, total_capacity_samples

    def _run_parallel_analysis(
        self,
        network: "Network",
        policy: "FailurePolicy | None",
        mc_iters: int,
        samples: dict[tuple[str, str], list[float]],
        total_capacity_samples: list[float],
    ) -> None:
        """Run capacity analysis in parallel using ProcessPoolExecutor.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations
            samples: Dictionary to accumulate flow results into
            total_capacity_samples: List to accumulate total capacity values into
        """
        # Limit workers to available iterations
        workers = min(self.parallelism, mc_iters)
        logger.info(
            f"Starting parallel analysis with {workers} workers for {mc_iters} iterations"
        )

        # Build worker arguments
        worker_args = []
        for i in range(mc_iters):
            seed_offset = None
            if self.seed is not None:
                seed_offset = self.seed + i

            # First iteration is baseline if baseline=True
            is_baseline = self.baseline and i == 0

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
                    is_baseline,
                    self.name or self.__class__.__name__,
                )
            )

        logger.debug(f"Created {len(worker_args)} worker argument sets")

        # Execute in parallel
        start_time = time.time()
        completed_tasks = 0

        logger.debug(f"Submitting {len(worker_args)} tasks to process pool")
        logger.debug(
            f"Network size: {len(network.nodes)} nodes, {len(network.links)} links"
        )

        with ProcessPoolExecutor(max_workers=workers) as pool:
            logger.debug(f"ProcessPoolExecutor created with {workers} workers")
            logger.info(f"Starting parallel execution of {mc_iters} iterations")

            try:
                for flow_results, total_capacity in pool.map(
                    _worker, worker_args, chunksize=1
                ):
                    completed_tasks += 1

                    # Add flow results to samples
                    result_count = len(flow_results)
                    for src, dst, val in flow_results:
                        samples[(src, dst)].append(val)

                    # Add total capacity to samples
                    total_capacity_samples.append(total_capacity)

                    # Progress logging
                    if (
                        completed_tasks % max(1, mc_iters // 10) == 0
                    ):  # Log every 10% completion
                        logger.info(
                            f"Parallel analysis progress: {completed_tasks}/{mc_iters} tasks completed"
                        )
                        logger.debug(
                            f"Latest task produced {result_count} flow results, total capacity: {total_capacity:.2f}"
                        )

            except Exception as e:
                logger.error(
                    f"Error during parallel execution: {type(e).__name__}: {e}"
                )
                logger.debug(f"Failed after {completed_tasks} completed tasks")
                raise

        elapsed_time = time.time() - start_time
        logger.info(f"Parallel analysis completed in {elapsed_time:.2f} seconds")
        logger.debug(
            f"Average time per iteration: {elapsed_time / mc_iters:.3f} seconds"
        )
        logger.debug(
            f"Total samples collected: {sum(len(vals) for vals in samples.values())}"
        )

    def _run_serial_analysis(
        self,
        network: "Network",
        policy: "FailurePolicy | None",
        mc_iters: int,
        samples: dict[tuple[str, str], list[float]],
        total_capacity_samples: list[float],
    ) -> None:
        """Run capacity analysis serially.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations
            samples: Dictionary to accumulate flow results into
            total_capacity_samples: List to accumulate total capacity values into
        """
        logger.debug("Starting serial analysis")
        start_time = time.time()

        for i in range(mc_iters):
            iter_start = time.time()
            seed_offset = None
            if self.seed is not None:
                seed_offset = self.seed + i

            # First iteration is baseline if baseline=True
            is_baseline = self.baseline and i == 0
            baseline_msg = " (baseline)" if is_baseline else ""

            if seed_offset is not None:
                logger.debug(
                    f"Serial iteration {i + 1}/{mc_iters}{baseline_msg} with seed offset {seed_offset}"
                )
            else:
                logger.debug(f"Serial iteration {i + 1}/{mc_iters}{baseline_msg}")

            _run_single_iteration(
                network,
                policy,
                self.source_path,
                self.sink_path,
                self.mode,
                self.shortest_path,
                self.flow_placement,
                samples,
                total_capacity_samples,
                seed_offset,
                is_baseline,
            )

            iter_time = time.time() - iter_start
            if mc_iters <= 10:  # Log individual iteration times for small runs
                logger.debug(
                    f"Serial iteration {i + 1} completed in {iter_time:.3f} seconds"
                )

            if (
                mc_iters > 1 and (i + 1) % max(1, mc_iters // 10) == 0
            ):  # Log every 10% completion
                logger.info(
                    f"Serial analysis progress: {i + 1}/{mc_iters} iterations completed"
                )
                avg_time = (time.time() - start_time) / (i + 1)
                logger.debug(f"Average iteration time so far: {avg_time:.3f} seconds")

        elapsed_time = time.time() - start_time
        logger.info(f"Serial analysis completed in {elapsed_time:.2f} seconds")
        if mc_iters > 1:
            logger.debug(
                f"Average time per iteration: {elapsed_time / mc_iters:.3f} seconds"
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
        logger.debug(f"Building capacity envelopes from {len(samples)} flow pairs")
        envelopes = {}

        for (src_label, dst_label), capacity_values in samples.items():
            if not capacity_values:
                logger.warning(
                    f"No capacity values found for flow {src_label}->{dst_label}"
                )
                continue

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

            # Detailed logging with statistics
            min_val = min(capacity_values)
            max_val = max(capacity_values)
            mean_val = sum(capacity_values) / len(capacity_values)
            logger.debug(
                f"Created envelope for {flow_key}: {len(capacity_values)} samples, "
                f"min={min_val:.2f}, max={max_val:.2f}, mean={mean_val:.2f}"
            )

        logger.debug(f"Successfully created {len(envelopes)} capacity envelopes")
        return envelopes


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("CapacityEnvelopeAnalysis")(CapacityEnvelopeAnalysis)
