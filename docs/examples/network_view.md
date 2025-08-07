# NetworkView Example

This example demonstrates how to use `NetworkView` for temporary exclusion simulation and concurrent network analysis without modifying the base network.

## Basic Usage

```python
from ngraph.network import Network, Node, Link
from ngraph.network_view import NetworkView

# Create a network
net = Network()
net.add_node(Node("A"))
net.add_node(Node("B"))
net.add_node(Node("C"))
net.add_link(Link("A", "B", capacity=100.0))
net.add_link(Link("B", "C", capacity=100.0))

# Create a view with node A excluded
view = NetworkView.from_excluded_sets(
    net,
    excluded_nodes=["A"],
    excluded_links=[]
)

# Analyze capacity with exclusion
flow = view.max_flow("^A$", "^C$", mode="combine")
print(f"Flow with A excluded: {flow}")  # Will be 0.0

# Original network is unchanged
assert not net.nodes["A"].disabled
```

## Workflow Integration

### CapacityEnvelopeAnalysis with Deterministic Analysis

```yaml
workflow:
  # Single deterministic analysis (equivalent to removed CapacityProbe)
  - step_type: CapacityEnvelopeAnalysis
    name: "deterministic_capacity_analysis"
    source_path: "^spine.*"
    sink_path: "^leaf.*"
    iterations: 1
    baseline: false
    failure_policy: null  # No failures for deterministic analysis
```

### NetworkStats with Exclusions

```python
from ngraph.workflow.network_stats import NetworkStats

# Get statistics with temporary exclusions
stats = NetworkStats(
    name="filtered_stats",
    excluded_nodes=["node1", "node2"],
    excluded_links=["link1"]
)
stats.run(scenario)
```

## Concurrent Analysis

```python
# Create multiple views for concurrent analysis
view1 = NetworkView.from_excluded_sets(net, excluded_nodes=["A"])
view2 = NetworkView.from_excluded_sets(net, excluded_nodes=["B"])
view3 = NetworkView.from_excluded_sets(net, excluded_nodes=["C"])

# Run concurrent analyses
results = []
for view in [view1, view2, view3]:
    flow = view.max_flow("^A$", "^C$", mode="combine")
    results.append(flow)

# Each view operates independently
print(f"Results: {results}")
```

## CapacityEnvelopeAnalysis Integration

The `CapacityEnvelopeAnalysis` workflow step now uses `NetworkView` internally:

```python
from ngraph.workflow.capacity_envelope_analysis import CapacityEnvelopeAnalysis

# This uses NetworkView internally for each Monte Carlo iteration
envelope = CapacityEnvelopeAnalysis(
    source_path="^spine.*",
    sink_path="^leaf.*",
    failure_policy="random_failures",
    iterations=1000,
    parallelism=8,  # Safe concurrent execution
    baseline=True,  # Run first iteration without failures for comparison
    store_failure_patterns=True  # Store failure patterns for analysis
)
```

### Baseline Analysis

The `baseline` parameter enables comparison between failure scenarios and no-failure baseline:

```yaml
workflow:
  - step_type: CapacityEnvelopeAnalysis
    name: "capacity_analysis"
    source_path: "^datacenter.*"
    sink_path: "^edge.*"
    failure_policy: "random_failures"
    iterations: 1000
    baseline: true  # First iteration runs without failures
    store_failure_patterns: true  # Store patterns for detailed analysis
```

This creates baseline capacity measurements alongside failure scenario results, enabling:

- Comparison of degraded vs. normal network capacity
- Analysis of failure impact magnitude
- Identification of failure-resistant flow paths

## Key Benefits

1. **Immutability**: Base network remains unchanged during analysis
2. **Concurrency**: Multiple views can analyze the same network simultaneously
3. **Performance**: Selective caching provides ~30x speedup for repeated operations
4. **Consistency**: Combines scenario-disabled and analysis-excluded elements

## Best Practices

1. Use `NetworkView` for all temporary exclusion analysis
2. Use `Network.disable_node()` only for persistent scenario configuration
3. Create new NetworkView instances for each analysis - they're lightweight
4. Leverage parallelism - NetworkView enables safe concurrent analysis
