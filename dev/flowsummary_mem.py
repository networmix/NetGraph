#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import is_dataclass
from typing import Any

from ngraph.scenario import Scenario
from ngraph.workflow.max_flow_step import MaxFlow


def _deep_size(obj: Any, seen: set[int] | None = None) -> int:
    """Approximate deep size in bytes for common Python containers.

    This walks dicts, lists, tuples, sets, and dataclasses. It avoids cycles
    using an object id set. This is an approximation intended for breakdowns,
    not exact accounting.
    """
    import sys as _sys

    if seen is None:
        seen = set()

    oid = id(obj)
    if oid in seen:
        return 0
    seen.add(oid)

    size = _sys.getsizeof(obj)

    # Basic containers
    if isinstance(obj, dict):
        for k, v in obj.items():
            size += _deep_size(k, seen)
            size += _deep_size(v, seen)
        return size

    if isinstance(obj, (list, tuple, set, frozenset)):
        for it in obj:
            size += _deep_size(it, seen)
        return size

    # Dataclasses: walk fields via __dict__
    if is_dataclass(obj):
        # Use __dict__ if available; dataclasses with slots may differ
        d = getattr(obj, "__dict__", None)
        if d is not None:
            size += _deep_size(d, seen)
        else:
            # Fallback: iterate over attributes if __slots__
            for attr in dir(obj):
                if attr.startswith("_"):
                    continue
                try:
                    val = getattr(obj, attr)
                except Exception:
                    continue
                size += _deep_size(val, seen)
        return size

    # Builtins (int, float, str, bytes, etc.) measured by getsizeof already
    return size


def pick_capacity_step(scn: Scenario) -> MaxFlow:
    for step in scn.workflow:
        if isinstance(step, MaxFlow):
            return step
    raise RuntimeError("No MaxFlow step found in scenario")


def stringify_edge(edge: Any) -> str:
    try:
        if isinstance(edge, (list, tuple)) and len(edge) == 3:
            u, v, k = edge
            return f"({u!s}, {v!s}, {k!s})"
        return str(edge)
    except Exception:
        return str(edge)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Inspect FlowSummary memory usage")
    parser.add_argument("scenario", help="Path to scenario YAML")
    parser.add_argument(
        "--pair-index",
        type=int,
        default=-1,
        help="Specific (src,dst) index to show in detail; -1 scans all",
    )
    args = parser.parse_args(argv)

    # Load scenario
    yaml_text = open(args.scenario, "r", encoding="utf-8").read()
    scenario = Scenario.from_yaml(yaml_text)

    step = pick_capacity_step(scenario)

    # Compute flow with summary for baseline (no failures)
    # Resolve flow_placement to enum if needed
    fp = getattr(step, "flow_placement", None)
    from ngraph.algorithms.base import FlowPlacement as _FP

    if isinstance(fp, str):
        fp_enum = _FP[fp.upper()]
    elif fp is None:
        fp_enum = _FP.PROPORTIONAL
    else:
        fp_enum = fp  # assume already FlowPlacement

    res = scenario.network.max_flow_with_summary(
        step.source_path,
        step.sink_path,
        mode=step.mode,
        shortest_path=step.shortest_path,
        flow_placement=fp_enum,
    )

    items = list(res.items())
    if not items:
        print("No flow pairs produced", file=sys.stderr)
        return 2

    def summarize_one(summary: Any) -> tuple[dict[str, int], dict[str, int], int]:
        total_flow = getattr(summary, "total_flow", None)
        edge_flow = getattr(summary, "edge_flow", None)
        residual_cap = getattr(summary, "residual_cap", None)
        reachable = getattr(summary, "reachable", None)
        min_cut = getattr(summary, "min_cut", None)
        cost_distribution = getattr(summary, "cost_distribution", None)
        fields = {
            "total_flow": total_flow,
            "edge_flow": edge_flow,
            "residual_cap": residual_cap,
            "reachable": reachable,
            "min_cut": min_cut,
            "cost_distribution": cost_distribution,
        }
        sizes: dict[str, int] = {}
        counts: dict[str, int] = {}
        for name, obj in fields.items():
            sizes[name] = _deep_size(obj)
            if isinstance(obj, dict):
                counts[name] = len(obj)
            elif isinstance(obj, (list, set, tuple, frozenset)):
                counts[name] = len(obj)
            else:
                counts[name] = 1 if obj is not None else 0
        total_summary_size = _deep_size(summary)
        return sizes, counts, total_summary_size

    def fmt_mb(n: int) -> str:
        return f"{n / 1024 / 1024:.2f} MB"

    if args.pair_index >= 0:
        # Show specific pair detail
        ((src, dst), (_flow, summary)) = items[args.pair_index]
        print(f"Analyzing pair: {src}->{dst}")
        sizes, counts, total_summary_size = summarize_one(summary)
        print("\nFlowSummary memory breakdown:")
        for name in (
            "total_flow",
            "edge_flow",
            "residual_cap",
            "reachable",
            "min_cut",
            "cost_distribution",
        ):
            sz = sizes[name]
            cnt = counts[name]
            print(f"- {name:16s}: {fmt_mb(sz):>10s}  (items={cnt})")
        print(f"\nApprox FlowSummary total: {fmt_mb(total_summary_size)}")
        edge_flow = getattr(summary, "edge_flow", None)
        residual_cap = getattr(summary, "residual_cap", None)
        if isinstance(edge_flow, dict):
            try:
                uv_set = {
                    (k[0], k[1])
                    for k in edge_flow.keys()
                    if isinstance(k, (list, tuple)) and len(k) == 3
                }
                print(f"Distinct (u,v) in edge_flow: {len(uv_set)}")
            except Exception:
                pass
            try:
                nonzero = [
                    (k, v)
                    for k, v in edge_flow.items()
                    if isinstance(v, (int, float)) and v != 0
                ]
                zeros = len(edge_flow) - len(nonzero)
                print(
                    f"edge_flow entries: total={len(edge_flow)}, nonzero={len(nonzero)}, zero={zeros}"
                )
                for _i, (k, v) in enumerate(nonzero[:5]):
                    print(f"  edge_flow[{k}]={v}")
            except Exception:
                pass
        if isinstance(residual_cap, dict):
            try:
                saturated = [
                    (k, v)
                    for k, v in residual_cap.items()
                    if isinstance(v, (int, float)) and v <= 1e-12
                ]
                nonsat = len(residual_cap) - len(saturated)
                print(
                    f"residual_cap entries: total={len(residual_cap)}, saturated={len(saturated)}, non-saturated={nonsat}"
                )
                for _i, (k, v) in enumerate(saturated[:5]):
                    print(f"  residual_cap[{k}]={v}")
            except Exception:
                pass
        return 0

    # Scan all pairs and report aggregates and top contributors
    agg_sizes: dict[str, int] = {
        k: 0
        for k in (
            "total_flow",
            "edge_flow",
            "residual_cap",
            "reachable",
            "min_cut",
            "cost_distribution",
        )
    }
    agg_counts: dict[str, int] = {k: 0 for k in agg_sizes}
    totals: list[
        tuple[int, str, str, int, dict[str, int]]
    ] = []  # (total_size, src, dst, idx, sizes)
    for idx, ((src, dst), (_flow, summary)) in enumerate(items):
        sizes, counts, total_sz = summarize_one(summary)
        totals.append((total_sz, src, dst, idx, sizes))
        for k in agg_sizes:
            agg_sizes[k] += sizes[k]
            agg_counts[k] += counts[k]

    n = len(items)
    print(f"Scanned {n} flow pairs")
    print("Average per-pair memory by field:")
    for k in agg_sizes:
        avg = agg_sizes[k] // max(1, n)
        avg_cnt = agg_counts[k] // max(1, n)
        print(f"- {k:16s}: {fmt_mb(avg):>10s}  (avg items={avg_cnt})")

    totals.sort(reverse=True, key=lambda t: t[0])
    top = totals[:10]
    print("\nTop 10 heaviest pairs by FlowSummary size:")
    for total_sz, src, dst, idx, sizes in top:
        print(
            f"  [{idx:3d}] {src}->{dst}: {fmt_mb(total_sz)} | edge_flow={fmt_mb(sizes['edge_flow'])}, residual_cap={fmt_mb(sizes['residual_cap'])}, reachable={fmt_mb(sizes['reachable'])}, min_cut={fmt_mb(sizes['min_cut'])}, cost_dist={fmt_mb(sizes['cost_distribution'])}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
