"""FailureManager for Monte Carlo failure analysis.

Runs an analysis function over many failure scenarios, handling failure policy
application, graph caching, and parallel execution. Used by workflow steps and
directly from user code.

Performance characteristics:
Time complexity: O(S + I * A / P), where S is one-time graph setup cost,
I is iteration count, A is per-iteration analysis cost, and P is parallelism.
Graph caching amortizes graph construction across all iterations: each
iteration applies its exclusions as an O(|excluded|) mask update instead of
rebuilding the graph or re-scanning all O(V+E) nodes and edges.

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
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, Set

from ngraph.logging import get_logger
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.selectors import (
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
)
from ngraph.types.base import FlowPlacement

if TYPE_CHECKING:
    import cProfile

    from ngraph.model.network import Network, RiskGroup

from ngraph.analysis.functions import (
    demand_placement_analysis,
    max_flow_analysis,
    sensitivity_analysis,
)
from ngraph.model.failure.policy import FailurePolicy

logger = get_logger(__name__)


def _is_hashable(obj: Any) -> bool:
    """Return True if obj is hashable, False otherwise."""
    try:
        hash(obj)
        return True
    except TypeError:
        return False


def _hashable_kwargs_key(analysis_kwargs: Dict[str, Any]) -> tuple:
    """Build the hashable, order-independent kwargs component of a dedup key.

    This part of the key is invariant across Monte Carlo iterations, so
    callers should compute it once and combine it with the per-iteration
    exclusion sets via `_create_dedup_key`.
    """
    hashable_kwargs = []
    for key, value in sorted(analysis_kwargs.items()):
        if _is_hashable((key, value)):
            hashable_kwargs.append((key, value))
        else:
            # Use object id for non-hashable values. Avoid str() which triggers
            # deep __repr__ traversals on large objects (e.g., graphs with
            # thousands of edges). id() is safe here because these objects
            # persist across calls within one FailureManager lifetime.
            hashable_kwargs.append((key, f"{type(value).__name__}_{id(value)}"))
    return tuple(hashable_kwargs)


def _create_dedup_key(
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    analysis_name: str,
    kwargs_key: tuple,
) -> tuple:
    """Create deduplication key from exclusions, analysis name, and parameters.

    The key identifies identical failure patterns before dispatch: iterations
    sharing a key are executed once and fanned back out via occurrence_count.
    This is pre-dispatch deduplication, not a result cache.

    Args:
        excluded_nodes: Set of excluded node names.
        excluded_links: Set of excluded link IDs.
        analysis_name: Name of the analysis function.
        kwargs_key: Precomputed `_hashable_kwargs_key(analysis_kwargs)`.

    Returns:
        Tuple suitable for use as a deduplication key.
    """
    return (
        tuple(sorted(excluded_nodes)),
        tuple(sorted(excluded_links)),
        analysis_name,
        kwargs_key,
    )


class AnalysisFunction(Protocol):
    """Protocol for analysis functions used with FailureManager.

    Analysis functions take a Network, exclusion sets, and analysis-specific
    parameters, returning results of any type.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute analysis on network with exclusions and parameters."""
        ...


def _generic_worker(args: tuple[Any, ...]) -> Any:
    """Execute the analysis function once for one exclusion pattern.

    Unpacks the args tuple, optionally enables per-worker cProfile when
    NGRAPH_PROFILE_DIR is set, and calls
    analysis_func(network, excluded_nodes, excluded_links, **analysis_kwargs).
    Duplicate exclusion patterns are deduplicated upstream in
    run_monte_carlo_analysis, so each worker invocation is unique work.

    Args:
        args: Tuple containing (network, excluded_nodes, excluded_links, analysis_func,
              analysis_kwargs, iteration_index, is_baseline, analysis_name).

    Returns:
        The analysis function's result.
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

    worker_logger.debug(f"Worker {worker_id} executing {analysis_name}")
    result = analysis_func(network, excluded_nodes, excluded_links, **analysis_kwargs)
    worker_logger.debug(f"Worker {worker_id} completed analysis")

    # Dump profile if enabled (for performance analysis)
    if profiler is not None:
        profiler.disable()
        import pstats
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

    return result


class FailureManager:
    """Run an analysis function across Monte Carlo failure scenarios.

    Applies a failure policy, deduplicates identical failure patterns, and
    runs iterations in parallel. Used by workflow steps and directly from user code.

    Executes any analysis function that takes a Network plus exclusion sets and
    returns results, so the same engine covers capacity, traffic, connectivity,
    and custom analyses.

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
        self._merged_rg_attrs: dict[str, dict[str, Any]] | None = None
        # Keyed by id(policy); each entry pins the policy object so a freed
        # policy's address cannot be reused and silently match a stale entry.
        self._prepared_policy_matches: dict[
            int, tuple[FailurePolicy, dict[int, tuple[str, ...]]]
        ] = {}
        self._prepared_policy_weights: dict[
            int,
            tuple[
                FailurePolicy,
                dict[int, tuple[dict[str, float], tuple[str, ...]]],
            ],
        ] = {}
        self._risk_group_exclusions: (
            dict[str, tuple[frozenset[str], frozenset[str]]] | None
        ) = None
        # Risk-group -> entity-ID index used by policies with
        # expand_groups=True. Depends only on the static network, so it is
        # built once per manager and shared across policies and iterations.
        self._prepared_rg_index: dict[str, set[str]] | None = None

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

    def _ensure_flattened_maps(self) -> None:
        """Build flattened attribute views for all entity types (once).

        Merges top-level model fields (name, disabled, etc.) with .attrs
        so that condition matching in apply_failures works uniformly.
        All three maps are built together to prevent partial initialization.
        """
        if self._merged_node_attrs is not None:
            return
        self._merged_node_attrs = {
            name: flatten_node_attrs(node) for name, node in self.network.nodes.items()
        }
        self._merged_link_attrs = {
            lid: flatten_link_attrs(link, lid)
            for lid, link in self.network.links.items()
        }
        self._merged_rg_attrs = {
            name: flatten_risk_group_attrs(rg)
            for name, rg in self.network.risk_groups.items()
        }

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

        self._ensure_flattened_maps()
        assert (
            self._merged_node_attrs is not None
        )  # guaranteed by _ensure_flattened_maps
        assert self._merged_link_attrs is not None
        assert self._merged_rg_attrs is not None
        node_map = self._merged_node_attrs
        link_map = self._merged_link_attrs
        rg_map = self._merged_rg_attrs
        prepared_matches = self._get_prepared_policy_matches(
            policy, node_map, link_map, rg_map
        )
        prepared_weights = self._get_prepared_policy_weights(
            policy, prepared_matches, node_map, link_map, rg_map
        )
        # getattr: compute_exclusions accepts duck-typed policy objects that
        # may not declare expand_groups.
        wants_expansion = getattr(policy, "expand_groups", False)
        prepared_rg_index = self._get_prepared_rg_index() if wants_expansion else None
        if wants_expansion:
            if self._risk_group_exclusions is None:
                self._risk_group_exclusions = self._build_risk_group_exclusions()
            prepared_rg_members = self._risk_group_exclusions
        else:
            prepared_rg_members = None

        # Apply failure policy with optional deterministic seed override.
        # The typed variant keeps entity kinds separate: probing merged IDs
        # against network collections misclassifies a risk group that shares
        # its name with a node or link.
        failed_nodes, failed_links, failed_rgs = policy.apply_failures_typed(
            node_map,
            link_map,
            rg_map,
            seed=seed_offset,
            failure_trace=failure_trace,
            prepared_matches=prepared_matches,
            prepared_weights=prepared_weights,
            prepared_rg_index=prepared_rg_index,
            prepared_rg_members=prepared_rg_members,
        )

        excluded_nodes.update(failed_nodes)
        excluded_links.update(failed_links)
        for rg_name in failed_rgs:
            risk_group_nodes, risk_group_links = self._get_risk_group_exclusions(
                rg_name
            )
            excluded_nodes.update(risk_group_nodes)
            excluded_links.update(risk_group_links)

        return excluded_nodes, excluded_links

    def _get_risk_group_exclusions(
        self,
        risk_group_name: str,
    ) -> tuple[frozenset[str], frozenset[str]]:
        """Return transitive node/link exclusions for a failed risk group."""
        if self._risk_group_exclusions is None:
            self._risk_group_exclusions = self._build_risk_group_exclusions()
        return self._risk_group_exclusions.get(
            risk_group_name,
            (frozenset(), frozenset()),
        )

    def _build_risk_group_exclusions(
        self,
    ) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
        """Build transitive member index for each risk group once per manager."""
        direct_nodes: dict[str, set[str]] = {
            name: set() for name in self.network.risk_groups
        }
        direct_links: dict[str, set[str]] = {
            name: set() for name in self.network.risk_groups
        }

        for node_name, node in self.network.nodes.items():
            for risk_group_name in node.risk_groups:
                direct_nodes.setdefault(risk_group_name, set()).add(node_name)

        for link_id, link in self.network.links.items():
            for risk_group_name in link.risk_groups:
                direct_links.setdefault(risk_group_name, set()).add(link_id)

        expanded: dict[str, tuple[frozenset[str], frozenset[str]]] = {}

        # Recurse on RiskGroup objects directly: nested groups are not
        # registered in network.risk_groups (only top-level groups are), so
        # resolving children by name would silently drop grandchild members.
        def expand_group(
            group: "RiskGroup",
        ) -> tuple[frozenset[str], frozenset[str]]:
            cached = expanded.get(group.name)
            if cached is not None:
                return cached
            if group.name in visiting:
                return (
                    frozenset(direct_nodes.get(group.name, ())),
                    frozenset(direct_links.get(group.name, ())),
                )

            visiting.add(group.name)
            nodes = set(direct_nodes.get(group.name, ()))
            links = set(direct_links.get(group.name, ()))
            for child in group.children:
                child_nodes, child_links = expand_group(child)
                nodes.update(child_nodes)
                links.update(child_links)

            result = (frozenset(nodes), frozenset(links))
            visiting.remove(group.name)
            expanded[group.name] = result
            return result

        visiting: set[str] = set()
        for risk_group in self.network.risk_groups.values():
            expand_group(risk_group)

        return expanded

    def _get_prepared_policy_matches(
        self,
        policy: "FailurePolicy",
        node_map: dict[str, dict[str, Any]],
        link_map: dict[str, dict[str, Any]],
        rg_map: dict[str, dict[str, Any]],
    ) -> dict[int, tuple[str, ...]]:
        """Prepare stable ordered candidate pools for a policy once per manager."""
        policy_key = id(policy)
        cached = self._prepared_policy_matches.get(policy_key)
        if cached is not None and cached[0] is policy:
            return cached[1]

        prepared = policy.prepare_matches(
            node_map,
            link_map,
            rg_map,
        )
        self._prepared_policy_matches[policy_key] = (policy, prepared)
        return prepared

    def _get_prepared_policy_weights(
        self,
        policy: "FailurePolicy",
        prepared_matches: dict[int, tuple[str, ...]],
        node_map: dict[str, dict[str, Any]],
        link_map: dict[str, dict[str, Any]],
        rg_map: dict[str, dict[str, Any]],
    ) -> dict[int, tuple[dict[str, float], tuple[str, ...]]]:
        """Prepare per-rule weight splits for a policy once per manager."""
        policy_key = id(policy)
        cached = self._prepared_policy_weights.get(policy_key)
        if cached is not None and cached[0] is policy:
            return cached[1]

        # Duck-typed policy objects may not implement the optional
        # prepare_weights optimization; treat it as "no precomputed weights".
        prepare = getattr(policy, "prepare_weights", None)
        prepared = (
            prepare(prepared_matches, node_map, link_map, rg_map) if prepare else {}
        )
        self._prepared_policy_weights[policy_key] = (policy, prepared)
        return prepared

    def _get_prepared_rg_index(self) -> dict[str, set[str]]:
        """Build the risk-group -> entity-ID expansion index once per manager.

        The index consumed by ``FailurePolicy.apply_failures`` (via
        ``prepared_rg_index``) depends only on the static network, so it is
        built once and reused across policies and Monte Carlo iterations
        instead of being rebuilt on every ``apply_failures`` call.
        """
        if self._prepared_rg_index is None:
            self._ensure_flattened_maps()
            assert (
                self._merged_node_attrs is not None
            )  # guaranteed by _ensure_flattened_maps
            assert self._merged_link_attrs is not None
            self._prepared_rg_index = FailurePolicy.build_risk_group_index(
                self._merged_node_attrs,
                self._merged_link_attrs,
            )
        return self._prepared_rg_index

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

        The analysis function is arbitrary (see AnalysisFunction); this method
        supplies the exclusion sets, the parallelism, and the deduplication.

        Baseline is always run first as a separate reference iteration (no failures).

        Analysis functions may carry a ``prepare_inputs`` attribute; the
        built-in ones do, and custom functions can set
        ``func.prepare_inputs = lambda network, kwargs: {...}``. It runs once
        per run, and the kwargs it returns (typically a pre-built ``context``)
        are merged into every iteration's call, so expensive graph
        construction happens once. Functions without the attribute run with
        their kwargs unchanged, and passing ``context`` explicitly skips the
        hook.

        Args:
            analysis_func: Function that takes (network, excluded_nodes, excluded_links, **kwargs)
                          and returns results. Executed concurrently via threads;
                          the network is shared by reference and must not be mutated.
            iterations: Number of failure iterations to run (baseline is always run separately).
            parallelism: Number of parallel worker threads to use.
            seed: Optional seed for reproducible results across runs. If None,
                falls back to the policy's own seed when set, so iterations
                still vary while remaining reproducible.
            store_failure_patterns: If True, populate failure_trace on each result.
                Iterations are deduplicated by exclusion pattern, so the trace
                describes the representative (first) iteration of each pattern;
                different mode/rule draws that produced the same exclusions are
                not individually recorded.
            **analysis_kwargs: Additional arguments passed to analysis_func.

        Returns:
            Dictionary containing:
            - 'baseline': FlowIterationResult for the baseline (no failures)
            - 'results': List of unique results (deduplicated patterns).
              FlowIterationResult objects carry occurrence_count; for any
              result type, metadata["occurrence_counts"] is aligned with
              this list.
            - 'metadata': Execution metadata (iterations, unique_patterns,
              occurrence_counts, execution_time, etc.)

        Note:
            Deduplication executes each unique exclusion pattern once and
            weights it by occurrence count, which is statistically valid only
            for deterministic analysis functions (the built-ins are). A
            stochastic custom function should not rely on per-iteration
            re-execution.
        """
        policy = self.get_failure_policy()

        has_effective_rules = bool(
            policy and any(len(m.rules) > 0 for m in policy.modes)
        )

        # Without effective rules, only baseline makes sense (no failure iterations)
        if not has_effective_rules:
            iterations = 0

        logger.info(
            f"Running baseline + {iterations} failure iterations"
            if iterations > 0
            else "Running baseline only (no failure policy)"
        )

        # Pre-build expensive per-run inputs when the analysis function
        # carries a `prepare_inputs` hook (attached by the built-in analysis
        # functions; third-party functions can set the attribute themselves)
        # and the caller did not supply a pre-built context. This amortizes
        # graph construction across all iterations.
        prepare = getattr(analysis_func, "prepare_inputs", None)
        if prepare is not None and "context" not in analysis_kwargs:
            cache_start = time.time()
            analysis_kwargs = dict(analysis_kwargs)  # Don't mutate caller's dict
            analysis_kwargs.update(prepare(self.network, analysis_kwargs))
            logger.debug(
                f"Pre-built analysis inputs in {time.time() - cache_start:.3f}s"
            )

        # Get function name safely (Protocol doesn't guarantee __name__)
        func_name = getattr(analysis_func, "__name__", "analysis_function")
        logger.debug(
            f"Analysis parameters: function={func_name}, "
            f"parallelism={parallelism}, policy={self.policy_name}"
        )

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

        logger.debug("Pre-computing failure exclusions for all iterations")
        pre_compute_start = time.time()

        key_to_first_arg: dict[tuple, tuple] = {}
        key_to_count: dict[tuple, int] = {}
        key_to_trace: dict[tuple, dict[str, Any]] = {}

        # Fall back to the policy's own seed so iterations still vary: with
        # seed_offset=None a seeded policy would rebuild the identical RNG
        # (and failure pattern) on every iteration.
        effective_seed = seed
        if effective_seed is None and policy is not None:
            effective_seed = policy.seed

        # Invariant across iterations; only the exclusion sets vary.
        kwargs_key = _hashable_kwargs_key(analysis_kwargs)

        for i in range(iterations):
            seed_offset = effective_seed + i if effective_seed is not None else None
            trace = {} if store_failure_patterns else None
            excluded_nodes, excluded_links = self.compute_exclusions(
                policy, seed_offset, failure_trace=trace
            )

            dedup_key = _create_dedup_key(
                excluded_nodes, excluded_links, func_name, kwargs_key
            )
            if dedup_key not in key_to_first_arg:
                key_to_first_arg[dedup_key] = (
                    self.network,
                    excluded_nodes,
                    excluded_links,
                    analysis_func,
                    analysis_kwargs,
                    i,  # iteration_index (0-based for failures)
                    False,  # is_baseline
                    func_name,
                )
                key_to_count[dedup_key] = 1
                if trace is not None:
                    key_to_trace[dedup_key] = trace
            else:
                key_to_count[dedup_key] += 1

        pre_compute_time = time.time() - pre_compute_start
        logger.debug(
            f"Pre-computed {iterations} failure exclusion sets in {pre_compute_time:.2f}s"
        )

        unique_worker_args: list[tuple] = list(key_to_first_arg.values())
        num_unique_tasks: int = len(unique_worker_args)
        if iterations > 0:
            logger.info(
                f"Monte-Carlo deduplication: {num_unique_tasks} unique patterns from {iterations} failure iterations"
            )

        start_time = time.time()

        baseline_result_raw = self._run_serial([baseline_arg])
        baseline_result = baseline_result_raw[0] if baseline_result_raw else None

        if baseline_result is not None and hasattr(baseline_result, "failure_id"):
            baseline_result.failure_id = ""
            baseline_result.failure_state = {"excluded_nodes": [], "excluded_links": []}
            baseline_result.failure_trace = None

        if iterations > 0:
            use_parallel = parallelism > 1 and num_unique_tasks > 1
            if use_parallel:
                unique_result_values = self._run_parallel(
                    unique_worker_args, num_unique_tasks, parallelism
                )
            else:
                unique_result_values = self._run_serial(unique_worker_args)

            key_to_result: dict[tuple, Any] = {}
            for (dedup_key, _arg), value in zip(
                key_to_first_arg.items(), unique_result_values, strict=True
            ):
                key_to_result[dedup_key] = value
        else:
            key_to_result = {}

        elapsed_time = time.time() - start_time

        # Enrich unique failure results with metadata and occurrence_count.
        # metadata["occurrence_counts"] carries the per-pattern multiplicity
        # aligned with `results`, so custom result types (which cannot be
        # enriched in place) still get correct weights for aggregation.
        results: list[Any] = []
        occurrence_counts: list[int] = []
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
            occurrence_counts.append(key_to_count[dedup_key])

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
                "occurrence_counts": occurrence_counts,
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

            for result in pool.map(_generic_worker, worker_args):
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

        try:
            for i, args in enumerate(worker_args):
                iter_start = time.time()

                is_baseline_arg = len(args) > 6 and args[6]  # is_baseline flag
                baseline_msg = " (baseline)" if is_baseline_arg else ""
                logger.debug(
                    f"Serial iteration {i + 1}/{len(worker_args)}{baseline_msg}"
                )

                result = _generic_worker(args)

                results.append(result)

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
            # Restore worker profiling env var even if an analysis function raised
            if _restore_profile_env and _saved_profile_dir is not None:
                os.environ["NGRAPH_PROFILE_DIR"] = _saved_profile_dir

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
        """Run one failure iteration, for quick analysis or debugging.

        For full Monte Carlo analysis, use run_monte_carlo_analysis().

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
        if result["results"]:
            return result["results"][0]
        return result["baseline"]

    # Convenience methods for common analysis patterns

    def run_max_flow_monte_carlo(
        self,
        source: str | dict[str, Any],
        target: str | dict[str, Any],
        mode: str = "combine",
        iterations: int = 100,
        parallelism: int = 1,
        shortest_path: bool = False,
        require_capacity: bool = True,
        flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL,
        seed: int | None = None,
        store_failure_patterns: bool = False,
        include_flow_summary: bool = False,
        include_min_cut: bool = False,
    ) -> Any:
        """Compute max-flow capacity envelopes between node groups under failures.

        Each iteration applies one failure pattern and re-solves; the
        per-pattern results, weighted by occurrence count, form the
        frequency-based envelope.

        Baseline (no failures) is always run first as a separate reference.

        Args:
            source: Source node selector (string path or selector dict).
            target: Target node selector (string path or selector dict).
            mode: "combine" (aggregate) or "pairwise" (individual flows).
            iterations: Number of failure scenarios to simulate.
            parallelism: Number of parallel worker threads.
            shortest_path: If True, use single-tier shortest-path flow (IP/IGP
                mode) instead of full iterative max-flow.
            require_capacity: If True (default), path selection considers available
                capacity. If False, path selection is cost-only (true IP/IGP semantics).
            flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP);
                accepts the enum or its string name.
            seed: Optional seed for reproducible results. If None, falls back
                to the policy's own seed when set.
            store_failure_patterns: Whether to store failure trace on results.
            include_flow_summary: Whether to collect detailed flow summary data.
            include_min_cut: Whether to include min-cut edges in results.

        Returns:
            Dictionary with keys:
            - 'baseline': FlowIterationResult for baseline (no failures)
            - 'results': List of unique FlowIterationResult objects (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        if isinstance(flow_placement, str):
            flow_placement = FlowPlacement.from_string(flow_placement)

        raw_results = self.run_monte_carlo_analysis(
            analysis_func=max_flow_analysis,
            iterations=iterations,
            parallelism=parallelism,
            seed=seed,
            store_failure_patterns=store_failure_patterns,
            source=source,
            target=target,
            mode=mode,
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            include_flow_details=include_flow_summary,
            include_min_cut=include_min_cut,
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
        | Any,  # List of demand configs or DemandSet
        iterations: int = 100,
        parallelism: int = 1,
        seed: int | None = None,
        store_failure_patterns: bool = False,
        include_flow_details: bool = False,
        include_used_edges: bool = False,
    ) -> Any:
        """Analyze traffic demand placement success under failures.

        Attempts to place traffic demands on the network across
        Monte Carlo failure scenarios and measures success rates.

        Baseline (no failures) is always run first as a separate reference.

        Args:
            demands_config: List of demand configs or DemandSet object.
            iterations: Number of failure scenarios to simulate.
            parallelism: Number of parallel worker threads.
            seed: Optional seed for reproducible results. If None, falls back
                to the policy's own seed when set.
            store_failure_patterns: Whether to store failure trace on results.
            include_flow_details: Whether to include cost distribution details.
            include_used_edges: Whether to include used edges in results.

        Returns:
            Dictionary with keys:
            - 'baseline': FlowIterationResult for baseline (no failures)
            - 'results': List of unique FlowIterationResult objects (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        # If caller passed a sequence of TrafficDemand objects, convert to dicts
        if not isinstance(demands_config, list):
            # Accept DemandSet or any container providing get_all_demands()
            serializable_demands: list[dict[str, Any]] = []
            if hasattr(demands_config, "get_all_demands"):
                td_iter = demands_config.get_all_demands()  # DemandSet helper
            else:
                td_iter = []
            for demand in td_iter:  # type: ignore[assignment]
                # Analysis wire format: canonical dict with the raw preset
                serializable_demands.append(
                    {**demand.to_dict(), "flow_policy": demand.flow_policy}
                )
            demands_config = serializable_demands

        raw_results = self.run_monte_carlo_analysis(
            analysis_func=demand_placement_analysis,
            iterations=iterations,
            parallelism=parallelism,
            seed=seed,
            store_failure_patterns=store_failure_patterns,
            demands_config=demands_config,
            include_flow_details=include_flow_details,
            include_used_edges=include_used_edges,
        )
        return raw_results

    def run_sensitivity_monte_carlo(
        self,
        source: str | dict[str, Any],
        target: str | dict[str, Any],
        mode: str = "combine",
        iterations: int = 100,
        parallelism: int = 1,
        shortest_path: bool = False,
        flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL,
        seed: int | None = None,
        store_failure_patterns: bool = False,
    ) -> dict[str, Any]:
        """Analyze component criticality for flow capacity under failures.

        Identifies critical network components by measuring their impact on flow
        capacity across Monte Carlo failure scenarios.

        Baseline (no failures) is always run first as a separate reference.

        Args:
            source: Source node selector (string path or selector dict).
            target: Target node selector (string path or selector dict).
            mode: "combine" (aggregate) or "pairwise" (individual flows).
            iterations: Number of failure scenarios to simulate.
            parallelism: Number of parallel worker threads.
            shortest_path: If True, report only edges used under ECMP routing
                (IP/IGP mode); if False, report all saturated edges (SDN/TE).
            flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP);
                accepts the enum or its string name.
            seed: Optional seed for reproducible results. If None, falls back
                to the policy's own seed when set.
            store_failure_patterns: Whether to store failure trace on results.

        Returns:
            Dictionary with keys:
            - 'baseline': Baseline result (no failures)
            - 'results': List of unique per-iteration sensitivity dicts (deduplicated patterns).
              Each result has occurrence_count indicating how many iterations matched.
            - 'component_scores': aggregated statistics (mean, max, min, count) per component per flow
            - 'metadata': Execution metadata (iterations, unique_patterns, execution_time, etc.)
        """
        if isinstance(flow_placement, str):
            flow_placement = FlowPlacement.from_string(flow_placement)

        raw_results = self.run_monte_carlo_analysis(
            analysis_func=sensitivity_analysis,
            iterations=iterations,
            parallelism=parallelism,
            seed=seed,
            store_failure_patterns=store_failure_patterns,
            source=source,
            target=target,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )

        # Aggregate component scores across iterations for statistical analysis
        raw_results["component_scores"] = self._process_sensitivity_results(
            raw_results["results"]
        )

        # Augment metadata with analysis-specific context
        raw_results["metadata"]["source"] = source
        raw_results["metadata"]["target"] = target
        raw_results["metadata"]["mode"] = mode

        return raw_results
