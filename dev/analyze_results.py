"""Result analyzer for NetGraph scenarios.

Provides a CLI to summarize `results.json` and (optionally) validate against
scenario expectations. Focuses on common checks for `NetworkStats` and
`CapacityEnvelopeAnalysis` steps. Designed for fast local feedback when
iterating on scenarios.

Usage:
    python3 dev/analyze_results.py --results results.json \
        --scenario scenarios/backbone.yml --strict

Exit status is non-zero when `--strict` is passed and any validation fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class ValidationResult:
    """Aggregated validation outcome.

    Attributes:
        passed: Whether all checks passed.
        messages: Human-readable summary lines.
    """

    passed: bool
    messages: list[str]


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file into a dictionary.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dictionary.
    """

    return json.loads(path.read_text())


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file into a dictionary.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dictionary.
    """

    return yaml.safe_load(path.read_text())


def print_header(title: str) -> None:
    print("\n" + title)
    print("=" * len(title))


def summarize_workflow(results: dict[str, Any]) -> None:
    wf = results.get("workflow", {})
    if not isinstance(wf, dict) or not wf:
        print("❌ workflow metadata missing or empty")
        return
    print("✅ workflow metadata present")
    for i, (step_name, meta) in enumerate(
        sorted(wf.items(), key=lambda kv: kv[1].get("execution_order", 0)), start=1
    ):
        step_type = meta.get("step_type", "?")
        order = meta.get("execution_order", "?")
        print(f"  {i:2d}. {step_name} ({step_type}) [order={order}]")


def summarize_network_stats(results: dict[str, Any], step_name: str) -> None:
    stats = results.get(step_name)
    print(f"\nNetworkStats [{step_name}]")
    print("-" * 12)
    if not isinstance(stats, dict):
        print(f"❌ step '{step_name}' not found")
        return
    keys = sorted(stats.keys())
    print(f"✅ keys: {', '.join(keys)}")
    print(
        "  nodes=",
        stats.get("node_count"),
        "links=",
        stats.get("link_count"),
        "cap[min,max]=",
        stats.get("min_capacity"),
        stats.get("max_capacity"),
    )
    print(
        "  degree[mean,median]=",
        stats.get("mean_degree"),
        stats.get("median_degree"),
    )


def _extract_envelope_pairs(env: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for k in env.keys():
        if "->" not in k:
            continue
        src, dst = k.split("->", 1)
        pairs.add((src, dst))
    return pairs


def summarize_capacity_envelopes(
    results: dict[str, Any], step_name: str
) -> dict[str, Any]:
    print(f"\nCapacityEnvelopeAnalysis [{step_name}]")
    print("-" * 24)
    step = results.get(step_name)
    if not isinstance(step, dict):
        print(f"❌ step '{step_name}' not found")
        return {}

    env = step.get("capacity_envelopes", {})
    if not isinstance(env, dict) or not env:
        print("❌ capacity_envelopes missing or empty")
        return {}

    pairs = _extract_envelope_pairs(env)
    labels = set()
    for a, b in pairs:
        labels.add(a)
        labels.add(b)

    # Sample count distribution
    sample_counts = Counter()
    zero_max = 0
    for v in env.values():
        sample_counts[v.get("total_samples", 0)] += 1
        if float(v.get("max", 0)) == 0.0:
            zero_max += 1

    self_flows = sum(1 for (a, b) in pairs if a.split("/")[0] == b.split("/")[0])

    print(f"✅ envelopes: {len(env):,}")
    print(f"  unique labels: {len(labels):,}")
    print(f"  self flows: {self_flows:,}")
    print("  total_samples distribution:", dict(sorted(sample_counts.items())))
    print(f"  envelopes with max=0: {zero_max}")

    # Failure pattern results (if present)
    pat = step.get("failure_pattern_results")
    if isinstance(pat, dict):
        print(f"  failure_pattern_results: {len(pat)} keys")
        if "baseline" in pat:
            baseline_matrix = pat["baseline"].get("capacity_matrix", {})
            print(f"  baseline capacity_matrix size: {len(baseline_matrix)} entries")
    else:
        print("  failure_pattern_results: none")

    # Flow summary presence summary
    fs_present = 0
    for v in env.values():
        if isinstance(v, dict) and "flow_summary_stats" in v:
            fs_present += 1
    if fs_present:
        print(f"  flow_summary_stats present in {fs_present}/{len(env)} envelopes")

    return {
        "num_envelopes": len(env),
        "labels": labels,
        "self_flows": self_flows,
        "sample_counts": dict(sample_counts),
        "zero_max": zero_max,
        "has_patterns": isinstance(step.get("failure_pattern_results"), dict),
        "num_patterns": len(
            step.get("failure_pattern_results", {})
            if isinstance(step.get("failure_pattern_results"), dict)
            else {}
        ),
        "has_baseline_pattern": isinstance(step.get("failure_pattern_results"), dict)
        and ("baseline" in step.get("failure_pattern_results", {})),
        "baseline_matrix_size": (
            len(
                step.get("failure_pattern_results", {})
                .get("baseline", {})
                .get("capacity_matrix", {})
            )
            if isinstance(step.get("failure_pattern_results"), dict)
            else 0
        ),
    }


def validate_against_scenario(
    results: dict[str, Any], scenario: dict[str, Any]
) -> ValidationResult:
    """Validate key expectations derived from the scenario.

    Checks focus on the first `CapacityEnvelopeAnalysis` step found.
    """

    messages: list[str] = []
    passed = True

    wf = scenario.get("workflow", [])
    cea_cfg: Optional[dict[str, Any]] = None
    for step in wf:
        if (
            isinstance(step, dict)
            and step.get("step_type") == "CapacityEnvelopeAnalysis"
        ):
            cea_cfg = step
            break

    if not cea_cfg:
        return ValidationResult(
            True,
            [
                "No CapacityEnvelopeAnalysis step found in scenario; skipping validation.",
            ],
        )

    mode = str(cea_cfg.get("mode", "combine")).lower()
    iterations = int(cea_cfg.get("iterations", 1))
    baseline = bool(cea_cfg.get("baseline", False))
    store_patterns = bool(cea_cfg.get("store_failure_patterns", False))

    # Determine the step name from scenario config
    step_name = str(cea_cfg.get("name") or cea_cfg.get("step_type") or "").strip()
    if not step_name:
        return ValidationResult(False, ["CapacityEnvelopeAnalysis step has no name"])

    # Use computed summary from results for robust validation
    cea_summary = summarize_capacity_envelopes(results, step_name=step_name)
    if not cea_summary:
        return ValidationResult(False, ["capacity_envelopes missing in results"])

    num_env = int(cea_summary["num_envelopes"])
    labels = cea_summary["labels"]
    label_count = len(labels)

    if mode == "pairwise":
        expected_env = label_count * label_count
        if num_env != expected_env:
            passed = False
            messages.append(
                f"❌ pairwise envelope count mismatch: {num_env} != {expected_env}"
            )
        else:
            messages.append(f"✅ pairwise envelopes match: {num_env} == {expected_env}")
    else:
        messages.append("ℹ️ combine mode: envelope count depends on aggregation")

    # Sample counts should not exceed iterations; expect values <= iterations
    sc = cea_summary["sample_counts"]
    over = {k: v for k, v in sc.items() if isinstance(k, int) and k > iterations}
    if over:
        passed = False
        messages.append(f"❌ total_samples exceed iterations: {over}")
    else:
        messages.append(
            f"✅ total_samples within iterations (max={max(sc) if sc else 0},"
            f" iters={iterations})"
        )

    # Baseline expectations
    if baseline:
        if not cea_summary["has_baseline_pattern"]:
            passed = False
            messages.append("❌ baseline requested but missing in patterns")
        else:
            # Baseline matrix should include all flows observed
            if cea_summary["baseline_matrix_size"] != num_env:
                passed = False
                messages.append(
                    "❌ baseline capacity_matrix size does not match envelopes"
                )
            else:
                messages.append("✅ baseline pattern present with full matrix")
    else:
        messages.append("ℹ️ baseline not requested; no baseline pattern required")

    # Failure pattern storage expectation
    if store_patterns and not cea_summary["has_patterns"]:
        passed = False
        messages.append("❌ store_failure_patterns=True but none found")
    elif store_patterns:
        messages.append(
            f"✅ failure patterns present: {cea_summary['num_patterns']} keys"
        )

    # Flow summary validation (if present) for CapacityEnvelopeAnalysis
    flow_summary_present = False
    # Look up the specific step by name
    step_data = results.get(step_name, {}) if isinstance(step_name, str) else {}
    envelopes = (
        step_data.get("capacity_envelopes", {}) if isinstance(step_data, dict) else {}
    )
    if isinstance(envelopes, dict) and envelopes:
        for v in envelopes.values():
            if isinstance(v, dict) and "flow_summary_stats" in v:
                flow_summary_present = True
                break

    if flow_summary_present:
        fs_ok, fs_msgs = _validate_flow_summaries(envelopes, iterations)
        messages.extend(fs_msgs)
        if not fs_ok:
            passed = False
    else:
        messages.append("ℹ️ flow summaries not present; skipping checks")

    return ValidationResult(passed, messages)


def _extract_expected_steps(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    wf = scenario.get("workflow", [])
    steps: list[dict[str, Any]] = []
    for step in wf:
        if isinstance(step, dict) and step.get("step_type"):
            steps.append(step)
    return steps


def _result_step_names(results: dict[str, Any]) -> set[str]:
    # Everything except the reserved 'workflow' key is a step root
    return {k for k in results.keys() if k != "workflow"}


def validate_all_steps(results: dict[str, Any], scenario: dict[str, Any]) -> bool:
    """Validate all workflow steps discovered in the scenario against results.

    - Maps expected step names from scenario to results by exact name.
    - For CapacityEnvelopeAnalysis: run capacity validation using the discovered name.
    - For TrafficMatrixPlacementAnalysis: run placement validation using the discovered name.
    - Reports missing/extra steps.
    Returns True when all validations pass and no missing steps.
    """

    expected_steps = _extract_expected_steps(scenario)
    result_step_roots = _result_step_names(results)

    ok = True

    # Map expected names to types
    def _safe_name(step: dict[str, Any]) -> str:
        n = step.get("name")
        if isinstance(n, str) and n:
            return n
        st = step.get("step_type")
        return str(st) if isinstance(st, str) else ""

    name_to_type = {
        _safe_name(step): str(step.get("step_type") or "") for step in expected_steps
    }

    # Check presence
    missing = [n for n in name_to_type.keys() if n and n not in result_step_roots]
    extra = [n for n in result_step_roots if n not in name_to_type and n != "workflow"]

    if missing:
        print(f"❌ Missing results for steps: {', '.join(missing)}")
        ok = False
    if extra:
        print(f"ℹ️ Extra result steps present: {', '.join(extra)}")

    # Run per-type validations with discovered step names
    for step in expected_steps:
        step_type = step.get("step_type")
        step_name = step.get("name") or step_type

        if step_type == "CapacityEnvelopeAnalysis":
            # Temporarily call existing validator but override display summary to use this name
            vr = validate_against_scenario(results, {"workflow": [step]})
            for msg in vr.messages:
                print(msg)
            ok = ok and vr.passed
        elif step_type == "TrafficMatrixPlacementAnalysis":
            vr = validate_tm_placement(results, {"workflow": [step]})
            for msg in vr.messages:
                print(msg)
            ok = ok and vr.passed
        else:
            # For unknown step types, at least assert presence
            if step_name in result_step_roots:
                print(f"✅ Found results for step '{step_name}' ({step_type})")
            else:
                print(f"❌ Missing results for step '{step_name}' ({step_type})")
                ok = False

    return ok


def summarize_tm_placement(results: dict[str, Any], step_name: str) -> dict[str, Any]:
    print(f"\nTrafficMatrixPlacementAnalysis [{step_name}]")
    print("-" * 30)
    step = results.get(step_name)
    if not isinstance(step, dict):
        print(f"❌ step '{step_name}' not found")
        return {}

    env = step.get("placement_envelopes", {})
    if not isinstance(env, dict) or not env:
        print("❌ placement_envelopes missing or empty")
        return {}

    meta = step.get("metadata", {}) if isinstance(step, dict) else {}
    iters = int(meta.get("iterations", 0))
    baseline = bool(meta.get("baseline", False))
    parallelism = meta.get("parallelism")

    # Envelope counts and labels
    labels = set()
    sample_counts = Counter()
    fs_present = 0
    edge_freq_total = 0
    cost_levels_total = 0
    cost_level_issues = 0
    for v in env.values():
        labels.add(v.get("src", ""))
        labels.add(v.get("dst", ""))
        sample_counts[int(v.get("total_samples", 0))] += 1
        if isinstance(v, dict) and "flow_summary_stats" in v:
            fs_present += 1
            fs = v.get("flow_summary_stats", {}) or {}
            cds = fs.get("cost_distribution_stats", {}) if isinstance(fs, dict) else {}
            cost_levels_total += len(cds) if isinstance(cds, dict) else 0
            # Validate cost-level frequency sums
            if isinstance(cds, dict):
                for _cost, stats in cds.items():
                    if not isinstance(stats, dict):
                        continue
                    try:
                        freq_sum = sum(
                            int(x)
                            for x in (stats.get("frequencies", {}) or {}).values()
                        )
                    except Exception:
                        freq_sum = -1
                    if int(stats.get("total_samples", 0)) != freq_sum:
                        cost_level_issues += 1
            ef = fs.get("edge_usage_frequencies", {}) if isinstance(fs, dict) else {}
            edge_freq_total += len(ef) if isinstance(ef, dict) else 0

    print(f"✅ envelopes: {len(env):,}")
    print(f"  unique labels: {len(labels):,}")
    print(f"  total_samples distribution: {dict(sorted(sample_counts.items()))}")
    print(f"  flow_summary_stats present in {fs_present}/{len(env)} envelopes")
    if fs_present:
        print(
            f"  cost levels: {cost_levels_total}, edge usage entries: {edge_freq_total}"
        )
        if cost_level_issues:
            print(f"  ⚠️ cost-level frequency mismatches: {cost_level_issues}")
    print(
        f"  metadata: iterations={iters}, baseline={baseline}, parallelism={parallelism}"
    )

    return {
        "num_envelopes": len(env),
        "label_count": len(labels),
        "sample_counts": dict(sample_counts),
        "iters": iters,
        "baseline": baseline,
        "parallelism": parallelism,
        "fs_present": fs_present,
        "cost_levels_total": cost_levels_total,
        "edge_freq_total": edge_freq_total,
        "cost_level_issues": cost_level_issues,
    }


def validate_tm_placement(
    results: dict[str, Any], scenario: dict[str, Any]
) -> ValidationResult:
    messages: list[str] = []
    passed = True

    # Locate the placement step config
    wf = scenario.get("workflow", [])
    tm_cfg: Optional[dict[str, Any]] = None
    for step in wf:
        if (
            isinstance(step, dict)
            and step.get("step_type") == "TrafficMatrixPlacementAnalysis"
        ):
            tm_cfg = step
            break

    if not tm_cfg:
        return ValidationResult(
            True, ["No TrafficMatrixPlacementAnalysis in scenario; skipping"]
        )

    # Determine step name and summarize results
    step_name = str(tm_cfg.get("name") or tm_cfg.get("step_type") or "").strip()
    if not step_name:
        return ValidationResult(
            False, ["TrafficMatrixPlacementAnalysis step has no name"]
        )

    tm_sum = summarize_tm_placement(results, step_name)
    if not tm_sum:
        return ValidationResult(False, ["placement_envelopes missing in results"])

    # Expected iterations
    iters_expected = int(tm_cfg.get("iterations", 1))
    sc = tm_sum["sample_counts"]
    over = {k: v for k, v in sc.items() if isinstance(k, int) and k > iters_expected}
    if over:
        passed = False
        messages.append(f"❌ placement total_samples exceed iterations: {over}")
    elif set(sc.keys()) != {iters_expected}:
        passed = False
        messages.append(
            f"❌ placement total_samples not constant per envelope: {dict(sorted(sc.items()))}"
        )
    else:
        messages.append(
            f"✅ placement total_samples match iterations ({iters_expected}) for all envelopes"
        )

    # Informational: compare number of envelopes to potential cross pairs derived
    # from labels present in placement envelopes themselves
    # (No failure if they differ; TMs may cover subsets.)
    step_data = results.get(step_name, {}) if isinstance(step_name, str) else {}
    env = (
        step_data.get("placement_envelopes", {}) if isinstance(step_data, dict) else {}
    )
    labels: set[str] = set()
    for v in env.values():
        if isinstance(v, dict):
            labels.add(str(v.get("src", "")))
            labels.add(str(v.get("dst", "")))
    labels.discard("")
    expected_pairs = len(labels) * (len(labels) - 1)
    if expected_pairs:
        if tm_sum["num_envelopes"] != expected_pairs:
            messages.append(
                f"ℹ️ placement envelopes {tm_sum['num_envelopes']} vs potential pairs {expected_pairs}"
            )
        else:
            messages.append(
                f"✅ placement envelopes match potential cross pairs ({expected_pairs})"
            )

    # Failure pattern storage expectation
    store_patterns = bool(tm_cfg.get("store_failure_patterns", False))
    step_name = tm_cfg.get("name") or "tm_placement"
    step_data = results.get(step_name, {}) if isinstance(step_name, str) else {}
    has_patterns = isinstance(step_data.get("failure_pattern_results"), dict)
    if store_patterns and not has_patterns:
        passed = False
        messages.append("❌ placement store_failure_patterns=True but none found")
    elif store_patterns:
        num_pats = len(step_data.get("failure_pattern_results", {}))
        messages.append(f"✅ placement failure patterns present: {num_pats}")
    else:
        messages.append("ℹ️ placement failure patterns not requested")

    # Flow details expectation
    include_flow_details = bool(tm_cfg.get("include_flow_details", False))
    if include_flow_details:
        if tm_sum["fs_present"] != tm_sum["num_envelopes"]:
            passed = False
            messages.append(
                f"❌ flow_summary_stats missing for some envelopes: {tm_sum['fs_present']}/{tm_sum['num_envelopes']}"
            )
        else:
            messages.append("✅ flow_summary_stats present for all placement envelopes")
        if tm_sum["cost_level_issues"]:
            passed = False
            messages.append(
                f"❌ cost-level frequency mismatches: {tm_sum['cost_level_issues']}"
            )
    else:
        if tm_sum["fs_present"]:
            messages.append(
                f"⚠️ flow_summary_stats present despite include_flow_details=False ({tm_sum['fs_present']})"
            )

    return ValidationResult(passed, messages)


def _validate_flow_summaries(
    envelopes: dict[str, Any], iterations: int
) -> tuple[bool, list[str]]:
    """Validate flow_summary_stats for capacity envelopes.

    Validations:
    - total_flow_summaries equals envelope total_samples
    - Sum of envelope frequency counts equals envelope total_samples
    - For zero-capacity envelopes (max == 0), cost/min-cut stats are empty
    - For each cost level: 0 <= min <= mean <= max <= envelope max
    - For each cost level: total_samples equals sum of its frequency counts
    """

    ok = True
    msgs: list[str] = []

    total = len(envelopes)
    missing = 0
    ts_mismatch = 0
    freq_mismatch = 0
    zero_with_stats = 0
    bad_cost_stats = 0
    checked_cost_levels = 0

    for env in envelopes.values():
        if not isinstance(env, dict):
            continue
        fs = env.get("flow_summary_stats")
        if fs is None:
            missing += 1
            continue

        total_samples = int(env.get("total_samples", 0))

        # Capacity frequency sum must match total_samples
        freqs = env.get("frequencies", {}) or {}
        if isinstance(freqs, dict):
            try:
                freq_sum = sum(int(v) for v in freqs.values())
            except Exception:
                freq_sum = -1
        else:
            freq_sum = -1
        if freq_sum != total_samples:
            freq_mismatch += 1

        # Flow summary totals must match total_samples
        tfs = int(fs.get("total_flow_summaries", 0)) if isinstance(fs, dict) else 0
        if tfs != total_samples:
            ts_mismatch += 1

        # Zero-capacity flows should have empty stats
        env_max = float(env.get("max", 0.0))
        cds = fs.get("cost_distribution_stats", {}) if isinstance(fs, dict) else {}
        mcf = fs.get("min_cut_frequencies", {}) if isinstance(fs, dict) else {}
        if env_max == 0.0 and (cds or mcf):
            zero_with_stats += 1

        # Validate per-cost statistics
        if isinstance(cds, dict):
            for _cost, stats in cds.items():
                if not isinstance(stats, dict):
                    continue
                mn = float(stats.get("min", 0.0))
                mx = float(stats.get("max", 0.0))
                mean = float(stats.get("mean", 0.0))
                ts = int(stats.get("total_samples", 0))
                freqs2 = stats.get("frequencies", {}) or {}
                try:
                    freq_sum2 = sum(int(v) for v in freqs2.values())
                except Exception:
                    freq_sum2 = -1
                checked_cost_levels += 1
                if not (0.0 <= mn <= mean <= mx <= max(env_max, 0.0)):
                    bad_cost_stats += 1
                if ts != freq_sum2:
                    bad_cost_stats += 1

    if missing:
        msgs.append(f"❌ envelopes missing flow_summary_stats: {missing}")
        ok = False
    else:
        msgs.append(f"✅ flow_summary_stats present for {total} envelopes")

    if ts_mismatch:
        msgs.append(f"❌ total_flow_summaries mismatch in {ts_mismatch} envelopes")
        ok = False
    else:
        msgs.append("✅ total_flow_summaries match envelope total_samples")

    if freq_mismatch:
        msgs.append(f"❌ frequency sum != total_samples in {freq_mismatch} envelopes")
        ok = False
    else:
        msgs.append("✅ capacity frequency sums match total_samples")

    if zero_with_stats:
        msgs.append(
            f"⚠️ zero-capacity envelopes with non-empty summary: {zero_with_stats}"
        )
    else:
        msgs.append("✅ zero-capacity envelopes have empty flow summaries")

    if checked_cost_levels == 0:
        msgs.append("ℹ️ no cost distribution levels to validate")
    elif bad_cost_stats:
        msgs.append(
            f"❌ invalid cost-level stats detected: {bad_cost_stats} issues across "
            f"{checked_cost_levels} levels"
        )
        ok = False
    else:
        msgs.append(
            f"✅ validated {checked_cost_levels} cost distribution levels without issues"
        )

    return ok, msgs


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="analyze_results",
        description=(
            "Summarize results.json and optionally validate against scenario YAML"
        ),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results.json"),
        help="Path to results JSON (default: results.json)",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        help="Optional path to scenario YAML for validation",
    )
    # Always strict: non-zero exit when validation fails

    args = parser.parse_args()

    if not args.results.exists():
        print(f"❌ results not found: {args.results}")
        return 2

    results = load_json(args.results)

    print_header("WORKFLOW")
    summarize_workflow(results)

    # Helper to get step names by type from workflow metadata
    def _step_names_by_type(_results: dict[str, Any], _type: str) -> list[str]:
        wf = _results.get("workflow", {})
        if not isinstance(wf, dict):
            return []
        return [
            name
            for name, meta in sorted(
                wf.items(), key=lambda kv: kv[1].get("execution_order", 0)
            )
            if str(meta.get("step_type", "")) == _type
        ]

    if args.scenario:
        if not args.scenario.exists():
            print(f"❌ scenario not found: {args.scenario}")
            return 2
        scenario = load_yaml(args.scenario)
        print_header("VALIDATION")
        overall_ok = validate_all_steps(results, scenario)

        # Summarize non-validated steps (e.g., NetworkStats)
        for ns_name in _step_names_by_type(results, "NetworkStats"):
            summarize_network_stats(results, ns_name)

        if not overall_ok:
            return 1
        return 0

    # No scenario: summarize all recognized steps based on workflow metadata
    for ns_name in _step_names_by_type(results, "NetworkStats"):
        summarize_network_stats(results, ns_name)
    for ce_name in _step_names_by_type(results, "CapacityEnvelopeAnalysis"):
        summarize_capacity_envelopes(results, ce_name)
    for tm_name in _step_names_by_type(results, "TrafficMatrixPlacementAnalysis"):
        summarize_tm_placement(results, tm_name)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
