"""Benchmark pairwise max-flow on a scenario graph.

This script loads a scenario YAML, builds its `StrictMultiDiGraph`, identifies
datacenter nodes by a regex pattern, and measures the runtime of three modes:

- bare: direct pairwise calls to `calc_max_flow` on graph copies
- solver: `ngraph.solver.maxflow.max_flow(..., mode="pairwise")`
- fm: FailureManager `run_max_flow_monte_carlo` with iterations=1

Use this to compare backbone vs clos scenarios and isolate overheads.

Run examples:

  python -m dev.bench_pairwise_maxflow \
    --scenario scenarios/backbone.yml --limit-pairs 50

  python -m dev.bench_pairwise_maxflow \
    --scenario scenarios/clos_scenario.yml --limit-pairs 50

Notes:
- The script does not modify the repository state and writes no files by default.
- For large scenarios, consider `--limit-pairs` or `--max-metros` to constrain work.
"""

from __future__ import annotations

import argparse
import statistics
import time
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, Sequence, Tuple

from ngraph.algorithms.max_flow import calc_max_flow
from ngraph.failure.manager.manager import FailureManager
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.scenario import Scenario
from ngraph.solver.maxflow import max_flow as solver_max_flow


def _pairwise(iterable: Sequence[str]) -> Iterator[Tuple[str, str]]:
    for i, a in enumerate(iterable):
        for j, b in enumerate(iterable):
            if i == j:
                continue
            yield a, b


def _take(it: Iterable[Tuple[str, str]], n: int | None) -> list[Tuple[str, str]]:
    if n is None or n <= 0:
        return list(it)
    return list(islice(it, n))


def _select_dc_nodes(scenario: Scenario, group_pattern: str) -> list[Tuple[str, str]]:
    """Return list of (label, node_name) for DC groups.

    Args:
        scenario: Loaded scenario instance.
        group_pattern: Regex used to group/select DC nodes; labels are group labels.

    Returns:
        List of tuples where each tuple is (group_label, node_name). If a group
        contains multiple nodes, each node is returned with the same label.
    """
    groups = scenario.network.select_node_groups_by_path(group_pattern)
    items: list[Tuple[str, str]] = []
    for label, nodes in groups.items():
        for node in nodes:
            items.append((label, node.name))
    # Stable by label then node name
    items.sort(key=lambda p: (p[0], p[1]))
    return items


def _build_base_graph(scenario: Scenario) -> StrictMultiDiGraph:
    """Build the base graph from the scenario network (bidirectional links)."""
    return scenario.network.to_strict_multidigraph(add_reverse=True)


def _bench_bare_pairwise(
    base_graph: StrictMultiDiGraph,
    dc_nodes: list[Tuple[str, str]],
    limit_pairs: int | None,
) -> dict:
    """Benchmark direct calc_max_flow calls with pseudo source/sink per pair.

    For each (src_node, dst_node), copy the base_graph, attach pseudo nodes with
    infinite capacity, then call `calc_max_flow(copy_graph=False)`.
    """
    # Deduplicate labels by node selection order
    node_names: list[str] = [n for (_, n) in dc_nodes]
    pairs: list[Tuple[str, str]] = _take(_pairwise(node_names), limit_pairs)

    times_ms: list[float] = []
    last_flow: float | None = None
    t_start = time.perf_counter()

    for src, dst in pairs:
        g = base_graph.copy()
        g.add_node("source")
        g.add_node("sink")
        g.add_edge("source", src, capacity=float("inf"), cost=0)
        g.add_edge(dst, "sink", capacity=float("inf"), cost=0)
        t0 = time.perf_counter()
        last_flow = float(
            calc_max_flow(
                g,
                "source",
                "sink",
                copy_graph=False,
            )
        )
        t1 = time.perf_counter()
        times_ms.append(1000.0 * (t1 - t0))

    t_end = time.perf_counter()
    return {
        "pairs": len(pairs),
        "last_flow": last_flow,
        "elapsed_s": (t_end - t_start),
        "min_ms": min(times_ms) if times_ms else 0.0,
        "mean_ms": statistics.mean(times_ms) if times_ms else 0.0,
        "median_ms": statistics.median(times_ms) if times_ms else 0.0,
        "max_ms": max(times_ms) if times_ms else 0.0,
    }


def _bench_solver_pairwise(
    scenario: Scenario,
    group_pattern: str,
) -> dict:
    """Benchmark solver.max_flow pairwise over all groups (no limit)."""
    t0 = time.perf_counter()
    flows = solver_max_flow(
        scenario.network,
        group_pattern,
        group_pattern,
        mode="pairwise",
        shortest_path=False,
    )
    t1 = time.perf_counter()
    return {
        "pairs": len(flows),
        "elapsed_s": (t1 - t0),
        "nonzero": sum(1 for v in flows.values() if v > 0.0),
    }


def _bench_failure_manager(
    scenario: Scenario,
    group_pattern: str,
) -> dict:
    """Benchmark FailureManager with iterations=1, pairwise mode.

    This mirrors the CapacityEnvelopeAnalysis step configuration used in scenarios.
    """
    fm = FailureManager(
        network=scenario.network,
        failure_policy_set=scenario.failure_policy_set,
        policy_name=None,
    )
    t0 = time.perf_counter()
    res = fm.run_max_flow_monte_carlo(
        source_path=group_pattern,
        sink_path=group_pattern,
        mode="pairwise",
        iterations=1,
        parallelism=1,
        shortest_path=False,
        flow_placement="PROPORTIONAL",
        baseline=False,
        seed=scenario.seed,
        store_failure_patterns=False,
        include_flow_summary=False,
    )
    t1 = time.perf_counter()
    meta = getattr(res, "metadata", {})
    envs = getattr(res, "envelopes", {})
    return {
        "pairs": len(envs),
        "elapsed_s": (t1 - t0),
        "meta_time_s": float(meta.get("execution_time", 0.0))
        if isinstance(meta, dict)
        else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector.

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Benchmark pairwise max-flow for a scenario"
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Path to scenario YAML",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=r"(metro[0-9]+/dc[0-9]+)",
        help="Regex to group/select DC nodes (use capturing group to label)",
    )
    parser.add_argument(
        "--limit-pairs",
        type=int,
        default=0,
        help="Limit number of pairwise computations in bare mode (0 = all)",
    )
    parser.add_argument(
        "--skip-modes",
        type=str,
        default="",
        help="Comma-separated modes to skip: bare,solver,fm",
    )

    args = parser.parse_args(argv)
    skip = {s.strip() for s in args.skip_modes.split(",") if s.strip()}

    yaml_text = args.scenario.read_text()
    scenario = Scenario.from_yaml(yaml_text)

    # Build graph and DC node list
    base_graph = _build_base_graph(scenario)
    dc_items = _select_dc_nodes(scenario, args.pattern)
    dc_labels = sorted({lbl for (lbl, _) in dc_items})

    print(f"scenario: {args.scenario}")
    print(
        f"graph: nodes={len(base_graph)}, edges={base_graph.number_of_edges()} | dcs={len(dc_labels)}"
    )

    # Mode: bare
    if "bare" not in skip:
        print("[bench] bare pairwise calc_max_flow ...")
        bare_stats = _bench_bare_pairwise(
            base_graph,
            dc_items,
            None if args.limit_pairs <= 0 else int(args.limit_pairs),
        )
        print(
            f"[bare ] pairs={bare_stats['pairs']} elapsed={bare_stats['elapsed_s']:.3f}s "
            f"min/mean/med/max={bare_stats['min_ms']:.2f}/{bare_stats['mean_ms']:.2f}/"
            f"{bare_stats['median_ms']:.2f}/{bare_stats['max_ms']:.2f} ms"
        )

    # Mode: solver (full pairwise)
    if "solver" not in skip:
        print("[bench] solver.max_flow pairwise ...")
        sol_stats = _bench_solver_pairwise(scenario, args.pattern)
        print(
            f"[solve] pairs={sol_stats['pairs']} elapsed={sol_stats['elapsed_s']:.3f}s "
            f"nonzero={sol_stats['nonzero']}"
        )

    # Mode: FailureManager (iterations=1)
    if "fm" not in skip:
        print("[bench] FailureManager iterations=1 pairwise ...")
        fm_stats = _bench_failure_manager(scenario, args.pattern)
        print(
            f"[fm   ] pairs={fm_stats['pairs']} elapsed={fm_stats['elapsed_s']:.3f}s "
            f"meta_time={fm_stats['meta_time_s']:.3f}s"
        )

    return 0


if __name__ == "__main__":  # pragma: no cover - manual utility
    raise SystemExit(main())
