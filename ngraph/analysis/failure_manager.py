"""FailureManager for Monte Carlo failure analysis.

Provides the failure analysis engine for NetGraph. Supports parallel
processing, graph caching, and failure policy handling for workflow steps
and direct programmatic use.

Performance characteristics:
Time complexity: O(S + I * A / P), where S is one-time graph setup cost,
I is iteration count, A is per-iteration analysis cost, and P is parallelism.
Graph caching amortizes expensive graph construction across all iterations,
and O(|excluded|) mask building replaces O(V+E) iteration.

Space complexity: O(V + E + I * R), where V and E are node and link counts,
and R is result size per iteration. The pre-built graph is shared across
all iterations.

Parallelism: The C++ Core backend releases the GIL during computation,
enabling true parallelism with Python threads. With graph caching, most
per-iteration work runs in GIL-free C++ code; speedup depends on workload
and parallelism level.
"""

from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, Set, TypeVar

from ngraph.dsl.selectors import flatten_link_attrs, flatten_node_attrs
from ngraph.logging import get_logger
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.types.base import FlowPlacement

if TYPE_CHECKING:
    import cProfile

    from ngraph.model.network import Network

from ngraph.model.failure.policy import FailurePolicy

logger = get_logger(__name__)


def _is_hashable(obj: Any) -> bool:
    """Return True if obj is hashable, False otherwise.

    This avoids try/except TypeError patterns when checking hashability.
    """
    try:
        hash(obj)
        return True
    except TypeError:
        return False


def _create_cache_key(
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    analysis_name: str,
    analysis_kwargs: Dict[str, Any],
) -> tuple:
    """Create cache key from exclusions, analysis name, and parameters.

    Args:
        excluded_nodes: Set of excluded node names.
        excluded_links: Set of excluded link IDs.
        analysis_name: Name of the analysis function.
        analysis_kwargs: Analysis function arguments.

    Returns:
        Tuple suitable for use as a cache key.
    """
    # Basic components that are always hashable
    base_key = (
        tuple(sorted(excluded_nodes)),
        tuple(sorted(excluded_links)),
        analysis_name,
    )

    # Normalize analysis_kwargs for hashing
    hashable_kwargs = []
    for key, value in sorted(analysis_kwargs.items()):
        # Try to hash the (key, value) pair directly
        if _is_hashable((key, value)):
            hashable_kwargs.append((key, value))
        else:
            # Use object id for non-hashable values. Avoid str() which triggers
            # deep __repr__ traversals on large objects (e.g., graphs with thousands
            # of edges). id() works here because these objects persist across calls.
            hashable_kwargs.append((key, f"{type(value).__name__}_{id(value)}"))

    return base_key + (tuple(hashable_kwargs),)


def _auto_adjust_parallelism(parallelism: int, analysis_func: Any) -> int:
    """Adjust parallelism based on function characteristics.

    Args:
        parallelism: Requested parallelism level.
        analysis_func: Analysis function to check.

    Returns:
        Adjusted parallelism level.
    """
    # Check if function is defined in __main__ (notebook context)
    if hasattr(analysis_func, "__module__") and analysis_func.__module__ == "__main__":
        if parallelism > 1:
            logger.warning(
                "Function defined in notebook/script (__main__) detected. "
                "Forcing serial execution (parallelism=1) to avoid pickling issues. "
                "Consider moving analysis function to a separate module for parallel execution."
            )
        return 1

    return parallelism


T = TypeVar("T")


class AnalysisFunction(Protocol):
    """Protocol for analysis functions used with FailureManager.

    Analysis functions should take a Network, exclusion sets, and any additional
    keyword arguments, returning analysis results of any type.
    """

    def __call__(
        self,
        network: "Network",
        excluded_nodes: Set[str],
        excluded_links: Set[str],
        **kwargs,
    ) -> Any:
        """Execute analysis on network with exclusions and optional parameters."""
        ...


def _generic_worker(args: tuple[Any, ...]) -> tuple[Any, int, bool, set[str], set[str]]:
    """Execute analysis function with caching.

    Caches analysis results based on exclusion patterns and analysis parameters
    since many Monte Carlo iterations share the same exclusion sets.
    Analysis computation is deterministic for identical inputs, making caching safe.

    Args:
        args: Tuple containing (network, excluded_nodes, excluded_links, analysis_func,
              analysis_kwargs, iteration_index, is_baseline, analysis_name).

    Returns:
        Tuple of (analysis_result, iteration_index, is_baseline,
                 excluded_nodes, excluded_links).
    """
    worker_logger = get_logger(f"{__name__}.worker")

    (
        network,
        excluded_nodes,
        excluded_links,
        analysis_func,
        analysis_kwargs,
        iteration_index,
        is_baseline,
        analysis_name,
    ) = args

    # Optional per-worker profiling for performance analysis
    profile_dir_env = os.getenv("NGRAPH_PROFILE_DIR")
    collect_profile: bool = bool(profile_dir_env)

    profiler: "cProfile.Profile | None" = None
    if collect_profile:
        # Install per-worker profiler when requested
        import cProfile

        profiler = cProfile.Profile()
        try:
            profiler.enable()
        except ValueError:
            # Another profiler is already active (e.g., pytest-cov in threading mode)
            profiler = None
            collect_profile = False

    import threading

    worker_id = threading.current_thread().name
    worker_logger.debug(
        f"Worker {worker_id} starting: iteration={iteration_index}, "
        f"excluded_nodes={len(excluded_nodes)}, excluded_links={len(excluded_links)}"
    )

    # Execute analysis function with network and exclusion sets
    worker_logger.debug(f"Worker {worker_id} executing {analysis_name}")
    result = analysis_func(network, excluded_nodes, excluded_links, **analysis_kwargs)
    worker_logger.debug(f"Worker {worker_id} completed analysis")

    # Dump profile if enabled (for performance analysis)
    if profiler is not None:
        profiler.disable()
        import pstats
        import threading
        import uuid
        from pathlib import Path

        profile_dir = Path(profile_dir_env) if profile_dir_env else None
        if profile_dir is not None:
            profile_dir.mkdir(parents=True, exist_ok=True)
            unique_id = uuid.uuid4().hex[:8]
            thread_id = threading.current_thread().ident
            profile_path = (
                profile_dir / f"{analysis_name}_thread_{thread_id}_{unique_id}.pstats"
            )
            pstats.Stats(profiler).dump_stats(profile_path)
            worker_logger.debug("Saved worker profile to %s", profile_path.name)

    return (result, iteration_index, is_baseline, excluded_nodes, excluded_links)


class FailureManager:
    """Failure analysis engine with Monte Carlo capabilities.

    This is the component for failure analysis in NetGraph.
    Provides parallel processing, worker caching, and failure
    policy handling for workflow steps and direct notebook usage.

    The FailureManager can execute any analysis function that takes a Network
    with exclusion sets and returns results, making it generic for different
    types of failure analysis (capacity, traffic, connectivity, etc.).

    Attributes:
        network: The underlying network (not modified during analysis).
        failure_policy_set: Set of named failure policies.
        policy_name: Name of specific failure policy to use.
    """

    def __init__(
        self,
        network: "Network",
        failure_policy_set: FailurePolicySet,
        policy_name: str | None = None,
    ) -> None:
        """Initialize FailureManager.

        Args:
            network: Network to analyze (read-only, not modified).
            failure_policy_set: Set of named failure policies.
            policy_name: Name of specific policy to use. If None, no failure policy is applied.
        """
        self.network = network
        self.failure_policy_set = failure_policy_set
        self.policy_name = policy_name
        self._merged_node_attrs: dict[str, dict[str, Any]] | None = None
        self._merged_link_attrs: dict[str, dict[str, Any]] | None = None

    def get_failure_policy(self) -> "FailurePolicy | None":
        """Get failure policy for analysis.

        Returns:
            FailurePolicy instance or None if no policy should be applied.

        Raises:
            ValueError: If named policy is not found in failure_policy_set.
        """
        if self.policy_name is not None:
            try:
                return self.failure_policy_set.get_policy(self.policy_name)
            except KeyError as exc:
                raise ValueError(
                    f"Failure policy '{self.policy_name}' not found in scenario"
                ) from exc
        else:
            return None

    def compute_exclusions(
        self,
        policy: "FailurePolicy | None" = None,
        seed_offset: int | None = None,
        failure_trace: Optional[Dict[str, Any]] = None,
    ) -> tuple[set[str], set[str]]:
        """Compute set of nodes and links to exclude for a failure iteration.

        Applies failure policy logic and returns exclusion sets. This is
        equivalent to applying failures to the network and then filtering, but
        with lower overhead since exclusion sets are typically small.

        Args:
            policy: Failure policy to apply. If None, uses instance policy.
            seed_offset: Optional seed for deterministic failures.
            failure_trace: Optional dict to populate with trace data from policy.

        Returns:
            Tuple of (excluded_nodes, excluded_links) containing entity IDs to exclude.
        """
        if policy is None:
            policy = self.get_failure_policy()

        excluded_nodes = set()
        excluded_links = set()

        if policy is None:
            return excluded_nodes, excluded_links

        # Build merged views of nodes and links including top-level fields required by
        # policy matching and risk-group expansion. Results are cached for reuse.
        if self._merged_node_attrs is None:
            self._merged_node_attrs = {
                node_name: flatten_node_attrs(node)
                for node_name, node in self.network.nodes.items()
            }
        if self._merged_link_attrs is None:
            self._merged_link_attrs = {
                link_id: flatten_link_attrs(link, link_id)
                for link_id, link in self.network.links.items()
            }

        node_map = self._merged_node_attrs
        link_map = self._merged_link_attrs

        # Apply failure policy with optional deterministic seed override
        failed_ids = policy.apply_failures(
            node_map,
            link_map,
            self.network.risk_groups,
            seed=seed_offset,
            failure_trace=failure_trace,
        )

        # Separate entity types for exclusion sets
        for f_id in failed_ids:
            if f_id in self.network.nodes:
                excluded_nodes.add(f_id)
            elif f_id in self.network.links:
                excluded_links.add(f_id)
            elif f_id in self.network.risk_groups:
                # Recursively expand risk groups
                risk_group = self.network.risk_groups[f_id]
                to_check = [risk_group]
                while to_check:
                    grp = to_check.pop()
                    # Add all nodes/links in this risk group
                    for node_name, node in self.network.nodes.items():
                        if grp.name in node.risk_groups:
                            excluded_nodes.add(node_name)
                    for link_id, link in self.network.links.items():
                        if grp.name in link.risk_groups:
                            excluded_links.add(link_id)
                    # Check children recursively
                    to_check.extend(grp.children)

        return excluded_nodes, excluded_links

    def run_monte_carlo_analysis(
        self,
        analysis_func: AnalysisFunction,
        iterations: int = 1,
        parallelism: int = 1,
        seed: int | None = None,
        store_failure_patterns: bool = False,
        **analysis_kwargs,
    ) -> dict[str, Any]:
        """Run Monte Carlo failure analysis with any analysis function.

        This is the main method for executing failure analysis. Handles
        parallel processing, worker caching, and failure policy
        application, while allowing flexibility in the analysis function.

        Baseline is always run first as a separate reference iteration (no failures).
        The ``iterations`` parameter specifies the number of failure iterations to run.

        Args:
            analysis_func: Function that takes (network, excluded_nodes, excluded_links, **kwargs)
                          and returns results. Must be serializable for parallel execution.
            iterations: Number of failure iterations to run (baseline is always run separately).
            parallelism: Number of parallel worker threads to use.
            seed: Optional seed for reproducible results across runs.
            store_failure_patterns: If True, populate failure_trace on each result.
            **analysis_kwargs: Additional arguments passed to analysis_func.

        Returns:
            Dictionary containing:
            - 'baseline': FlowIterationResult for the baseline (no failures)
            - 'results': List of unique FlowIterationResult objects (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        policy = self.get_failure_policy()

        # Check if policy has effective rules
        has_effective_rules = bool(
            policy and any(len(m.rules) > 0 for m in policy.modes)
        )

        # Without effective rules, only baseline makes sense (no failure iterations)
        if not has_effective_rules:
            iterations = 0

        # Auto-adjust parallelism based on function characteristics
        parallelism = _auto_adjust_parallelism(parallelism, analysis_func)

        logger.info(
            f"Running baseline + {iterations} failure iterations"
            if iterations > 0
            else "Running baseline only (no failure policy)"
        )

        # Pre-build context for analysis functions
        # This amortizes expensive graph construction across all iterations
        if "context" not in analysis_kwargs:
            analysis_kwargs = dict(analysis_kwargs)  # Don't mutate caller's dict
            cache_start = time.time()

            if "demands_config" in analysis_kwargs:
                # Demand placement analysis
                from ngraph.analysis.functions import build_demand_context

                logger.debug("Pre-building context for demand placement analysis")
                analysis_kwargs["context"] = build_demand_context(
                    self.network, analysis_kwargs["demands_config"]
                )
                logger.debug(f"Context built in {time.time() - cache_start:.3f}s")

            elif "source" in analysis_kwargs and "sink" in analysis_kwargs:
                # Max-flow analysis or sensitivity analysis
                from ngraph.analysis.functions import build_maxflow_context

                logger.debug("Pre-building context for max-flow analysis")
                analysis_kwargs["context"] = build_maxflow_context(
                    self.network,
                    analysis_kwargs["source"],
                    analysis_kwargs["sink"],
                    mode=analysis_kwargs.get("mode", "combine"),
                )
                logger.debug(f"Context built in {time.time() - cache_start:.3f}s")

        # Get function name safely (Protocol doesn't guarantee __name__)
        func_name = getattr(analysis_func, "__name__", "analysis_function")
        logger.debug(
            f"Analysis parameters: function={func_name}, "
            f"parallelism={parallelism}, policy={self.policy_name}"
        )

        # Pre-compute worker arguments for all iterations
        logger.debug("Pre-computing failure exclusions for all iterations")
        pre_compute_start = time.time()

        # Baseline is always run first (no failures, separate from failure iterations)
        baseline_arg = (
            self.network,
            set(),  # No excluded nodes
            set(),  # No excluded links
            analysis_func,
            analysis_kwargs,
            -1,  # Special index for baseline
            True,  # is_baseline
            func_name,
        )

        # Build failure iteration arguments (indexed 0..iterations-1)
        worker_args: list[tuple] = []
        key_to_first_arg: dict[tuple, tuple] = {}
        key_to_count: dict[tuple, int] = {}
        key_to_trace: dict[tuple, dict[str, Any]] = {}

        for i in range(iterations):
            seed_offset = seed + i if seed is not None else None

            # Pre-compute exclusions for this failure iteration
            trace = {} if store_failure_patterns else None
            excluded_nodes, excluded_links = self.compute_exclusions(
                policy, seed_offset, failure_trace=trace
            )

            arg = (
                self.network,
                excluded_nodes,
                excluded_links,
                analysis_func,
                analysis_kwargs,
                i,  # iteration_index (0-based for failures)
                False,  # is_baseline
                func_name,
            )
            worker_args.append(arg)

            # Build deduplication key (excludes iteration index)
            dedup_key = _create_cache_key(
                excluded_nodes, excluded_links, func_name, analysis_kwargs
            )
            if dedup_key not in key_to_first_arg:
                key_to_first_arg[dedup_key] = arg
                key_to_count[dedup_key] = 1
                # Store trace for first occurrence
                if trace is not None:
                    key_to_trace[dedup_key] = trace
            else:
                key_to_count[dedup_key] += 1

        pre_compute_time = time.time() - pre_compute_start
        logger.debug(
            f"Pre-computed {len(worker_args)} failure exclusion sets in {pre_compute_time:.2f}s"
        )

        # Prepare unique tasks (deduplicated by failure pattern + analysis params)
        unique_worker_args: list[tuple] = list(key_to_first_arg.values())
        num_unique_tasks: int = len(unique_worker_args)
        if iterations > 0:
            logger.info(
                f"Monte-Carlo deduplication: {num_unique_tasks} unique patterns from {iterations} failure iterations"
            )

        start_time = time.time()

        # Always run baseline first (separate from failure iterations)
        baseline_result_raw = self._run_serial([baseline_arg])
        baseline_result = baseline_result_raw[0] if baseline_result_raw else None

        # Enrich baseline result with failure metadata
        if baseline_result is not None and hasattr(baseline_result, "failure_id"):
            baseline_result.failure_id = ""
            baseline_result.failure_state = {"excluded_nodes": [], "excluded_links": []}
            baseline_result.failure_trace = None  # No policy applied for baseline

        # Execute failure iterations (deduplicated)
        if iterations > 0:
            use_parallel = parallelism > 1 and num_unique_tasks > 1
            if use_parallel:
                unique_result_values = self._run_parallel(
                    unique_worker_args, num_unique_tasks, parallelism
                )
            else:
                unique_result_values = self._run_serial(unique_worker_args)

            # Map unique task results back to their dedup keys
            key_to_result: dict[tuple, Any] = {}
            for (dedup_key, _arg), value in zip(
                key_to_first_arg.items(), unique_result_values, strict=False
            ):
                key_to_result[dedup_key] = value
        else:
            key_to_result = {}

        elapsed_time = time.time() - start_time

        # Enrich unique failure results with metadata and occurrence_count
        results: list[Any] = []
        for dedup_key, rep_arg in key_to_first_arg.items():
            result = key_to_result.get(dedup_key)
            if result is None:
                continue

            exc_nodes: set[str] = rep_arg[1]
            exc_links: set[str] = rep_arg[2]

            # Compute failure_id (hash of exclusions, or "" for empty)
            if not exc_nodes and not exc_links:
                fid = ""
            else:
                payload = (
                    ",".join(sorted(exc_nodes)) + "|" + ",".join(sorted(exc_links))
                )
                fid = hashlib.blake2s(
                    payload.encode("utf-8"), digest_size=8
                ).hexdigest()

            # Enrich FlowIterationResult-like objects
            if hasattr(result, "failure_id") and hasattr(result, "summary"):
                result.failure_id = fid
                result.failure_state = {
                    "excluded_nodes": list(exc_nodes),
                    "excluded_links": list(exc_links),
                }
                result.failure_trace = (
                    key_to_trace.get(dedup_key) if store_failure_patterns else None
                )
                result.occurrence_count = key_to_count[dedup_key]

            results.append(result)

        return {
            "baseline": baseline_result,
            "results": results,
            "metadata": {
                "iterations": iterations,
                "parallelism": parallelism,
                "analysis_function": func_name,
                "policy_name": self.policy_name,
                "execution_time": elapsed_time,
                "unique_patterns": num_unique_tasks,
            },
        }

    def _run_parallel(
        self,
        worker_args: list[tuple],
        total_tasks: int,
        parallelism: int,
    ) -> list[Any]:
        """Run analysis in parallel using shared network approach.

        Network is shared by reference across all threads (zero-copy), which is
        safe since the network is read-only during analysis. Each worker receives
        only small exclusion sets, and the C++ Core backend releases the GIL
        during computation to enable true parallelism.

        Args:
            worker_args: Pre-computed worker arguments for all iterations.
            total_tasks: Number of tasks to run.
            parallelism: Number of parallel worker threads to use.

        Returns:
            List of analysis results.
        """
        workers = min(parallelism, total_tasks)
        logger.info(
            f"Running parallel analysis with {workers} workers for {total_tasks} iterations"
        )

        # Network is shared by reference (zero-copy) across threads
        logger.debug(f"Sharing network by reference across {workers} threads")

        # Calculate optimal chunksize to minimize overhead
        chunksize = max(1, total_tasks // (workers * 4))
        logger.debug(f"Using chunksize={chunksize} for parallel execution")

        start_time = time.time()
        completed_tasks = 0
        results = []

        with ThreadPoolExecutor(
            max_workers=workers,
        ) as pool:
            logger.debug(
                f"ThreadPoolExecutor created with {workers} workers and shared network"
            )
            logger.info(f"Starting parallel execution of {total_tasks} iterations")

            for (
                result,
                _iteration_index,
                _is_baseline,
                _excluded_nodes,
                _excluded_links,
            ) in pool.map(_generic_worker, worker_args, chunksize=chunksize):
                completed_tasks += 1
                results.append(result)

                # Progress logging (throttle for small N at INFO)
                if total_tasks >= 20:
                    # Show approx 10% increments
                    step = max(1, total_tasks // 10)
                    if completed_tasks % step == 0:
                        logger.info(
                            f"Parallel analysis progress: {completed_tasks}/{total_tasks} tasks completed"
                        )

        elapsed_time = time.time() - start_time
        logger.info(f"Parallel analysis completed in {elapsed_time:.2f} seconds")
        logger.debug(
            f"Average time per iteration: {elapsed_time / total_tasks:.3f} seconds"
        )

        return results

    def _run_serial(
        self,
        worker_args: list[tuple],
    ) -> list[Any]:
        """Run analysis serially for single process execution.

        Args:
            worker_args: Pre-computed worker arguments for all iterations.

        Returns:
            List of analysis results.
        """
        logger.info("Running serial analysis")
        start_time = time.time()

        results = []

        # In serial mode, disable worker-level profiling in the current process
        # to avoid nesting profilers when the CLI has already enabled step-level
        # profiling. This prevents errors from profilers that require exclusivity.
        _restore_profile_env = False
        _saved_profile_dir = os.environ.get("NGRAPH_PROFILE_DIR")
        if _saved_profile_dir:
            # Temporarily remove the env var so _generic_worker skips profiling
            os.environ.pop("NGRAPH_PROFILE_DIR", None)
            _restore_profile_env = True
            logger.debug(
                "Temporarily disabled NGRAPH_PROFILE_DIR for serial execution to avoid nested profilers"
            )

        for i, args in enumerate(worker_args):
            iter_start = time.time()

            is_baseline_arg = len(args) > 6 and args[6]  # is_baseline flag
            baseline_msg = " (baseline)" if is_baseline_arg else ""
            logger.debug(f"Serial iteration {i + 1}/{len(worker_args)}{baseline_msg}")

            (
                result,
                _iteration_index,
                _is_baseline,
                _excluded_nodes,
                _excluded_links,
            ) = _generic_worker(args)

            results.append(result)

            iter_time = time.time() - iter_start
            if len(worker_args) <= 10:
                logger.debug(
                    f"Serial iteration {i + 1} completed in {iter_time:.3f} seconds"
                )

            if len(worker_args) > 1 and (i + 1) % max(1, len(worker_args) // 10) == 0:
                logger.info(
                    f"Serial analysis progress: {i + 1}/{len(worker_args)} iterations completed"
                )

        # Restore worker profiling env var if we changed it
        if _restore_profile_env:
            os.environ["NGRAPH_PROFILE_DIR"] = _saved_profile_dir or ""

        elapsed_time = time.time() - start_time
        logger.info(f"Serial analysis completed in {elapsed_time:.2f} seconds")
        if len(worker_args) > 1:
            logger.debug(
                f"Average time per iteration: {elapsed_time / len(worker_args):.3f} seconds"
            )

        return results

    def run_single_failure_scenario(
        self, analysis_func: AnalysisFunction, **kwargs
    ) -> Any:
        """Run a single failure scenario for convenience.

        This is a convenience method for running a single iteration, useful for
        quick analysis or debugging. For full Monte Carlo analysis, use
        run_monte_carlo_analysis().

        Args:
            analysis_func: Function that takes (network, excluded_nodes, excluded_links, **kwargs)
                          and returns results.
            **kwargs: Additional arguments passed to analysis_func.

        Returns:
            Result from the analysis function. Returns the first failure result if
            available, otherwise the baseline result.
        """
        result = self.run_monte_carlo_analysis(
            analysis_func=analysis_func, iterations=1, parallelism=1, **kwargs
        )
        # Return first failure result if available, otherwise baseline
        if result["results"]:
            return result["results"][0]
        return result["baseline"]

    # Convenience methods for common analysis patterns

    def run_max_flow_monte_carlo(
        self,
        source: str | dict[str, Any],
        sink: str | dict[str, Any],
        mode: str = "combine",
        iterations: int = 100,
        parallelism: int = 1,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL,
        seed: int | None = None,
        store_failure_patterns: bool = False,
        include_flow_summary: bool = False,
        **kwargs,
    ) -> Any:
        """Analyze maximum flow capacity envelopes between node groups under failures.

        Computes statistical distributions (envelopes) of maximum flow capacity between
        source and sink node groups across Monte Carlo failure scenarios. Results include
        frequency-based capacity envelopes and optional failure pattern analysis.

        Baseline (no failures) is always run first as a separate reference.

        Args:
            source: Source node selector (string path or selector dict).
            sink: Sink node selector (string path or selector dict).
            mode: "combine" (aggregate) or "pairwise" (individual flows).
            iterations: Number of failure scenarios to simulate.
            parallelism: Number of parallel workers (auto-adjusted if needed).
            shortest_path: Whether to use shortest paths only.
            require_capacity: If True (default), path selection considers available
                capacity. If False, path selection is cost-only (true IP/IGP semantics).
            flow_placement: Flow placement strategy.
            seed: Optional seed for reproducible results.
            store_failure_patterns: Whether to store failure trace on results.
            include_flow_summary: Whether to collect detailed flow summary data.

        Returns:
            Dictionary with keys:
            - 'baseline': FlowIterationResult for baseline (no failures)
            - 'results': List of unique FlowIterationResult objects (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        from ngraph.analysis.functions import max_flow_analysis

        # Convert string flow_placement to enum if needed
        if isinstance(flow_placement, str):
            flow_placement = FlowPlacement.from_string(flow_placement)

        # Run Monte Carlo analysis
        raw_results = self.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=iterations,
            parallelism=parallelism,
            seed=seed,
            store_failure_patterns=store_failure_patterns,
            source=source,
            sink=sink,
            mode=mode,
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            include_flow_details=include_flow_summary,
            **kwargs,
        )
        return raw_results

    def _process_sensitivity_results(
        self, results: list[Any]
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Process sensitivity results to aggregate component impact scores.

        Args:
            results: List of unique FlowIterationResult objects (deduplicated).
                Each result has occurrence_count indicating how many iterations
                produced that pattern.

        Returns:
            Dictionary mapping flow keys to component impact aggregations.
        """
        from collections import defaultdict

        from ngraph.results.flow import FlowIterationResult

        # Aggregate component scores weighted by occurrence_count
        # Store (weighted_sum, total_count, min, max) per component
        flow_aggregates: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(lambda: [0.0, 0, float("inf"), float("-inf")])
        )

        for result in results:
            if not isinstance(result, FlowIterationResult):
                continue
            count = getattr(result, "occurrence_count", 1)
            for entry in result.flows:
                flow_key = f"{entry.source}->{entry.destination}"
                sensitivity = entry.data.get("sensitivity", {})
                for component_key, score in sensitivity.items():
                    agg = flow_aggregates[flow_key][component_key]
                    agg[0] += score * count  # weighted sum
                    agg[1] += count  # total count
                    agg[2] = min(agg[2], score)  # min
                    agg[3] = max(agg[3], score)  # max

        # Calculate statistics for each component
        processed_scores: dict[str, dict[str, dict[str, float]]] = {}
        for flow_key, components in flow_aggregates.items():
            flow_stats: dict[str, dict[str, float]] = {}
            for component_key, agg in components.items():
                weighted_sum, total_count, min_val, max_val = agg
                if total_count > 0:
                    flow_stats[component_key] = {
                        "mean": weighted_sum / total_count,
                        "max": max_val,
                        "min": min_val,
                        "count": float(total_count),
                    }
            processed_scores[flow_key] = flow_stats

        logger.debug(
            f"Processed sensitivity scores for {len(processed_scores)} flow pairs"
        )
        return processed_scores

    def run_demand_placement_monte_carlo(
        self,
        demands_config: list[dict[str, Any]]
        | Any,  # List of demand configs or TrafficMatrixSet
        iterations: int = 100,
        parallelism: int = 1,
        placement_rounds: int | str = "auto",
        seed: int | None = None,
        store_failure_patterns: bool = False,
        include_flow_details: bool = False,
        include_used_edges: bool = False,
        **kwargs,
    ) -> Any:
        """Analyze traffic demand placement success under failures.

        Attempts to place traffic demands on the network across
        Monte Carlo failure scenarios and measures success rates.

        Baseline (no failures) is always run first as a separate reference.

        Args:
            demands_config: List of demand configs or TrafficMatrixSet object.
            iterations: Number of failure scenarios to simulate.
            parallelism: Number of parallel workers (auto-adjusted if needed).
            placement_rounds: Optimization rounds for demand placement.
            seed: Optional seed for reproducible results.
            store_failure_patterns: Whether to store failure trace on results.

        Returns:
            Dictionary with keys:
            - 'baseline': FlowIterationResult for baseline (no failures)
            - 'results': List of unique FlowIterationResult objects (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        from ngraph.analysis.functions import demand_placement_analysis

        # If caller passed a sequence of TrafficDemand objects, convert to dicts
        if not isinstance(demands_config, list):
            # Accept TrafficMatrixSet or any container providing get_matrix()/matrices
            serializable_demands: list[dict[str, Any]] = []
            if hasattr(demands_config, "get_all_demands"):
                td_iter = demands_config.get_all_demands()  # TrafficMatrixSet helper
            elif hasattr(demands_config, "demands"):
                # Accept a mock object exposing 'demands' for tests
                td_iter = demands_config.demands
            else:
                td_iter = []
            for demand in td_iter:  # type: ignore[assignment]
                serializable_demands.append(
                    {
                        "id": getattr(demand, "id", None),
                        "source": getattr(demand, "source", ""),
                        "sink": getattr(demand, "sink", ""),
                        "demand": float(getattr(demand, "demand", 0.0)),
                        "mode": getattr(demand, "mode", "pairwise"),
                        "group_mode": getattr(demand, "group_mode", "flatten"),
                        "expand_vars": getattr(demand, "expand_vars", {}),
                        "expansion_mode": getattr(
                            demand, "expansion_mode", "cartesian"
                        ),
                        "flow_policy_config": getattr(
                            demand, "flow_policy_config", None
                        ),
                        "priority": int(getattr(demand, "priority", 0)),
                    }
                )
            demands_config = serializable_demands

        raw_results = self.run_monte_carlo_analysis(
            analysis_func=demand_placement_analysis,
            iterations=iterations,
            parallelism=parallelism,
            seed=seed,
            store_failure_patterns=store_failure_patterns,
            demands_config=demands_config,
            placement_rounds=placement_rounds,
            include_flow_details=include_flow_details,
            include_used_edges=include_used_edges,
            **kwargs,
        )
        return raw_results

    def run_sensitivity_monte_carlo(
        self,
        source: str | dict[str, Any],
        sink: str | dict[str, Any],
        mode: str = "combine",
        iterations: int = 100,
        parallelism: int = 1,
        shortest_path: bool = False,
        flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL,
        seed: int | None = None,
        store_failure_patterns: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """Analyze component criticality for flow capacity under failures.

        Identifies critical network components by measuring their impact on flow
        capacity across Monte Carlo failure scenarios. Returns aggregated sensitivity
        scores showing which components have the greatest effect on network capacity.

        Baseline (no failures) is always run first as a separate reference.

        Args:
            source: Source node selector (string path or selector dict).
            sink: Sink node selector (string path or selector dict).
            mode: "combine" (aggregate) or "pairwise" (individual flows).
            iterations: Number of failure scenarios to simulate.
            parallelism: Number of parallel workers (auto-adjusted if needed).
            shortest_path: Whether to use shortest paths only.
            flow_placement: Flow placement strategy.
            seed: Optional seed for reproducible results.
            store_failure_patterns: Whether to store failure trace on results.

        Returns:
            Dictionary with keys:
            - 'baseline': Baseline result (no failures)
            - 'results': List of unique per-iteration sensitivity dicts (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'component_scores': aggregated statistics (mean, max, min, count) per component per flow
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        from ngraph.analysis.functions import sensitivity_analysis

        # Convert string flow_placement to enum if needed
        if isinstance(flow_placement, str):
            flow_placement = FlowPlacement.from_string(flow_placement)

        raw_results = self.run_monte_carlo_analysis(
            analysis_func=sensitivity_analysis,
            iterations=iterations,
            parallelism=parallelism,
            seed=seed,
            store_failure_patterns=store_failure_patterns,
            source=source,
            sink=sink,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
            **kwargs,
        )

        # Aggregate component scores across iterations for statistical analysis
        raw_results["component_scores"] = self._process_sensitivity_results(
            raw_results["results"]
        )

        # Augment metadata with analysis-specific context
        raw_results["metadata"]["source"] = source
        raw_results["metadata"]["sink"] = sink
        raw_results["metadata"]["mode"] = mode

        return raw_results
