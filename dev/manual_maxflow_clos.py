"""Manual max-flow timing on the CLOS scenario graph.

Reads the serialized node-link graph under the ``build_graph`` section of a
results JSON file (e.g., ``clos_scenario.json``), reconstructs a
``StrictMultiDiGraph``, and runs ``calc_max_flow`` between two specified nodes
while reporting timing, optional profiling, and summary diagnostics.

Run from repo root:

    python -m dev.manual_maxflow_clos --json clos_scenario.json \
        --source "metro1/dc1/dc/dc" --sink "metro10/dc1/dc/dc"

The script prints: load times, node/edge counts, degree of endpoints,
max-flow value, min-cut size, and a few top edges by placed flow.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import platform
import pstats
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from pstats import SortKey
from typing import Any, Iterable

from ngraph.algorithms.max_flow import calc_max_flow
from ngraph.graph.io import node_link_to_graph
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def _format_bytes(num_bytes: int) -> str:
    """Return a human-friendly string for a byte count.

    Args:
        num_bytes: Number of bytes.

    Returns:
        Formatted size string.
    """

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def _top_k_by_flow(
    edge_flow_items: Iterable[tuple[tuple[Any, Any, Any], float]], k: int
) -> list[tuple[tuple[Any, Any, Any], float]]:
    """Return top-k edges by flow value.

    Args:
        edge_flow_items: Iterable of ``((u, v, key), flow)`` items.
        k: Number of entries to return.

    Returns:
        List of top-k items sorted by descending flow.
    """

    # Convert to list once since we'll sort
    items = list(edge_flow_items)
    items.sort(key=lambda p: p[1], reverse=True)
    return items[:k]


def load_graph_from_results(json_path: Path) -> StrictMultiDiGraph:
    """Load ``StrictMultiDiGraph`` from a results JSON file.

    The file must contain ``{"build_graph": {"graph": { ... node-link ... }}}``.

    Args:
        json_path: Path to results JSON file.

    Returns:
        Reconstructed ``StrictMultiDiGraph``.

    Raises:
        FileNotFoundError: If the JSON file does not exist.
        KeyError: If required keys are missing.
        json.JSONDecodeError: If JSON cannot be parsed.
    """

    if not json_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    file_size = json_path.stat().st_size
    print(f"[load] Reading: {json_path} ({_format_bytes(file_size)})")

    t0 = time.perf_counter()
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    t1 = time.perf_counter()
    print(f"[load] JSON parsed in {1000.0 * (t1 - t0):.2f} ms")

    graph_payload = data["build_graph"]["graph"]
    t2 = time.perf_counter()
    graph = node_link_to_graph(graph_payload)
    t3 = time.perf_counter()
    print(
        f"[load] Graph reconstructed in {1000.0 * (t3 - t2):.2f} ms; "
        f"nodes={len(graph)}, edges={graph.number_of_edges()}"
    )
    return graph


def _run_maxflow_once(
    graph: StrictMultiDiGraph, src: Any, dst: Any
) -> tuple[float, Any, float]:
    """Run one max-flow measurement.

    Args:
        graph: Graph instance.
        src: Source node ID.
        dst: Sink node ID.

    Returns:
        Tuple of (flow_value, summary, elapsed_ms).
    """

    t_start = time.perf_counter()
    flow_value, summary = calc_max_flow(graph, src, dst, return_summary=True)
    t_end = time.perf_counter()
    return flow_value, summary, 1000.0 * (t_end - t_start)


def _profile_maxflow(
    graph: StrictMultiDiGraph,
    src: Any,
    dst: Any,
    *,
    sort_by: str,
    top_n: int,
    save_path: Path | None,
) -> None:
    """Profile ``calc_max_flow`` with cProfile and print top entries.

    Args:
        graph: Graph instance.
        src: Source node ID.
        dst: Sink node ID.
        sort_by: Sort key for stats (e.g., 'cumulative', 'tottime').
        top_n: Number of entries to display.
        save_path: If provided, write raw profile data to this path.
    """

    print("[prof] cProfile starting...")
    pr = cProfile.Profile()
    pr.enable()
    _ = calc_max_flow(graph, src, dst, return_summary=False)
    pr.disable()

    if save_path is not None:
        pr.dump_stats(str(save_path))
        print(f"[prof] raw stats saved to: {save_path}")

    stats = pstats.Stats(pr)
    sort_key = {
        "cumulative": SortKey.CUMULATIVE,
        "tottime": SortKey.TIME,
        "ncalls": SortKey.CALLS,
        "file": SortKey.FILENAME,
        "name": SortKey.NAME,
        "line": SortKey.LINE,
    }.get(sort_by, SortKey.CUMULATIVE)
    stats.sort_stats(sort_key)
    print(f"[prof] top {top_n} by {sort_by}:")
    stats.print_stats(top_n)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Optional argument vector.

    Returns:
        Process exit code (0 on success, non-zero on failure).
    """

    parser = argparse.ArgumentParser(
        description="Time and optionally profile calc_max_flow on a CLOS scenario results graph",
    )
    parser.add_argument(
        "--json",
        type=Path,
        required=True,
        help="Path to results JSON containing build_graph.graph (e.g., clos_scenario.json)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="metro1/dc1/dc/dc",
        help="Source node ID",
    )
    parser.add_argument(
        "--sink",
        type=str,
        default="metro10/dc1/dc/dc",
        help="Sink node ID",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Show top-K edges by placed flow in summary",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat max-flow computation N times (report per-run and summary stats)",
    )
    parser.add_argument(
        "--cprofile",
        action="store_true",
        help="Run cProfile around a scalar max-flow call (no summary).",
    )
    parser.add_argument(
        "--profile-save",
        type=Path,
        default=None,
        help="If set, save raw cProfile stats to this path.",
    )
    parser.add_argument(
        "--profile-sort",
        type=str,
        choices=["cumulative", "tottime", "ncalls", "file", "name", "line"],
        default="cumulative",
        help="Sort key for cProfile stats printing.",
    )
    parser.add_argument(
        "--profile-top",
        type=int,
        default=30,
        help="Number of cProfile entries to print.",
    )

    args = parser.parse_args(argv)

    try:
        tracemalloc.start()

        # Load graph from JSON
        graph = load_graph_from_results(args.json)

        # Environment diagnostics
        print(
            f"[env ] Python {platform.python_version()} | pid={os.getpid()} | "
            f"cpus={os.cpu_count()}"
        )

        # Sanity checks on endpoints
        src = args.source
        dst = args.sink
        print(f"[info] Source: {src}")
        print(f"[info] Sink  : {dst}")

        missing = [n for n in (src, dst) if n not in graph]
        if missing:
            print(f"[error] Missing nodes: {missing}")
            # Provide hints for nearby IDs by simple substring heuristic
            for node in (src, dst):
                if node not in graph:
                    candidates = [n for n in graph if node.split("/")[0] in str(n)]
                    sample = candidates[:10]
                    print(
                        f"[hint] Examples of nodes sharing metro prefix for {node!r}:"
                    )
                    for ex in sample:
                        print(f"        {ex}")
            return 2

        src_out = graph.out_degree(src)
        dst_in = graph.in_degree(dst)
        print(f"[info] deg_out({src})={src_out}, deg_in({dst})={dst_in}")

        # Repeat runs
        times_ms: list[float] = []
        last_flow_value: float | None = None
        last_summary: Any | None = None

        for i in range(args.repeat):
            print(f"[run ] iteration {i + 1}/{args.repeat} starting...")
            flow_value, summary, elapsed_ms = _run_maxflow_once(graph, src, dst)
            times_ms.append(elapsed_ms)
            last_flow_value = flow_value
            last_summary = summary
            print(
                f"[done] iteration {i + 1}: {elapsed_ms:.2f} ms; flow={flow_value:.6f}"
            )

        current, peak = tracemalloc.get_traced_memory()
        if times_ms:
            print(
                f"[stat] time ms -> min={min(times_ms):.2f}, "
                f"mean={statistics.mean(times_ms):.2f}, "
                f"median={statistics.median(times_ms):.2f}, "
                f"max={max(times_ms):.2f}"
            )
        print(f"[mem ] current={_format_bytes(current)}, peak={_format_bytes(peak)}")

        # Diagnostics from last summary
        if last_summary is not None and last_flow_value is not None:
            summary = last_summary
            print(
                f"[sum ] min_cut_size={len(summary.min_cut)}, "
                f"reachable={len(summary.reachable)}, "
                f"cost_buckets={len(summary.cost_distribution)}"
            )
            # List a few top edges by placed flow
            top_k = _top_k_by_flow(summary.edge_flow.items(), args.top_k)
            print(f"[sum ] top {len(top_k)} edges by flow:")
            for (u, v, k), f in top_k:
                if f <= 0:
                    break
                print(f"       {u} -> {v} (key={k}) flow={f}")

        # Optional profiling (single scalar call for cleaner stats)
        if args.cprofile:
            _profile_maxflow(
                graph,
                src,
                dst,
                sort_by=args.profile_sort,
                top_n=args.profile_top,
                save_path=args.profile_save,
            )

        return 0
    except KeyboardInterrupt:
        print("[abort] interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 - manual script diagnostics
        print(f"[error] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
