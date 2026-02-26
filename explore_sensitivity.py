#!/usr/bin/env python3
"""Sensitivity analysis exploration script for NetGraph.

Exercises sensitivity analysis at three levels of abstraction:
1. Low-level: AnalysisContext.sensitivity() on a simple network
2. Mid-level: FailureManager.run_sensitivity_monte_carlo() with failure scenarios
3. High-level: YAML scenario with Sensitivity workflow step via CLI
4. NSFNET: Real-world topology sensitivity analysis
"""

from __future__ import annotations

import textwrap
import time

from ngraph.analysis.context import Mode, analyze
from ngraph.analysis.failure_manager import FailureManager
from ngraph.model.failure.parser import build_failure_policy_set
from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario
from ngraph.types.base import FlowPlacement
from ngraph.utils.seed_manager import SeedManager

# ── Helper ───────────────────────────────────────────────────────────────


def build_network(nodes: list[str], edges: list[tuple[str, str, float, int]]) -> Network:
    """Build a Network from node names and (src, dst, capacity, cost) tuples."""
    net = Network()
    for name in nodes:
        net.add_node(Node(name=name))
    for src, dst, cap, cost in edges:
        net.add_link(Link(source=src, target=dst, capacity=cap, cost=cost))
    return net


# ── 1. Low-level: AnalysisContext.sensitivity() ──────────────────────────

print("=" * 72)
print("1. LOW-LEVEL: AnalysisContext.sensitivity()")
print("=" * 72)

# Build a small 4-node diamond network:
#       A
#      / \
#    10   5     (capacity)
#    /     \
#   B       C
#    \     /
#     8   3
#      \ /
#       D
net = build_network(
    ["A", "B", "C", "D"],
    [("A", "B", 10.0, 1), ("A", "C", 5.0, 1),
     ("B", "D", 8.0, 1), ("C", "D", 3.0, 1)],
)

print(f"\nNetwork: diamond (4 nodes)")
print(f"  Nodes: {list(net.nodes.keys())}")
print(f"  Links: {len(net.links)} links")
for lid, link in net.links.items():
    print(f"    {lid}: {link.source} -> {link.target} "
          f"(cap={link.capacity}, cost={link.cost})")

# Run max-flow from A to D
ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
flow = ctx.max_flow()
print(f"\n  Max flow A->D: {flow}")

# Run sensitivity analysis (combine mode)
sensitivity = ctx.sensitivity()
print(f"\n  Sensitivity (critical edges):")
for (src, dst), edge_impacts in sensitivity.items():
    print(f"    Flow {src} -> {dst}:")
    if not edge_impacts:
        print("      (no critical edges found)")
    for edge_key, reduction in sorted(edge_impacts.items(), key=lambda x: -x[1]):
        print(f"      {edge_key}: flow reduction = {reduction:.1f}")

# Also try pairwise mode
print("\n  --- Pairwise mode ---")
ctx2 = analyze(net, source="^[AB]$", sink="^[CD]$", mode=Mode.PAIRWISE)
flow2 = ctx2.max_flow()
print(f"  Max flow (pairwise): {flow2}")
sens2 = ctx2.sensitivity()
for (src, dst), edge_impacts in sens2.items():
    print(f"    Flow {src} -> {dst}:")
    if not edge_impacts:
        print("      (no critical edges)")
        continue
    for edge_key, reduction in sorted(edge_impacts.items(), key=lambda x: -x[1]):
        print(f"      {edge_key}: -{reduction:.1f}")


# ── 2. Mid-level: FailureManager.run_sensitivity_monte_carlo() ──────────

print("\n" + "=" * 72)
print("2. MID-LEVEL: FailureManager.run_sensitivity_monte_carlo()")
print("=" * 72)

# Build a 6-node ring network for richer failure analysis
#   N1 -- N2 -- N3
#   |           |
#   N6 -- N5 -- N4
ring = build_network(
    [f"N{i}" for i in range(1, 7)],
    [(f"N{i}", f"N{i%6+1}", 10.0, 1) for i in range(1, 7)],
)

print(f"\nNetwork: 6-node ring")

# Build a failure policy: fail 1 random link
failure_config = {
    "single_link": {
        "modes": [{
            "weight": 1.0,
            "rules": [{"scope": "link", "mode": "choice", "count": 1}]
        }]
    }
}
seed_mgr = SeedManager(42)
fps = build_failure_policy_set(
    failure_config,
    derive_seed=lambda n: seed_mgr.derive_seed("failure_policy", n),
)

# Run Monte Carlo sensitivity analysis
fm = FailureManager(
    network=ring,
    failure_policy_set=fps,
    policy_name="single_link",
)

t0 = time.perf_counter()
results = fm.run_sensitivity_monte_carlo(
    source="^N1$",
    target="^N4$",
    mode="combine",
    iterations=50,
    parallelism=1,
    shortest_path=False,
    flow_placement=FlowPlacement.PROPORTIONAL,
    seed=42,
)
elapsed = time.perf_counter() - t0

print(f"  Iterations: {results['metadata']['iterations']}")
print(f"  Unique failure patterns: {results['metadata']['unique_patterns']}")
print(f"  Execution time: {elapsed:.3f}s")

# Print baseline
baseline = results["baseline"]
print(f"\n  Baseline (no failures):")
for flow_entry in baseline.flows:
    print(f"    {flow_entry.source} -> {flow_entry.destination}: "
          f"flow={flow_entry.placed:.1f}")
    sens_data = flow_entry.data.get("sensitivity", {})
    for edge, reduction in sorted(sens_data.items(), key=lambda x: -x[1]):
        print(f"      {edge}: -{reduction:.1f}")

# Print component scores (aggregated statistics)
print(f"\n  Component Scores (aggregated across failure iterations):")
comp_scores = results["component_scores"]
for flow_key, components in comp_scores.items():
    print(f"    Flow: {flow_key}")
    sorted_components = sorted(
        components.items(), key=lambda x: -x[1].get("mean", 0)
    )
    for comp_name, stats in sorted_components[:10]:
        print(f"      {comp_name}: mean={stats['mean']:.2f}, "
              f"max={stats['max']:.2f}, min={stats['min']:.2f}, "
              f"count={stats['count']}")


# ── 3. High-level: YAML Scenario with Sensitivity workflow step ──────────

print("\n" + "=" * 72)
print("3. HIGH-LEVEL: YAML Scenario with Sensitivity workflow step")
print("=" * 72)

yaml_str = textwrap.dedent("""\
seed: 42
network:
  nodes:
    DC1:
      attrs:
        site_type: datacenter
    DC2:
      attrs:
        site_type: datacenter
    Core1:
      attrs:
        site_type: core
    Core2:
      attrs:
        site_type: core
    Edge1:
      attrs:
        site_type: edge
    Edge2:
      attrs:
        site_type: edge
  links:
    - source: DC1
      target: Core1
      capacity: 100.0
      cost: 1
    - source: DC1
      target: Core2
      capacity: 80.0
      cost: 2
    - source: DC2
      target: Core1
      capacity: 60.0
      cost: 2
    - source: DC2
      target: Core2
      capacity: 100.0
      cost: 1
    - source: Core1
      target: Edge1
      capacity: 50.0
      cost: 1
    - source: Core1
      target: Edge2
      capacity: 40.0
      cost: 2
    - source: Core2
      target: Edge1
      capacity: 30.0
      cost: 2
    - source: Core2
      target: Edge2
      capacity: 70.0
      cost: 1
failures:
  random_link:
    modes:
      - weight: 1.0
        rules:
          - scope: link
            mode: choice
            count: 1
workflow:
  - type: Sensitivity
    name: bottleneck_analysis
    source: "^DC.*"
    target: "^Edge.*"
    mode: combine
    failure_policy: random_link
    iterations: 100
    parallelism: 1
    shortest_path: false
    flow_placement: PROPORTIONAL
    seed: 42
    store_failure_patterns: false
""")

scenario = Scenario.from_yaml(yaml_str)
print(f"\nScenario loaded:")
print(f"  Nodes: {list(scenario.network.nodes.keys())}")
print(f"  Links: {len(scenario.network.links)}")
print(f"  Workflow steps: {len(scenario.workflow)}")
print(f"  Failure policies: {list(scenario.failure_policy_set.policies.keys())}")

t0 = time.perf_counter()
scenario.run()
elapsed = time.perf_counter() - t0
print(f"\n  Scenario completed in {elapsed:.3f}s")

# Inspect results (use get_step for post-run access)
step_results = scenario.results.get_step("bottleneck_analysis")
data = step_results.get("data", {})
metadata = step_results.get("metadata", {})

print(f"\n  Metadata:")
print(f"    Iterations: {metadata.get('iterations')}")
print(f"    Unique patterns: {metadata.get('unique_patterns')}")

print(f"\n  Baseline:")
baseline_data = data.get("baseline", {})
if baseline_data:
    for flow in baseline_data.get("flows", []):
        src = flow.get("source", "?")
        dst = flow.get("destination", "?")
        placed = flow.get("placed", 0)
        sens = flow.get("data", {}).get("sensitivity", {})
        print(f"    {src} -> {dst}: flow={placed:.1f}")
        for edge, reduction in sorted(sens.items(), key=lambda x: -x[1])[:5]:
            print(f"      {edge}: -{reduction:.1f}")

print(f"\n  Component Scores (top bottlenecks):")
comp_scores = data.get("component_scores", {})
for flow_key, components in comp_scores.items():
    print(f"    Flow: {flow_key}")
    sorted_comps = sorted(
        components.items(), key=lambda x: -x[1].get("mean", 0)
    )
    for comp_name, stats in sorted_comps[:8]:
        print(f"      {comp_name}: mean={stats['mean']:.2f}, "
              f"max={stats['max']:.2f}, count={stats['count']}")

print(f"\n  Flow results (unique failure patterns): {len(data.get('flow_results', []))}")


# ── 4. NSFNET: Real-world topology ──────────────────────────────────────

print("\n" + "=" * 72)
print("4. NSFNET: Sensitivity on a real-world topology")
print("=" * 72)

from pathlib import Path

nsfnet_path = Path("scenarios/nsfnet.yaml")
nsfnet_yaml = nsfnet_path.read_text()

# Replace the workflow section with a Sensitivity step
parts = nsfnet_yaml.split("workflow:")
nsfnet_sensitivity_yaml = parts[0] + textwrap.dedent("""\
workflow:
  - type: Sensitivity
    name: nsfnet_sensitivity
    source: "^NewYork$"
    target: "^PaloAlto$"
    mode: combine
    failure_policy: single_link_failure
    iterations: 20
    parallelism: 1
    shortest_path: false
    flow_placement: PROPORTIONAL
    seed: 42
""")

nsfnet_scenario = Scenario.from_yaml(nsfnet_sensitivity_yaml)
print(f"\nNSFNET Scenario:")
print(f"  Nodes: {len(nsfnet_scenario.network.nodes)}")
print(f"  Links: {len(nsfnet_scenario.network.links)}")

t0 = time.perf_counter()
nsfnet_scenario.run()
elapsed = time.perf_counter() - t0
print(f"  Completed in {elapsed:.3f}s")

nsfnet_step = nsfnet_scenario.results.get_step("nsfnet_sensitivity")
nsfnet_data = nsfnet_step.get("data", {})
nsfnet_meta = nsfnet_step.get("metadata", {})

print(f"\n  Metadata:")
print(f"    Iterations: {nsfnet_meta.get('iterations')}")
print(f"    Unique patterns: {nsfnet_meta.get('unique_patterns')}")

print(f"\n  Baseline (NewYork -> PaloAlto):")
nsfnet_baseline = nsfnet_data.get("baseline", {})
if nsfnet_baseline:
    for flow in nsfnet_baseline.get("flows", []):
        placed = flow.get("placed", 0)
        print(f"    Max flow: {placed:.1f}")
        sens = flow.get("data", {}).get("sensitivity", {})
        print(f"    Critical edges ({len(sens)} total):")
        for edge, reduction in sorted(sens.items(), key=lambda x: -x[1])[:10]:
            print(f"      {edge}: -{reduction:.1f}")

print(f"\n  Top bottleneck components across failure scenarios:")
nsfnet_comp = nsfnet_data.get("component_scores", {})
for flow_key, components in nsfnet_comp.items():
    print(f"    Flow: {flow_key}")
    sorted_comps = sorted(
        components.items(), key=lambda x: -x[1].get("mean", 0)
    )
    for comp_name, stats in sorted_comps[:15]:
        print(f"      {comp_name}: mean={stats['mean']:.2f}, "
              f"max={stats['max']:.2f}, min={stats['min']:.2f}")


# ── Summary ──────────────────────────────────────────────────────────────

print("\n" + "=" * 72)
print("SUMMARY")
print("=" * 72)
print("""
Sensitivity analysis in NetGraph identifies network bottlenecks by:

1. Computing max-flow between source/target node groups
2. Identifying saturated (critical) edges in the flow solution
3. Measuring flow reduction when each critical edge is removed
4. Under Monte Carlo failure scenarios, aggregating component impact
   statistics (mean, max, min) across iterations

Key findings:
- Three API levels: AnalysisContext (low), FailureManager (mid), Scenario (high)
- Supports both shortest-path (IP/IGP) and full max-flow (SDN/TE) modes
- Parallel execution via C++ backend with GIL release
- Deduplicates identical failure patterns to save computation
- Results include per-component scores ranked by criticality
""")
