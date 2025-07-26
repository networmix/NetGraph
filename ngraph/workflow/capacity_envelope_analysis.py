"""Capacity envelope analysis workflow component.

Monte Carlo analysis of network capacity under random failures. Generates statistical
distributions (envelopes) of maximum flow capacity between node groups across failure scenarios.

## Analysis Process

1. **Pre-computation (Main Process)**: Apply failure policies for all Monte Carlo iterations
   upfront in the main process using `_compute_failure_exclusions`. Risk groups are recursively
   expanded to include member nodes/links. This generates small exclusion sets (typically <1%
   of entities) that minimize inter-process communication overhead.

2. **Distribution**: Network is pickled once and shared across worker processes via
   ProcessPoolExecutor initializer. Pre-computed exclusion sets are distributed to workers
   rather than modified network copies, avoiding repeated serialization overhead.

3. **Flow Computation (Workers)**: Each worker creates a NetworkView with exclusions (no copying)
   and computes max flow for each source-sink pair.
   Results are cached based on exclusion patterns since many iterations share identical failure
   sets. Cache is bounded with FIFO eviction.

4. **Statistical Aggregation**: Collect capacity samples from all iterations and build
   frequency-based distributions for memory efficiency. Results include capacity envelopes
   (min/max/mean/percentiles) and optional failure pattern frequency maps.

## Performance Characteristics

**Time Complexity**: O(I × (R + F × A) / P) where I=iterations, R=failure evaluation,
F=flow pairs, A=max-flow algorithm cost, P=parallelism. The max-flow algorithm uses
Ford-Fulkerson with Dijkstra SPF augmentation: A = O(V²E) iterations × O(E log V) per SPF
= O(V²E² log V) worst case, but typically much better. Also, per-worker cache reduces
effective iterations by 60-90% for common failure patterns.

**Space Complexity**: O(V + E + I × F + C) with frequency-based compression reducing
I×F samples to ~√(I×F) entries. Validated by benchmark tests in test suite.

## YAML Configuration Example

```yaml
workflow:
  - step_type: CapacityEnvelopeAnalysis
    name: "capacity_envelope_monte_carlo"     # Optional: Custom name for this step
    source_path: "^datacenter/.*"             # Regex pattern for source node groups
    sink_path: "^edge/.*"                     # Regex pattern for sink node groups
    mode: "combine"                           # "combine" or "pairwise" flow analysis
    failure_policy: "random_failures"         # Optional: Named failure policy to use
    iterations: 1000                          # Number of Monte-Carlo trials
    parallelism: 4                            # Number of parallel worker processes
    shortest_path: false                      # Use shortest paths only
    flow_placement: "PROPORTIONAL"            # Flow placement strategy
    baseline: true                            # Optional: Run first iteration without failures
    seed: 42                                  # Optional: Seed for reproducible results
    store_failure_patterns: false            # Optional: Store failure patterns in results
```

## Results

Results stored in scenario.results:
- `capacity_envelopes`: Dictionary mapping flow keys to CapacityEnvelope data
- `failure_pattern_results`: Frequency map of failure patterns (if store_failure_patterns=True)

"""

from __future__ import annotations

import json
import os
import pickle
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.logging import get_logger
from ngraph.network_view import NetworkView
from ngraph.results_artifacts import (
    CapacityEnvelope,
    FailurePatternResult,
)
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    import cProfile

    from ngraph.failure_policy import FailurePolicy
    from ngraph.network import Network
    from ngraph.scenario import Scenario
else:
    from ngraph.failure_policy import FailurePolicy

logger = get_logger(__name__)

# Global network object shared by all workers in a process pool.
# Each worker process gets its own copy (process isolation) and the network
# is read-only after initialization, making this safe for concurrent access.
_shared_network: "Network | None" = None

# Global flow cache shared by all iterations in a worker process.
# Caches flow computations based on exclusion patterns since many Monte Carlo
# iterations share the same exclusion sets. Cache key includes all parameters
# that affect flow computation to ensure correctness.
_flow_cache: dict[tuple, list[tuple[str, str, float]]] = {}


def _worker_init(network_pickle: bytes) -> None:
    """Initialize a worker process with the shared network object.

    Called exactly once per worker process lifetime via ProcessPoolExecutor's
    initializer mechanism. Network is deserialized once per worker (not per task)
    to avoid repeated serialization overhead. Process boundaries provide
    isolation so no cross-contamination is possible.

    Args:
        network_pickle: Serialized Network object to deserialize and share.
    """
    global _shared_network, _flow_cache

    # Each worker process has its own copy of globals (process isolation)
    _shared_network = pickle.loads(network_pickle)

    # Clear cache to ensure fresh state per analysis
    _flow_cache.clear()

    worker_logger = get_logger(f"{__name__}.worker")
    worker_logger.debug(f"Worker {os.getpid()} initialized with network")


def _compute_failure_exclusions(
    network: "Network",
    policy: "FailurePolicy | None",
    seed_offset: int | None = None,
) -> tuple[set[str], set[str]]:
    """Compute the set of nodes and links that should be excluded for a given failure iteration.

    Applies failure policy logic in the main process and returns
    exclusion sets to workers. This approach is equivalent to
    directly applying failures to the network: NetworkView(network, exclusions) ≡
    network.copy().apply_failures(), but with lower IPC overhead since exclusion
    sets are typically <1% of total entities.

    Args:
        network: Network to analyze (read-only access)
        policy: Failure policy to apply (None for baseline)
        seed_offset: Optional seed for deterministic failures

    Returns:
        Tuple of (excluded_nodes, excluded_links) containing entity IDs to exclude.
    """
    excluded_nodes = set()
    excluded_links = set()

    if policy is None:
        return excluded_nodes, excluded_links

    # Create a temporary copy of the policy with the iteration-specific seed
    # to ensure deterministic but varying results across iterations
    if seed_offset is not None:
        # Create a shallow copy with the iteration-specific seed
        temp_policy = FailurePolicy(
            rules=policy.rules,
            attrs=policy.attrs,
            fail_risk_groups=policy.fail_risk_groups,
            fail_risk_group_children=policy.fail_risk_group_children,
            use_cache=policy.use_cache,
            seed=seed_offset,  # Use iteration-specific seed
        )
    else:
        temp_policy = policy

    # Apply failure policy to determine which entities to exclude
    node_map = {n_name: n.attrs for n_name, n in network.nodes.items()}
    link_map = {link_name: link.attrs for link_name, link in network.links.items()}

    failed_ids = temp_policy.apply_failures(node_map, link_map, network.risk_groups)

    # Separate entity types for NetworkView creation
    for f_id in failed_ids:
        if f_id in network.nodes:
            excluded_nodes.add(f_id)
        elif f_id in network.links:
            excluded_links.add(f_id)
        elif f_id in network.risk_groups:
            # Recursively expand risk groups
            risk_group = network.risk_groups[f_id]
            to_check = [risk_group]
            while to_check:
                grp = to_check.pop()
                # Add all nodes/links in this risk group
                for node_name, node in network.nodes.items():
                    if grp.name in node.risk_groups:
                        excluded_nodes.add(node_name)
                for link_id, link in network.links.items():
                    if grp.name in link.risk_groups:
                        excluded_links.add(link_id)
                # Check children recursively
                to_check.extend(grp.children)

    return excluded_nodes, excluded_links


def _worker(
    args: tuple[Any, ...],
) -> tuple[list[tuple[str, str, float]], int, bool, set[str], set[str]]:
    """Worker function that computes capacity metrics for a given set of exclusions.

    Caches flow computations based on exclusion patterns since many Monte Carlo iterations
    share the same exclusion sets. Flow computation is deterministic for identical
    inputs, making caching safe.

    Args:
        args: Tuple containing (excluded_nodes, excluded_links, source_regex,
              sink_regex, mode, shortest_path, flow_placement, seed_offset, step_name,
              iteration_index, is_baseline)

    Returns:
        Tuple of (flow_results, iteration_index, is_baseline,
                 excluded_nodes, excluded_links) where flow_results is
        a serializable list of (source, sink, capacity) tuples
    """
    global _shared_network
    if _shared_network is None:
        raise RuntimeError("Worker not initialized with network data")

    worker_logger = get_logger(f"{__name__}.worker")

    (
        excluded_nodes,
        excluded_links,
        source_regex,
        sink_regex,
        mode,
        shortest_path,
        flow_placement,
        seed_offset,
        step_name,
        iteration_index,
        is_baseline,
    ) = args

    # Optional per-worker profiling for performance analysis
    profile_dir_env = os.getenv("NGRAPH_PROFILE_DIR")
    collect_profile: bool = bool(profile_dir_env)

    profiler: "cProfile.Profile | None" = None
    if collect_profile:
        import cProfile

        profiler = cProfile.Profile()
        profiler.enable()

    # Worker process ID for logging
    worker_pid = os.getpid()
    worker_logger.debug(
        f"Worker {worker_pid} starting: seed_offset={seed_offset}, "
        f"excluded_nodes={len(excluded_nodes)}, excluded_links={len(excluded_links)}"
    )

    # Create cache key from all parameters affecting flow computation.
    # Sorting ensures consistent keys for same sets regardless of iteration order.
    cache_key = (
        tuple(sorted(excluded_nodes)),
        tuple(sorted(excluded_links)),
        source_regex,
        sink_regex,
        mode,
        shortest_path,
        flow_placement,
    )

    # Check cache first since flow computation is deterministic
    global _flow_cache

    if cache_key in _flow_cache:
        worker_logger.debug(f"Worker {worker_pid} using cached flow results")
        result = _flow_cache[cache_key]
    else:
        worker_logger.debug(f"Worker {worker_pid} computing new flow (cache miss)")
        # Use NetworkView for exclusion without copying network
        network_view = NetworkView.from_excluded_sets(
            _shared_network,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )
        worker_logger.debug(f"Worker {worker_pid} created NetworkView")

        # Compute max flow
        worker_logger.debug(
            f"Worker {worker_pid} computing max flow: source={source_regex}, sink={sink_regex}, mode={mode}"
        )
        flows = network_view.max_flow(
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )

        # Convert to serializable format for inter-process communication
        result = [(src, dst, val) for (src, dst), val in flows.items()]

        # Cache results for future computations
        _flow_cache[cache_key] = result

        # Bound cache size to prevent memory exhaustion (FIFO eviction)
        if len(_flow_cache) > 1000:
            # Remove oldest entries (simple FIFO)
            for _ in range(100):
                _flow_cache.pop(next(iter(_flow_cache)))

        worker_logger.debug(f"Worker {worker_pid} computed {len(result)} flow results")

    # Dump profile if enabled (for performance analysis)
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
        except Exception as exc:  # pragma: no cover
            worker_logger.warning(
                "Failed to save worker profile: %s: %s", type(exc).__name__, exc
            )

    return (
        result,
        iteration_index,
        is_baseline,
        excluded_nodes,
        excluded_links,
    )


@dataclass
class CapacityEnvelopeAnalysis(WorkflowStep):
    """A workflow step that samples maximum capacity between node groups across random failures.

    Performs Monte-Carlo analysis by repeatedly applying failures and measuring capacity
    to build statistical envelopes of network resilience. Results include individual
    flow capacity envelopes across iterations.

    This implementation uses parallel processing:
    - Network is serialized once and shared across all worker processes
    - Failure exclusions are pre-computed in the main process
    - NetworkView excludes entities without copying the network
    - Flow computations are cached within workers to avoid redundant calculations

    All results are stored using frequency-based storage for memory efficiency.

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
        store_failure_patterns: If True, store failure patterns in results (default: False).
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
    store_failure_patterns: bool = False

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

        # Convert string flow_placement to enum if needed
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
        # Log analysis parameters
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

        # Run analysis
        samples, failure_patterns = self._run_capacity_analysis(
            scenario.network, base_policy, mc_iters
        )

        # Build capacity envelopes from samples
        envelopes = self._build_capacity_envelopes(samples)
        logger.info(f"Generated {len(envelopes)} capacity envelopes")

        # Store results in scenario
        scenario.results.put(self.name, "capacity_envelopes", envelopes)

        # Store failure patterns as frequency map if requested
        if self.store_failure_patterns:
            pattern_map = {}
            for pattern in failure_patterns:
                key = json.dumps(
                    {
                        "excluded_nodes": pattern["excluded_nodes"],
                        "excluded_links": pattern["excluded_links"],
                    },
                    sort_keys=True,
                )

                if key not in pattern_map:
                    # Get capacity matrix for this pattern
                    capacity_matrix = {}
                    for flow_key, _envelope_data in envelopes.items():
                        # Find capacity value for this pattern's iteration
                        pattern_iter = pattern["iteration_index"]
                        flow_tuple = self._parse_flow_key(flow_key)
                        if flow_tuple in samples and pattern_iter < len(
                            samples[flow_tuple]
                        ):
                            # Get capacity value from original samples
                            capacity_matrix[flow_key] = samples[flow_tuple][
                                pattern_iter
                            ]

                    pattern_map[key] = FailurePatternResult(
                        excluded_nodes=pattern["excluded_nodes"],
                        excluded_links=pattern["excluded_links"],
                        capacity_matrix=capacity_matrix,
                        count=0,
                        is_baseline=pattern["is_baseline"],
                    )
                pattern_map[key].count += 1

            failure_pattern_results = {
                result.pattern_key: result.to_dict() for result in pattern_map.values()
            }
            scenario.results.put(
                self.name, "failure_pattern_results", failure_pattern_results
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
                f"iterations={self.iterations} has no effect without a failure policy. "
                f"Without failures, all iterations produce the same results. "
                f"Either set iterations=1, provide a failure_policy with rules, or set baseline=True."
            )

    def _run_capacity_analysis(
        self, network: "Network", policy: "FailurePolicy | None", mc_iters: int
    ) -> tuple[dict[tuple[str, str], list[float]], list[dict[str, Any]]]:
        """Run the capacity analysis iterations.

        Args:
            network: Network to analyze
            policy: Failure policy to apply
            mc_iters: Number of Monte-Carlo iterations

        Returns:
            Tuple of (samples, failure_patterns) where:
            - samples: Dictionary mapping (src_label, dst_label) to list of capacity samples
            - failure_patterns: List of failure pattern details per iteration
        """
        samples: dict[tuple[str, str], list[float]] = defaultdict(list)
        failure_patterns: list[dict[str, Any]] = []

        # Pre-compute exclusions for all iterations
        logger.debug("Pre-computing failure exclusions for all iterations")
        pre_compute_start = time.time()

        worker_args = []
        for i in range(mc_iters):
            seed_offset = None
            if self.seed is not None:
                seed_offset = self.seed + i

            # First iteration is baseline if baseline=True (no failures)
            is_baseline = self.baseline and i == 0

            if is_baseline:
                # For baseline iteration, use empty exclusion sets
                excluded_nodes, excluded_links = set(), set()
            else:
                # Pre-compute exclusions for this iteration
                excluded_nodes, excluded_links = _compute_failure_exclusions(
                    network, policy, seed_offset
                )

            # Create worker arguments
            worker_args.append(
                (
                    excluded_nodes,  # Small set, cheap to pickle
                    excluded_links,  # Small set, cheap to pickle
                    self.source_path,
                    self.sink_path,
                    self.mode,
                    self.shortest_path,
                    self.flow_placement,
                    seed_offset,
                    self.name or self.__class__.__name__,
                    i,  # iteration index
                    is_baseline,  # baseline flag
                )
            )

        pre_compute_time = time.time() - pre_compute_start
        logger.debug(
            f"Pre-computed {len(worker_args)} exclusion sets in {pre_compute_time:.2f}s"
        )

        # Determine if we should run in parallel
        use_parallel = self.parallelism > 1 and mc_iters > 1

        if use_parallel:
            self._run_parallel(
                network,
                worker_args,
                mc_iters,
                samples,
                failure_patterns,
            )
        else:
            self._run_serial(network, worker_args, samples, failure_patterns)

        logger.debug(f"Collected samples for {len(samples)} flow pairs")
        return samples, failure_patterns

    def _run_parallel(
        self,
        network: "Network",
        worker_args: list[tuple],
        mc_iters: int,
        samples: dict[tuple[str, str], list[float]],
        failure_patterns: list[dict[str, Any]],
    ) -> None:
        """Run analysis in parallel using shared network approach.

        Network is serialized once in the main process and deserialized once per
        worker via the initializer, avoiding repeated serialization overhead.
        Each worker receives only small exclusion sets instead of modified network
        copies, reducing IPC overhead.

        Args:
            network: Network to analyze
            worker_args: Pre-computed worker arguments
            mc_iters: Number of iterations
            samples: Dictionary to accumulate flow results into
            failure_patterns: List to accumulate failure patterns into
        """
        workers = min(self.parallelism, mc_iters)
        logger.info(
            f"Running parallel analysis with {workers} workers for {mc_iters} iterations"
        )

        # Serialize network once for all workers
        network_pickle = pickle.dumps(network)
        logger.debug(f"Serialized network once: {len(network_pickle)} bytes")

        # Calculate optimal chunksize to minimize IPC overhead
        chunksize = max(1, mc_iters // (workers * 4))
        logger.debug(f"Using chunksize={chunksize} for parallel execution")

        start_time = time.time()
        completed_tasks = 0

        with ProcessPoolExecutor(
            max_workers=workers, initializer=_worker_init, initargs=(network_pickle,)
        ) as pool:
            logger.debug(
                f"ProcessPoolExecutor created with {workers} workers and shared network"
            )
            logger.info(f"Starting parallel execution of {mc_iters} iterations")

            try:
                for (
                    flow_results,
                    iteration_index,
                    is_baseline,
                    excluded_nodes,
                    excluded_links,
                ) in pool.map(_worker, worker_args, chunksize=chunksize):
                    completed_tasks += 1

                    # Add flow results to samples
                    result_count = len(flow_results)
                    for src, dst, val in flow_results:
                        samples[(src, dst)].append(val)

                    # Add failure pattern if requested
                    if self.store_failure_patterns:
                        failure_patterns.append(
                            {
                                "iteration_index": iteration_index,
                                "is_baseline": is_baseline,
                                "excluded_nodes": list(excluded_nodes),
                                "excluded_links": list(excluded_links),
                            }
                        )

                    # Progress logging
                    if completed_tasks % max(1, mc_iters // 10) == 0:
                        logger.info(
                            f"Parallel analysis progress: {completed_tasks}/{mc_iters} tasks completed"
                        )
                        logger.debug(
                            f"Latest task produced {result_count} flow results"
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

        # Log exclusion pattern diversity
        unique_exclusions = set()
        for args in worker_args:
            excluded_nodes, excluded_links = args[0], args[1]
            exclusion_key = (
                tuple(sorted(excluded_nodes)),
                tuple(sorted(excluded_links)),
            )
            unique_exclusions.add(exclusion_key)

        logger.info(
            f"Generated {len(unique_exclusions)} unique exclusion patterns from {mc_iters} iterations"
        )
        cache_efficiency = (mc_iters - len(unique_exclusions)) / mc_iters * 100
        logger.debug(
            f"Potential cache efficiency: {cache_efficiency:.1f}% (worker processes benefit from caching)"
        )

    def _run_serial(
        self,
        network: "Network",
        worker_args: list[tuple],
        samples: dict[tuple[str, str], list[float]],
        failure_patterns: list[dict[str, Any]],
    ) -> None:
        """Run analysis serially for single process execution.

        Args:
            network: Network to analyze
            worker_args: Pre-computed worker arguments
            samples: Dictionary to accumulate flow results into
            failure_patterns: List to accumulate failure patterns into
        """
        logger.info("Running serial analysis")
        start_time = time.time()

        # For serial execution, we need to initialize the global network
        global _shared_network
        _shared_network = network

        try:
            for i, args in enumerate(worker_args):
                iter_start = time.time()

                is_baseline = self.baseline and i == 0
                baseline_msg = " (baseline)" if is_baseline else ""
                logger.debug(
                    f"Serial iteration {i + 1}/{len(worker_args)}{baseline_msg}"
                )

                (
                    flow_results,
                    iteration_index,
                    is_baseline,
                    excluded_nodes,
                    excluded_links,
                ) = _worker(args)

                # Add flow results to samples
                for src, dst, val in flow_results:
                    samples[(src, dst)].append(val)

                # Add failure pattern if requested
                if self.store_failure_patterns:
                    failure_patterns.append(
                        {
                            "iteration_index": iteration_index,
                            "is_baseline": is_baseline,
                            "excluded_nodes": list(excluded_nodes),
                            "excluded_links": list(excluded_links),
                        }
                    )

                iter_time = time.time() - iter_start
                if len(worker_args) <= 10:
                    logger.debug(
                        f"Serial iteration {i + 1} completed in {iter_time:.3f} seconds"
                    )

                if (
                    len(worker_args) > 1
                    and (i + 1) % max(1, len(worker_args) // 10) == 0
                ):
                    logger.info(
                        f"Serial analysis progress: {i + 1}/{len(worker_args)} iterations completed"
                    )
        finally:
            # Clean up global network reference
            _shared_network = None

        elapsed_time = time.time() - start_time
        logger.info(f"Serial analysis completed in {elapsed_time:.2f} seconds")
        if len(worker_args) > 1:
            logger.debug(
                f"Average time per iteration: {elapsed_time / len(worker_args):.3f} seconds"
            )
        logger.info(
            f"Flow cache contains {len(_flow_cache)} unique patterns after serial analysis"
        )

    def _parse_flow_key(self, flow_key: str) -> tuple[str, str]:
        """Parse flow key back to (source, sink) tuple."""
        parts = flow_key.split("->", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid flow key format: {flow_key}")
        return parts[0], parts[1]

    def _build_capacity_envelopes(
        self, samples: dict[tuple[str, str], list[float]]
    ) -> dict[str, dict[str, Any]]:
        """Build CapacityEnvelope objects from collected samples.

        Args:
            samples: Dictionary mapping (src_label, dst_label) to capacity values.

        Returns:
            Dictionary mapping flow keys to serialized CapacityEnvelope data.
        """
        start_time = time.time()
        total_samples = sum(len(values) for values in samples.values())
        logger.info(
            f"Building capacity envelopes from {len(samples)} flow pairs with {total_samples:,} total samples"
        )

        envelopes = {}
        processed_flows = 0

        for (src_label, dst_label), capacity_values in samples.items():
            if not capacity_values:
                logger.warning(
                    f"No capacity values found for flow {src_label}->{dst_label}"
                )
                continue

            # Use flow key as the result key
            flow_key = f"{src_label}->{dst_label}"

            # Create frequency-based envelope
            envelope = CapacityEnvelope.from_values(
                source_pattern=self.source_path,
                sink_pattern=self.sink_path,
                mode=self.mode,
                values=capacity_values,
            )
            envelopes[flow_key] = envelope.to_dict()

            processed_flows += 1

            # Detailed logging with statistics
            logger.debug(
                f"Created frequency-based envelope for {flow_key}: {envelope.total_samples} samples, "
                f"min={envelope.min_capacity:.2f}, max={envelope.max_capacity:.2f}, "
                f"mean={envelope.mean_capacity:.2f}, unique_values={len(envelope.frequencies)}"
            )

            # Progress logging for large numbers of flows
            if len(samples) > 100 and processed_flows % max(1, len(samples) // 10) == 0:
                elapsed = time.time() - start_time
                logger.info(
                    f"Envelope building progress: {processed_flows}/{len(samples)} flows processed in {elapsed:.1f}s"
                )

        elapsed_time = time.time() - start_time
        logger.info(
            f"Generated {len(envelopes)} capacity envelopes in {elapsed_time:.2f} seconds"
        )
        return envelopes


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("CapacityEnvelopeAnalysis")(CapacityEnvelopeAnalysis)
