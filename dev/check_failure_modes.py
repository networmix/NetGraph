"""Failure mode distribution checker.

Reads a results.json produced by the workflow and a scenario YAML defining
the failure policy. Computes observed frequencies of failure pattern types and
compares them to expected weights from the configured modes.

Usage:
    python3 dev/check_failure_modes.py \
        --results /path/to/results.json \
        --scenario /path/to/scenario.yml \
        [--step capacity_envelope]  # defaults to all known steps

Assumptions:
- results.json uses the standard layout produced by the CLI run command.
- Each step stores failure patterns under the key "failure_pattern_results".
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import yaml

StepName = str


@dataclass
class Distribution:
    """Observed and expected distribution for one step.

    Attributes:
        total_iterations: Total iterations recorded (including baseline if present).
        baseline_count: Number of baseline iterations.
        non_baseline_count: Number of non-baseline iterations.
        counts: Observed counts keyed by class label.
        percents: Observed percentages keyed by class label over non-baseline.
        expected: Expected percentages keyed by class label over non-baseline.
    """

    total_iterations: int
    baseline_count: int
    non_baseline_count: int
    counts: dict[str, int]
    percents: dict[str, float]
    expected: dict[str, float]


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed object.
    """

    return json.loads(path.read_text())


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed object.
    """

    return yaml.safe_load(path.read_text())


def _classify_pattern(
    excluded_nodes: Iterable[str], excluded_links: Iterable[str]
) -> str:
    """Classify a failure pattern by excluded entity counts.

    Returns:
        One of: "baseline" (handled by caller), "node_only", "link_only",
        or "rg_related" (risk-group related or combined modes).
    """

    n_nodes = sum(1 for _ in excluded_nodes)
    n_links = sum(1 for _ in excluded_links)
    # Baseline is handled by caller; if both zero, caller maps to baseline
    if n_nodes == 1 and n_links == 0:
        return "node_only"
    if n_nodes == 0 and n_links == 1:
        return "link_only"
    return "rg_related"


def _extract_failure_patterns(step_obj: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract failure_pattern_results mapping from a step object if present."""

    fpr = step_obj.get("failure_pattern_results")
    if isinstance(fpr, dict):
        return fpr  # already expanded format
    # Backward-compat or different structure: try alternate keys
    alt = step_obj.get("failure_patterns")
    return alt if isinstance(alt, dict) else {}


def _expected_from_policy(
    scenario: dict[str, Any], policy_name: str
) -> dict[str, float]:
    """Compute expected class percentages from failure policy mode weights.

    Modes are mapped to classes by their rule scopes:
    - Only node rules  -> node_only
    - Only link rules  -> link_only
    - Any mode containing risk_group rules (with or without node rules)
      contributes to rg_related

    Args:
        scenario: Parsed scenario YAML dict.
        policy_name: Failure policy name to analyze.

    Returns:
        Normalized percentages over non-baseline iterations for keys:
        {"node_only", "link_only", "rg_related"}.
    """

    fps = scenario.get("failure_policy_set", {})
    policy = fps.get(policy_name, {}) if isinstance(fps, dict) else {}
    modes = policy.get("modes", []) if isinstance(policy, dict) else []

    node_w = 0.0
    link_w = 0.0
    rg_w = 0.0

    for mode in modes:
        if not isinstance(mode, dict):
            continue
        w = float(mode.get("weight", 0.0) or 0.0)
        rules = mode.get("rules", [])
        scopes = {r.get("entity_scope") for r in rules if isinstance(r, dict)}
        if scopes == {"node"}:
            node_w += w
        elif scopes == {"link"}:
            link_w += w
        elif "risk_group" in scopes:
            rg_w += w
        else:
            # Any other combination (should not occur in the provided scenario)
            rg_w += w

    total = node_w + link_w + rg_w
    if total <= 0.0:
        return {"node_only": 0.0, "link_only": 0.0, "rg_related": 0.0}

    return {
        "node_only": node_w / total * 100.0,
        "link_only": link_w / total * 100.0,
        "rg_related": rg_w / total * 100.0,
    }


def analyze_step(
    results_root: dict[str, Any],
    step_name: StepName,
    expected: dict[str, float],
) -> Optional[Distribution]:
    """Analyze failure patterns for one step.

    Args:
        results_root: Full results.json dict.
        step_name: Step key in results.
        expected: Expected percent distribution keyed by class label.

    Returns:
        Distribution or None if step missing or no patterns.
    """

    step_obj = results_root.get(step_name)
    if not isinstance(step_obj, dict):
        return None

    fpr = _extract_failure_patterns(step_obj)
    if not fpr:
        return None

    total_iterations = 0
    baseline_count = 0
    counts: Dict[str, int] = {"node_only": 0, "link_only": 0, "rg_related": 0}

    for key, pat in fpr.items():
        if not isinstance(pat, dict):
            continue
        count = int(pat.get("count", 0))
        is_baseline = bool(pat.get("is_baseline", key == "baseline"))
        total_iterations += count
        if is_baseline:
            baseline_count += count
            continue

        ex_nodes = pat.get("excluded_nodes", []) or []
        ex_links = pat.get("excluded_links", []) or []
        label = _classify_pattern(ex_nodes, ex_links)
        counts[label] = counts.get(label, 0) + count

    non_baseline = max(0, total_iterations - baseline_count)
    percents = (
        {k: (v / non_baseline * 100.0) for k, v in counts.items()}
        if non_baseline
        else {}
    )

    return Distribution(
        total_iterations=total_iterations,
        baseline_count=baseline_count,
        non_baseline_count=non_baseline,
        counts=counts,
        percents=percents,
        expected=expected,
    )


def _print_distribution(step_name: str, dist: Distribution) -> None:
    print(f"\nStep: {step_name}")
    print("-" * (len(step_name) + 6))
    print(
        f"iterations={dist.total_iterations:,} baseline={dist.baseline_count:,} non_baseline={dist.non_baseline_count:,}"
    )
    # Order for display
    for label in ("node_only", "link_only", "rg_related"):
        c = dist.counts.get(label, 0)
        p = dist.percents.get(label, 0.0)
        e = dist.expected.get(label, 0.0)
        delta = p - e
        print(
            f"  {label:11s}: {c:6d}  {p:6.2f}%  (expected {e:6.2f}%, delta {delta:+6.2f}pp)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check failure mode distributions")
    parser.add_argument(
        "--results",
        type=Path,
        required=True,
        help="Path to results.json",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Path to scenario YAML",
    )
    parser.add_argument(
        "--policy",
        type=str,
        default="mc_baseline",
        help="Failure policy name (default: mc_baseline)",
    )
    parser.add_argument(
        "--step",
        type=str,
        choices=["capacity_envelope", "tm_placement"],
        help="Optional specific step to analyze (default: both if present)",
    )

    args = parser.parse_args()

    results = load_json(args.results)
    scenario = load_yaml(args.scenario)

    expected = _expected_from_policy(scenario, args.policy)

    steps: Tuple[StepName, ...]
    if args.step:
        steps = (args.step,)
    else:
        # Analyze any known steps we find
        candidates = ("capacity_envelope", "tm_placement")
        steps = tuple(s for s in candidates if isinstance(results.get(s), dict))

    if not steps:
        print("No recognized analysis steps found in results for this checker.")
        return 1

    print("Expected distribution (non-baseline):")
    for k in ("node_only", "link_only", "rg_related"):
        print(f"  {k:11s}: {expected.get(k, 0.0):6.2f}%")

    for step in steps:
        dist = analyze_step(results, step, expected)
        if dist is None:
            print(f"\nStep: {step}\n------\n(no failure_pattern_results present)")
            continue
        _print_distribution(step, dist)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
