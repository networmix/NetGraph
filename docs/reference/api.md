# API Reference

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [Workflow Reference](workflow.md) — analysis workflow configuration and execution
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

This section provides a curated guide to NetGraph's Python API, organized by typical usage patterns.

## Performance Notes

NetGraph uses a **hybrid Python+C++ architecture**:

- **High-level APIs** (Network, Scenario, Workflow) are pure Python with ergonomic interfaces
- **Core algorithms** (shortest paths, max-flow, K-shortest paths) execute in optimized C++ via NetGraph-Core
- **GIL released** during algorithm execution for true parallel processing
- **Transparent integration**: You work with Python objects; Core acceleration is automatic

All public APIs accept and return Python types (Network, Node, Link, FlowSummary, etc.).
The C++ layer is an implementation detail you generally don't interact with directly.

## 1. Fundamentals

The core components that form the foundation of most NetGraph programs.

### Scenario

**Purpose:** Coordinates network topology, workflow execution, and result storage for complete analysis pipelines.

**When to use:** Entry point for analysis workflows - load from YAML for declarative scenarios or construct programmatically for direct API access.

```python
from pathlib import Path
from ngraph.scenario import Scenario

# Load complete scenario from YAML text
yaml_text = Path("scenarios/square_mesh.yaml").read_text()
scenario = Scenario.from_yaml(yaml_text)

# Execute the scenario
scenario.run()

# Export results
exported = scenario.results.to_dict()
print(exported["workflow"].keys())
```

**Key Methods:**

- `from_yaml(yaml_str, default_components=None)` - Parse scenario from YAML string (use `Path.read_text()` for file loading)
- `run()` - Execute workflow steps in sequence

**Integration:** Scenario coordinates Network topology, workflow execution, and Results collection. Components can also be used independently for direct programmatic access.

### Network

**Purpose:** Represents network topology.

**When to use:** Core component for representing network structure. Used directly for programmatic topology creation or accessed via `scenario.network`.

```python
from ngraph.model.network import Network, Node, Link
from ngraph.solver.maxflow import max_flow

# Create a tiny network
network = Network()
network.add_node(Node(name="n1"))
network.add_node(Node(name="n2"))
network.add_link(Link(source="n1", target="n2", capacity=100.0))

# Calculate maximum flow (returns Dict[Tuple[str, str], float])
flow_result = max_flow(
    network,
    source_path="n1",
    sink_path="n2"
)
print(flow_result)  # {("n1", "n2"): 100.0}
```

**Key Methods:**

- `add_node(node)`, `add_link(link)` - Build topology programmatically
- `nodes`, `links` - Access topology as dictionaries

**Key Concepts:**

- **disabled flags:** Node.disabled and Link.disabled mark components as inactive in the scenario topology (use `excluded_nodes`/`excluded_links` parameters for temporary analysis-time exclusion)
- **Node selection:** Use regex patterns anchored at start (e.g., `"^datacenter.*"`) or attribute directives (`"attr:role"`) to select and group nodes (see DSL Node Selection)


### Results

**Purpose:** Centralized container for storing and retrieving analysis results from workflow steps.

**When to use:** Managed by Scenario; stores workflow step outputs with metadata. Access via `scenario.results` for result retrieval and custom step implementation.

```python
# Access results from scenario
results = scenario.results

# Export all results for serialization
all_data = results.to_dict()
print(list(all_data["steps"].keys()))
```

**Key Methods:**

- `enter_step(step_name)` / `exit_step()` - Scope writes to a step (managed by WorkflowStep.execute())
- `put(key, value)` - Store value under active step; key must be `"metadata"` or `"data"`
- `get(key, default=None)` - Retrieve value from active step scope
- `get_step(step_name)` - Retrieve complete step dict for cross-step reads
- `to_dict()` - Export results with shape `{workflow, steps, scenario}` (JSON-serializable)

**Integration:** Used by all workflow steps for result storage. Provides consistent access pattern for analysis outputs.

## 2. Basic Analysis

Essential analysis capabilities for network evaluation.

### Flow Analysis

**Purpose:** Calculate network flows between source and sink groups with various policies and constraints.

**When to use:** Compute network capacity between source and sink groups. Supports multiple flow placement policies and failure scenarios.

**Performance:** Max-flow computation executes in C++ with the GIL released for concurrent execution. Algorithm complexity is O(V²E) for push-relabel with gap heuristic.

```python
from ngraph.types.base import FlowPlacement
from ngraph.solver.maxflow import max_flow, max_flow_with_details

# Maximum flow between group patterns (combine all sources/sinks)
flow_result = max_flow(
    network,
    source_path="^metro1/.*",
    sink_path="^metro5/.*",
    mode="combine"
)

# Detailed flow analysis with cost distribution
result = max_flow_with_details(
    network,
    source_path="^metro1/.*",
    sink_path="^metro5/.*",
    mode="combine"
)
(src_label, sink_label), summary = next(iter(result.items()))
print(summary.cost_distribution)  # Dict[float, float] mapping cost to flow volume
```

**Key Options:**

- `mode`: `"combine"` (aggregate flows) or `"pairwise"` (individual pair flows)
- `shortest_path`: `True` (shortest only) or `False` (all available paths)
- `flow_placement`: `FlowPlacement.PROPORTIONAL` (WCMP) or `FlowPlacement.EQUAL_BALANCED` (ECMP)

**Advanced Features:**

- **Cost Distribution**: `FlowSummary.cost_distribution` maps path cost to flow volume at that cost tier
- **Min-cut**: `FlowSummary.min_cut` contains saturated edges crossing the source-sink cut

**Integration:** Uses `excluded_nodes` and `excluded_links` parameters for filtered analysis. Foundation for FailureManager Monte Carlo analysis.

### Filtered Analysis (Failure Simulation)

**Purpose:** Execute analysis on filtered topology views using exclusion sets rather than graph mutation.

**When to use:** Failure simulation, sensitivity analysis, or concurrent evaluation of multiple degraded states.

```python
# Identify links to fail (e.g., all links from "n2")
failed_links = {
    l.id for l in network.links.values()
    if l.source == "n2" or l.target == "n2"
}

# Analyze degraded network by passing excluded_links
degraded_flow = max_flow(
    network,
    source_path="n1",
    sink_path="n3",
    excluded_links=failed_links
)
print(degraded_flow)
```

**Key Features:**

- **Read-only filtering:** Uses analysis-time exclusion lists without mutating the Network
- **Concurrent analysis:** Supports different failure scenarios in parallel (thread-safe)
- **Identical API:** Uses the same solver functions (`max_flow`, etc.) with optional exclusion arguments


## 3. Advanced Analysis

Sophisticated analysis capabilities using Monte Carlo methods and parallel processing.

### FailureManager

**Purpose:** Monte Carlo failure analysis engine with parallel execution and automatic result aggregation.

**When to use:** Monte Carlo failure analysis for capacity distribution, demand placement, or component criticality studies.

```python
from ngraph.exec.failure.manager import FailureManager
from ngraph.model.failure.policy import FailurePolicy, FailureMode, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet

policy_set = FailurePolicySet()
policy = FailurePolicy(modes=[
    FailureMode(
        weight=1.0,
        rules=[FailureRule(entity_scope="link", rule_type="choice", count=1)]
    )
])
policy_set.policies["one_link"] = policy

manager = FailureManager(
    network=network,
    failure_policy_set=policy_set,
    policy_name="one_link"
)

results = manager.run_max_flow_monte_carlo(
    source_path="n1",
    sink_path="n2",
    iterations=10,
    parallelism=1,
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

**Integration:** Uses `excluded_nodes`/`excluded_links` for isolated failure simulation. Returns specialized result objects for statistical analysis.

### Monte Carlo Results

**Purpose:** Rich result objects with statistical analysis and visualization capabilities.

**When to use:** Process results from FailureManager Monte Carlo methods. Provides statistical aggregation and serialization.

```python
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary

# Construct flow entries for a single iteration
flow = FlowEntry(
    source="n1", destination="n2", priority=0,
    demand=10.0, placed=10.0, dropped=0.0,
    cost_distribution={2.0: 6.0, 4.0: 4.0}
)
summary = FlowSummary(
    total_demand=10.0, total_placed=10.0, overall_ratio=1.0,
    dropped_flows=0, num_flows=1
)
iteration = FlowIterationResult(
    failure_id="baseline",
    flows=[flow],
    summary=summary
)
# Export to JSON-serializable dict
result_dict = iteration.to_dict()
```

**Key Result Types:**

- `FlowIterationResult` - Per-iteration flow results (flows + summary)
- `FlowEntry` - Per-flow entry (source, destination, volumes, cost distribution)
- `FlowSummary` - Aggregate totals for an iteration
- `SensitivityResults` - Component criticality rankings

**Integration:** Returned by FailureManager convenience methods. Analyze exported JSON results using external scripts.

## 4. Data & Results

Working with analysis outputs and implementing custom result storage.

### Result Artifacts

**Purpose:** Serializable data structures that store analysis results with consistent interfaces for export and reconstruction.

**When to use:** Working with stored analysis results, implementing custom workflow steps, or exporting data for external analysis.

```python
from ngraph.results import Results

# Access results after scenario execution
exported = scenario.results.to_dict()
print(list(exported["steps"].keys()))
```

**Key Classes:**

- `CapacityEnvelope` - Frequency-based capacity distributions with percentile analysis
- `FailurePatternResult` - Failure scenario details with capacity impact
- `FailurePolicySet` - Collections of named failure policies

**Integration:** Used by workflow steps and FailureManager. All provide `to_dict()` and `from_dict()` for serialization.

### Export Patterns

**Purpose:** Patterns for result storage in custom workflow steps with consistent serialization.

```python
from ngraph.workflow.base import WorkflowStep

class CustomAnalysis(WorkflowStep):
    def run(self, scenario):
        # Simple metrics
        scenario.results.put("metadata", {})
        scenario.results.put("data", {"node_count": len(scenario.network.nodes)})

        # Complex objects - convert to dict first
        analysis_result = self.perform_analysis(scenario.network)
        payload = analysis_result.to_dict() if hasattr(analysis_result, 'to_dict') else analysis_result
        scenario.results.put("data", {"analysis": payload})
```

**Storage Conventions:**

- Store step metadata using `results.put("metadata", {})`
- Store step data using `results.put("data", {...})`
- Convert complex objects to dicts via `to_dict()` before storage
- Export complete results via `scenario.results.to_dict()`

## 5. Automation

Workflow orchestration and reusable network templates.

### Workflow Steps

**Purpose:** Automated analysis sequences with standardized result storage and execution order.

**When to use:** Multi-step analysis pipelines with automatic result storage, execution ordering, and metadata tracking.

Available workflow steps:

- `BuildGraph` - Exports graph in node-link JSON under `data.graph`
- `NetworkStats` - Basic topology statistics under `data`
- `MaxFlow` - Monte Carlo flow capacity analysis under `data.flow_results`
- `TrafficMatrixPlacement` - Monte Carlo demand placement under `data.flow_results`
- `MaximumSupportedDemand` - Alpha search results under `data`

**Integration:** Defined in YAML scenarios or created programmatically. Each step stores results using consistent naming patterns in `scenario.results`.

### Blueprint System

**Purpose:** Reusable network topology templates defined in YAML for complex, hierarchical network structures.

**When to use:** Define reusable topology templates with parameterization. Common for data center fabrics and hierarchical network structures.

```python
# Blueprints are typically defined in YAML and used via Scenario
# For programmatic topology creation, use Network class directly
```

**Integration:** Blueprints are processed during scenario creation. See [DSL Reference](dsl.md) for YAML blueprint syntax and examples.

## 6. Extensions

Advanced capabilities for custom analysis and low-level operations.

### Utilities & Helpers

**Purpose:** Graph format conversion and access to adapter layer for advanced use cases.

**When to use:** Custom analysis requiring direct access to Core graphs, or when built-in analysis methods are insufficient.

**Note:** For most use cases, use the high-level Network API. The adapter layer (`ngraph.adapters.core`) is available for advanced scenarios requiring direct Core graph access.

```python
from ngraph.adapters.core import build_graph
import netgraph_core

# Access Core layer for custom algorithm implementation
graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(
    network, add_reverse=True
)

# Execute Core algorithms directly (operate on int node IDs, return NumPy arrays)
backend = netgraph_core.Backend.cpu()
algs = netgraph_core.Algorithms(backend)

src_id = node_mapper.to_id("A")
costs, predecessors = algs.spf(graph_handle, src_id)
# costs: numpy array of float64 distances from src_id to each node
```

**Integration:** Direct Core access for custom algorithm implementation. Built-in solver functions (`max_flow`, etc.) already provide Core integration.

### Error Handling

**Purpose:** Exception handling patterns and result validation for reliable analysis.

```python
try:
    scenario = Scenario.from_yaml(yaml_content)
    scenario.run()

    # Validate expected results
    exported = scenario.results.to_dict()
    assert "steps" in exported and exported["steps"], "No steps present in results"

except ValueError as e:
    print(f"YAML validation failed: {e}")
except Exception as e:
    print(f"Analysis error: {e}")
```

**Common Patterns:**

- Catch `ValueError` for YAML schema validation failures
- Use `results.get(key, default=None)` for optional result values
- Validate presence of expected workflow steps in exported results
