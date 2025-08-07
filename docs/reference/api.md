# API Reference

> **📚 Quick Navigation:**

> - **[DSL Reference](dsl.md)** - YAML syntax and scenario definition
> - **[Auto-Generated API Reference](api-full.md)** - Complete class and method documentation
> - **[CLI Reference](cli.md)** - Command-line interface documentation

This section provides a curated guide to NetGraph's Python API, organized by typical usage patterns.

## 1. Fundamentals

The core components that form the foundation of most NetGraph programs.

### Scenario

**Purpose:** The main orchestrator that coordinates network topology, analysis workflows, and result collection.

**When to use:** Every NetGraph program starts with a Scenario - either loaded from YAML or built programmatically.

```python
from ngraph.scenario import Scenario

# Load complete scenario from YAML (recommended)
scenario = Scenario.from_yaml(yaml_content)

# Or build programmatically
from ngraph.network import Network
scenario = Scenario(network=Network(), workflow=[])

# Execute the scenario
scenario.run()

# Access results
print(scenario.results.get("NetworkStats", "node_count"))
```

**Key Methods:**

- `from_yaml(yaml_content)` - Load scenario from YAML string/file
- `run()` - Execute the complete analysis workflow

**Integration:** Scenario coordinates Network topology, workflow execution, and Results collection. Components can also be used independently for direct programmatic access.

### Network

**Purpose:** Represents network topology and provides fundamental analysis capabilities like maximum flow calculation.

**When to use:** Core component for representing network structure. Used directly for programmatic topology creation or accessed via `scenario.network`.

```python
from ngraph.network import Network, Node, Link

# Create network topology
network = Network()

# Add nodes and links
node1 = Node(name="datacenter1")
node2 = Node(name="datacenter2")
network.add_node(node1)
network.add_node(node2)

link = Link(source="datacenter1", target="datacenter2", capacity=100.0)
network.add_link(link)

# Calculate maximum flow (returns dict)
max_flow = network.max_flow(
    source_path="datacenter1",
    sink_path="datacenter2"
)
# Result: {('datacenter1', 'datacenter2'): 100.0}
```

**Key Methods:**

- `add_node(node)`, `add_link(link)` - Build topology programmatically
- `max_flow(source_path, sink_path, **options)` - Calculate maximum flow (returns dict)
- `nodes`, `links` - Access topology as dictionaries

**Key Concepts:**

- **Node.disabled/Link.disabled:** Scenario-level configuration that persists across analyses
- **Regex patterns:** Use regex patterns like `"datacenter.*"` to select multiple nodes/links

**Integration:** Foundation for all analysis. Used directly or through NetworkView for filtered analysis.

### Results

**Purpose:** Centralized container for storing and retrieving analysis results from workflow steps.

**When to use:** Automatically managed by `scenario.results`. Used for storing custom analysis results and retrieving outputs from workflow steps.

```python
# Access results from scenario
results = scenario.results

# Retrieve specific results
node_count = results.get("NetworkStats", "node_count")
capacity_envelopes = results.get("CapacityEnvelopeAnalysis", "capacity_envelopes")

# Get all results for a metric across steps
all_capacities = results.get_all("total_capacity")

# Export all results for serialization
all_data = results.to_dict()
```

**Key Methods:**

- `get(step_name, key, default=None)` - Retrieve specific result
- `put(step_name, key, value)` - Store result (typically used by workflow steps)
- `get_all(key)` - Get all values for a key across steps
- `to_dict()` - Export all results with automatic serialization of objects with to_dict() method

**Integration:** Used by all workflow steps for result storage. Provides consistent access pattern for analysis outputs.

## 2. Basic Analysis

Essential analysis capabilities for network evaluation.

### Flow Analysis

**Purpose:** Calculate network flows between source and sink groups with various policies and constraints.

**When to use:** Fundamental analysis for understanding network capacity, bottlenecks, and traffic engineering scenarios.

```python
from ngraph.lib.algorithms.base import FlowPlacement

# Basic maximum flow (returns dict)
max_flow = network.max_flow(
    source_path="datacenter.*",  # Regex: all nodes matching pattern
    sink_path="edge.*",
    mode="combine"               # Aggregate all source->sink flows
)

# Advanced flow options
max_flow = network.max_flow(
    source_path="pod1/servers",
    sink_path="pod2/servers",
    mode="pairwise",            # Individual flows between each pair
    shortest_path=True,         # Use only shortest paths
    flow_placement=FlowPlacement.PROPORTIONAL  # UCMP load balancing
)

# Detailed flow analysis with cost distribution
result = network.max_flow_with_summary(
    source_path="datacenter.*",
    sink_path="edge.*",
    mode="combine"
)
(src_label, sink_label), (flow_value, summary) = next(iter(result.items()))

# Cost distribution shows flow volume per path cost (useful for latency analysis)
print(f"Cost distribution: {summary.cost_distribution}")
# Example: {2.0: 150.0, 4.0: 75.0} means 150 units on cost-2 paths, 75 on cost-4 paths
```

**Key Options:**

- `mode`: `"combine"` (aggregate flows) or `"pairwise"` (individual pair flows)
- `shortest_path`: `True` (shortest only) or `False` (all available paths)
- `flow_placement`: `FlowPlacement.PROPORTIONAL` (UCMP) or `FlowPlacement.EQUAL_BALANCED` (ECMP)

**Advanced Features:**

- **Cost Distribution**: `FlowSummary.cost_distribution` provides flow volume breakdown by path cost for latency span analysis and performance characterization
- **Analytics**: Edge flows, residual capacities, min-cut analysis, and reachability information

**Integration:** Available on both Network and NetworkView objects. Foundation for FailureManager Monte Carlo analysis.

### NetworkView

**Purpose:** Provides filtered view of network topology for failure analysis without modifying the base network.

**When to use:** Simulate component failures, analyze degraded network states, or perform parallel analysis with different exclusions.

```python
from ngraph.network_view import NetworkView

# Create view with failed components (for failure simulation)
failed_view = NetworkView.from_excluded_sets(
    network,
    excluded_nodes={"spine1", "spine2"},    # Failed nodes
    excluded_links={"link_123"}             # Failed links
)

# Analyze degraded network
degraded_flow = failed_view.max_flow("datacenter.*", "edge.*")

# NetworkView has same analysis API as Network
bottlenecks = failed_view.saturated_edges("source", "sink")
```

**Key Features:**

- **Read-only overlay:** Combines scenario-disabled and analysis-excluded elements
- **Concurrent analysis:** Supports different failure scenarios in parallel
- **Identical API:** Same analysis methods as Network

**Integration:** Used internally by FailureManager for Monte Carlo analysis. Enables concurrent failure simulations without network state conflicts.

## 3. Advanced Analysis

Sophisticated analysis capabilities using Monte Carlo methods and parallel processing.

### FailureManager

**Purpose:** Authoritative Monte Carlo failure analysis engine with parallel processing and result aggregation.

**When to use:** Capacity envelope analysis, demand placement studies, component sensitivity analysis, or custom Monte Carlo simulations.

```python
from ngraph.failure_manager import FailureManager
from ngraph.failure_policy import FailurePolicy, FailureRule
from ngraph.results_artifacts import FailurePolicySet

# Setup failure policies
policy_set = FailurePolicySet()
rule = FailureRule(entity_scope="link", rule_type="choice", count=2)
policy = FailurePolicy(rules=[rule])
policy_set.add("random_failures", policy)

# Create FailureManager
manager = FailureManager(
    network=network,
    failure_policy_set=policy_set,
    policy_name="random_failures"
)

# Capacity envelope analysis
envelope_results = manager.run_max_flow_monte_carlo(
    source_path="datacenter.*",
    sink_path="edge.*",
    iterations=1000,
    parallelism=4,
    baseline=True
)
```

**Key Methods:**

- `run_max_flow_monte_carlo()` - Capacity envelope analysis under failures
- `run_demand_placement_monte_carlo()` - Traffic demand placement success analysis
- `run_sensitivity_monte_carlo()` - Component criticality and impact analysis
- `run_monte_carlo_analysis()` - Generic Monte Carlo with custom analysis functions

**Key Features:**

- **Parallel processing** with worker caching for performance
- **Automatic result aggregation** into rich statistical objects
- **Reproducible results** with seed support
- **Failure policy integration** for realistic failure scenarios

**Integration:** Uses NetworkView for isolated failure simulation. Returns specialized result objects for statistical analysis.

### Monte Carlo Results

**Purpose:** Rich result objects with statistical analysis and visualization capabilities.

**When to use:** Analyzing outputs from FailureManager convenience methods - provides pandas integration and statistical summaries.

```python
# Work with capacity envelope results
flow_keys = envelope_results.flow_keys()  # Available flow pairs
envelope = envelope_results.get_envelope("datacenter->edge")

# Statistical analysis with pandas
stats_df = envelope_results.to_dataframe()
summary = envelope_results.summary_statistics()

# Export for further analysis
export_data = envelope_results.export_summary()

# For demand placement analysis
placement_results = manager.run_demand_placement_monte_carlo(demands)
success_rates = placement_results.success_rate_distribution()
```

**Key Result Types:**

- `CapacityEnvelopeResults` - Statistical flow capacity distributions
- `DemandPlacementResults` - Traffic placement success metrics
- `SensitivityResults` - Component criticality rankings

**Integration:** Returned by FailureManager convenience methods. Provides pandas DataFrames and export capabilities for notebook analysis.

## 4. Data & Results

Working with analysis outputs and implementing custom result storage.

### Result Artifacts

**Purpose:** Serializable data structures that store analysis results with consistent interfaces for export and reconstruction.

**When to use:** Working with stored analysis results, implementing custom workflow steps, or exporting data for external analysis.

```python
from ngraph.results_artifacts import CapacityEnvelope, FailurePatternResult

# Access capacity envelopes from analysis results
envelope_dict = scenario.results.get("CapacityEnvelopeAnalysis", "capacity_envelopes")
envelope = CapacityEnvelope.from_dict(envelope_dict["datacenter->edge"])

# Statistical access
print(f"Mean capacity: {envelope.mean_capacity}")
print(f"95th percentile: {envelope.get_percentile(95)}")

# Export and reconstruction
serialized = envelope.to_dict()  # For JSON storage
values = envelope.expand_to_values()  # Reconstruct original samples
```

**Key Classes:**

- `CapacityEnvelope` - Frequency-based capacity distributions with percentile analysis
- `FailurePatternResult` - Failure scenario details with capacity impact
- `FailurePolicySet` - Collections of named failure policies

**Integration:** Used by workflow steps and FailureManager. All provide `to_dict()` and `from_dict()` for serialization.

### Export Patterns

**Purpose:** Best practices for storing results in custom workflow steps and analysis functions.

```python
from ngraph.workflow.base import WorkflowStep

class CustomAnalysis(WorkflowStep):
    def run(self, scenario):
        # Simple metrics
        scenario.results.put(self.name, "node_count", len(scenario.network.nodes))

        # Complex objects - convert to dict first
        analysis_result = self.perform_analysis(scenario.network)
        if hasattr(analysis_result, 'to_dict'):
            scenario.results.put(self.name, "analysis", analysis_result.to_dict())
        else:
            scenario.results.put(self.name, "analysis", analysis_result)
```

**Storage Conventions:**

- Use `self.name` as step identifier for result storage
- Convert complex objects using `to_dict()` before storage
- Use descriptive keys like `"capacity_envelopes"`, `"network_statistics"`
- Results are automatically serialized via `results.to_dict()`

## 5. Automation

Workflow orchestration and reusable network templates.

### Workflow Steps

**Purpose:** Automated analysis sequences with standardized result storage and execution order.

**When to use:** Complex multi-step analysis, reproducible analysis pipelines, or when you need automatic result collection and metadata tracking.

Available workflow steps:

- `BuildGraph` - Converts Network to NetworkX StrictMultiDiGraph
- `NetworkStats` - Basic topology statistics (node/link counts, capacities)
- `CapacityEnvelopeAnalysis` - Monte Carlo failure analysis with FailureManager

**Integration:** Defined in YAML scenarios or created programmatically. Each step stores results using consistent naming patterns in `scenario.results`.

### Blueprint System

**Purpose:** Reusable network topology templates defined in YAML for complex, hierarchical network structures.

**When to use:** Creating standardized network architectures, multi-pod topologies, or when you need parameterized network generation.

```python
# Blueprints are typically defined in YAML and used via Scenario
# For programmatic topology creation, use Network class directly
```

**Integration:** Blueprints are processed during scenario creation. See [DSL Reference](dsl.md) for YAML blueprint syntax and examples.

## 6. Extensions

Advanced capabilities for custom analysis and low-level operations.

### Utilities & Helpers

**Purpose:** Graph format conversion and direct access to low-level algorithms.

**When to use:** Custom analysis requiring NetworkX integration, performance-critical algorithms, or when you need direct control over graph operations.

```python
from ngraph.lib.util import to_digraph, from_digraph
from ngraph.lib.algorithms.spf import spf
from ngraph.lib.algorithms.max_flow import calc_max_flow

# Convert to NetworkX for custom algorithms
nx_graph = to_digraph(scenario.network.to_strict_multidigraph())

# Direct algorithm access
costs, predecessors = spf(graph, source_node)
max_flow_value = calc_max_flow(graph, source, sink)
```

**Integration:** Provides bridge between NetGraph and NetworkX ecosystems. Used when built-in analysis methods are insufficient.

### Error Handling

**Purpose:** Exception handling patterns and result validation for reliable analysis.

```python
try:
    scenario = Scenario.from_yaml(yaml_content)
    scenario.run()

    # Validate expected results
    if scenario.results.get("CapacityEnvelopeAnalysis", "capacity_envelopes") is None:
        print("Warning: Expected flow analysis result not found")

except ValueError as e:
    print(f"YAML validation failed: {e}")
except Exception as e:
    print(f"Analysis error: {e}")
```

**Common Patterns:**

- Use `results.get()` with `default` parameter for safe result access
- Validate step execution using `results.get_step_metadata()`
- Handle YAML parsing errors with specific exception types

---

For complete method signatures and detailed parameter documentation, see the [Auto-Generated API Reference](api-full.md) or use Python's built-in help:

```python
help(Scenario.from_yaml)
help(Network.max_flow)
```
