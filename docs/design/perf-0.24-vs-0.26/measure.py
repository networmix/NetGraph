"""Time one scenario on the installed NetGraph, 0.24.1 or 0.26.x.

The phases are the boundaries of README.md: load, prepare (0.26 only), run, export
and cleanup. Peak memory is the process's maximum resident set size; both releases
run placement workers as threads of this process. The summary also gives the
export's SHA-256, which README.md states for the released 0.26.0.

    python measure.py SCENARIO.yml[.gz] RESULTS.json [--workers N] [--draws N]
        [--expect OTHER.json] [--reuse]
        [--probe NGPROBE.so [--discard] [--census] [--kernels]]

`--workers` and `--draws` override every placement step's workers and failure
draws; fewer draws give the reduced runs of README.md. The other options apply to
0.26 only and are diagnostics, not supported modes:

- `--expect` compares every decoded export field with another 0.26 export,
  except the four recorded build/runtime identity fields named in README.md.
- `--reuse` repeats each native action list on its retained programs, checks
  that the repeat delivers the same amounts, and times both calls.
- `--probe` loads the compiled `ngprobe` module. `--discard` drops each case's
  forwarding programs once the case is placed; `--census` sizes what the
  results own before that; `--kernels` reruns each placed result's exact
  admission and its forwarding with and without per-source attribution.
"""

import argparse
import gc
import gzip
import hashlib
import importlib.util
import json
import os
import resource
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes()).decode()
    return path.read_text()


def override(text: str, key: str, value: int) -> str:
    import yaml

    data = yaml.safe_load(text)
    for step in data["workflow"]:
        if step["type"] == "TrafficMatrixPlacement":
            step[key] = value
    return yaml.safe_dump(data, sort_keys=False)


def comparison_export(path: Path) -> tuple[dict, dict]:
    data = json.loads(path.read_text())
    metadata = data["metadata"]
    provenance = {
        key: metadata.pop(key)
        for key in (
            "netgraph_version",
            "core_version",
            "core_extension_sha256",
            "python_version",
        )
    }
    if not all(isinstance(value, str) for value in provenance.values()):
        raise ValueError("export build/runtime identity fields must be strings")
    return data, provenance


def peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("scenario", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--draws", type=int)
    parser.add_argument("--expect", type=Path)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--discard", action="store_true")
    parser.add_argument("--census", action="store_true")
    parser.add_argument("--kernels", action="store_true")
    args = parser.parse_args()
    if args.results.exists():
        parser.error(f"{args.results} exists; give a fresh path")

    release = version("ngraph")
    new = not release.startswith("0.24.")
    probes = args.discard or args.census or args.kernels
    if not new and (args.expect or args.reuse or args.probe or probes):
        # 0.24.1 exports carry per-run demand ids and timings, and their case order
        # varies with several workers.
        parser.error("--expect, --reuse and --probe apply to 0.26 only")
    if probes and not args.probe:
        parser.error("--discard, --census and --kernels need --probe")
    if args.probe:
        # The module reads the shipped extension's types and symbols.
        sys.setdlopenflags(os.RTLD_NOW | os.RTLD_GLOBAL)

    import ngraph
    from ngraph.scenario import Scenario

    text = read_text(args.scenario)
    if args.workers is not None:
        text = override(text, "workers" if new else "parallelism", args.workers)
    if args.draws is not None:
        text = override(text, "iterations", args.draws)

    census: dict[str, int] = defaultdict(int)
    kernels: dict[str, float] = defaultdict(float)
    reuse: dict[str, float] = defaultdict(float)
    discarded = 0
    probe: Any = None
    placement: Any = None
    core: Any = None
    if args.probe:
        spec = importlib.util.spec_from_file_location("ngprobe", args.probe)
        if spec is None or spec.loader is None:
            parser.error(f"cannot load {args.probe}")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
    if args.probe or args.reuse:
        import netgraph_core

        import ngraph.analysis.placement as placement_module

        placement = placement_module
        core = netgraph_core
    if args.probe:
        place_state = placement._place_state

        def place_and_probe(prepared, *a, **kw):
            nonlocal discarded
            state = place_state(prepared, *a, **kw)
            results = [row.result for row in state.rows]
            if args.census:
                for key, value in probe.census(results).items():
                    if not key.startswith("sizeof"):
                        census[key] += value
            if args.kernels:
                for result in results:
                    if result.delivered == 0:
                        kernels["zero_rows"] += 1
                        continue
                    k = probe.measure(prepared.topology.graph, result, result.requested)
                    group = "multi_source" if k["sources"] > 1 else "one_source"
                    kernels[f"{group}_rows"] += 1
                    kernels["lossless_s"] += k["lossless_s"]
                    kernels[f"{group}_aggregate_forward_s"] += k["aggregate_forward_s"]
                    kernels[f"{group}_attributed_forward_s"] += k[
                        "attributed_forward_s"
                    ]
                    kernels["attribution_entries"] += k["attribution_entries"]
                    kernels["max_search_probes"] = max(
                        kernels["max_search_probes"], k["search_probes"]
                    )
            if args.discard:
                probe.discard_programs(results)
                discarded += len(results)
            return state

        placement._place_state = place_and_probe
    if args.reuse:
        apply_actions = core.apply_actions

        def apply_twice(ledger, actions, *a, **kw):
            start = time.perf_counter()
            first = apply_actions(ledger, actions, *a, **kw)
            reuse["first_s"] += time.perf_counter() - start
            for action in actions:
                action.policy.remove()
            start = time.perf_counter()
            again = apply_actions(ledger, actions, *a, **kw)
            reuse["repeat_s"] += time.perf_counter() - start
            reuse["calls"] += 1
            for x, y in zip(first, again, strict=True):
                assert (x.requested, x.delivered) == (y.requested, y.delivered)
                assert [(s.source, s.delivered) for s in x.by_source] == [
                    (s.source, s.delivered) for s in y.by_source
                ]
            return first

        core.apply_actions = apply_twice

    phases: dict[str, float | None] = {}
    steps: list[tuple[str, float]] = []

    @contextmanager
    def hook(step):
        start = time.perf_counter()
        yield
        steps.append((step.name, time.perf_counter() - start))

    start = time.perf_counter()
    scenario: Any = Scenario.from_yaml(text)
    phases["load"] = time.perf_counter() - start
    del text

    result: Any
    start = time.perf_counter()
    if new:
        prepared = ngraph.prepare(scenario)
        phases["prepare"] = time.perf_counter() - start
        start = time.perf_counter()
        result = ngraph.run(prepared, step_hook=hook)
    else:
        prepared = None
        phases["prepare"] = None  # 0.24.1 prepares inside each step
        scenario.run(step_hook=hook)  # the 0.24.1 Scenario runs itself
        result = scenario.results
    phases["run"] = time.perf_counter() - start

    start = time.perf_counter()
    with args.results.open("x", encoding="utf-8") as stream:
        if new:
            ngraph.write_json(result, stream)
        else:
            stream.write(json.dumps(result.to_dict(), indent=2))
    phases["export"] = time.perf_counter() - start

    start = time.perf_counter()
    del result, prepared
    if not new:
        scenario.results = None
    del scenario
    gc.collect()
    phases["cleanup"] = time.perf_counter() - start

    engine = sum(phases[k] or 0.0 for k in ("prepare", "run", "export"))
    summary: dict[str, Any] = {
        "ngraph": release,
        "netgraph_core": version("netgraph-core"),
        "scenario": str(args.scenario),
        "workers": args.workers,
        "draws": args.draws,
        "phases_s": phases,
        "prepare_run_export_s": engine,
        "steps_s": steps,
        "peak_rss_gib": peak_rss_bytes() / 2**30,
        "export_sha256": hashlib.sha256(args.results.read_bytes()).hexdigest(),
    }
    if args.discard:
        summary["discarded_results"] = discarded
    if args.census:
        summary["census"] = dict(census)
    if args.kernels:
        summary["kernels"] = dict(kernels)
    if args.reuse:
        summary["reuse"] = dict(reuse)
    if args.expect:
        actual, actual_provenance = comparison_export(args.results)
        expected, expected_provenance = comparison_export(args.expect)
        summary["comparison_provenance"] = {
            "actual": actual_provenance,
            "expected": expected_provenance,
        }
        summary["equal_to_expected"] = actual == expected
    print(json.dumps(summary, indent=2))
    if args.expect and not summary["equal_to_expected"]:
        sys.exit(f"{args.results} differs from {args.expect}")


if __name__ == "__main__":
    main()
