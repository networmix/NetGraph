# Command Line Interface

NetGraph provides a command-line interface for inspecting, running, and analyzing scenarios directly from the terminal.

## Installation

The CLI is available when NetGraph is installed via pip:

```bash
pip install ngraph
```

## Basic Usage

The CLI provides two primary commands:

- `inspect`: Analyze and validate scenario files without running them
- `run`: Execute scenario files and generate results

### Quick Start

```bash
# Inspect a scenario to understand its structure
python -m ngraph inspect my_scenario.yaml

# Run a scenario after inspection
python -m ngraph run my_scenario.yaml --results
```

```bash
# Run a scenario (execution only, no file output)
python -m ngraph run scenario.yaml

# Run a scenario and export results to results.json
python -m ngraph run scenario.yaml --results

# Export results to a custom file
python -m ngraph run scenario.yaml --results output.json
python -m ngraph run scenario.yaml -r output.json

# Print results to stdout only (no file)
python -m ngraph run scenario.yaml --stdout

# Export to file AND print to stdout
python -m ngraph run scenario.yaml --results --stdout
```

## Command Reference

### `inspect`

Analyze and validate a NetGraph scenario file without executing it.

**Syntax:**

```bash
python -m ngraph inspect <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to inspect

**Options:**

- `--detail`, `-d`: Show detailed information including complete node/link tables and step parameters
- `--help`, `-h`: Show help message

**What it does:**

The `inspect` command loads and validates a scenario file, then provides information about:

- **Scenario metadata**: Seed configuration and deterministic behavior
- **Network structure**: Node/link counts, enabled/disabled breakdown, hierarchy analysis
- **Capacity statistics**: Link and node capacity analysis with min/max/mean/total values
- **Risk groups**: Network resilience groupings and their status
- **Components library**: Available components for network modeling
- **Failure policies**: Configured failure scenarios and their rules
- **Traffic matrices**: Demand patterns and traffic flows
- **Workflow steps**: Analysis pipeline and step-by-step execution plan

In detail mode (`--detail`), shows complete tables for all nodes and links with capacity and connectivity information.

**Examples:**

```bash
# Basic inspection
python -m ngraph inspect my_scenario.yaml

# Detailed inspection with comprehensive node/link tables and step parameters
python -m ngraph inspect my_scenario.yaml --detail

# Inspect with verbose logging
python -m ngraph inspect my_scenario.yaml --verbose
```

**Use cases:**

- **Scenario validation**: Verify YAML syntax and structure
- **Network debugging**: Analyze blueprint expansion and node/link creation
- **Capacity analysis**: Review network capacity distribution and connectivity
- **Workflow preview**: Examine analysis steps before execution

### `run`

Execute a NetGraph scenario file.

**Syntax:**

```bash
python -m ngraph run <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to execute

**Options:**

- `--results`, `-r`: Optional path to export results as JSON. If provided without a path, defaults to "results.json"
- `--stdout`: Print results to stdout
- `--keys`, `-k`: Space-separated list of workflow step names to include in output
- `--profile`: Enable performance profiling with CPU analysis and bottleneck detection
- `--help`, `-h`: Show help message

## Examples

### Basic Execution

```bash
# Run a scenario (execution only, no output files)
python -m ngraph run my_network.yaml

# Run a scenario and export results to default file
python -m ngraph run my_network.yaml --results
```

### Save Results to File

```bash
# Save results to a custom JSON file
python -m ngraph run my_network.yaml --results analysis.json

# Save to file AND print to stdout
python -m ngraph run my_network.yaml --results analysis.json --stdout
```

### Running Test Scenarios

```bash
# Run one of the included test scenarios with results export
python -m ngraph run tests/scenarios/scenario_1.yaml --results results.json
```

### Filtering Results by Step Names

You can filter the output to include only specific workflow steps using the `--keys` option:

```bash
# Only include results from the capacity_probe step (stdout only)
python -m ngraph run scenario.yaml --keys capacity_probe --stdout

# Include multiple specific steps and export to file
python -m ngraph run scenario.yaml --keys build_graph capacity_probe --results filtered.json

# Filter and print to stdout while also saving to default file
python -m ngraph run scenario.yaml --keys capacity_probe --results --stdout
```

The `--keys` option filters by the `name` field of workflow steps defined in your scenario YAML file. For example, if your scenario has:

```yaml
workflow:
  - step_type: BuildGraph
    name: build_graph
  - step_type: CapacityProbe
    name: capacity_probe
    # ... other parameters
```

Then `--keys build_graph` will include only the results from the BuildGraph step, and `--keys capacity_probe` will include only the CapacityProbe results.

### Performance Profiling

NetGraph provides performance profiling to identify bottlenecks, analyze execution time, and optimize workflow performance. The profiling system provides CPU-level analysis with function-by-function timing and bottleneck detection.

#### Performance Analysis

Use `--profile` to get performance analysis:

```bash
# Run scenario with profiling
python -m ngraph run scenario.yaml --profile

# Combine profiling with results export
python -m ngraph run scenario.yaml --profile --results

# Profiling with filtered output
python -m ngraph run scenario.yaml --profile --keys capacity_probe
```

Performance profiling provides:

- **Summary**: Total execution time, CPU efficiency, function call statistics
- **Step timing analysis**: Time spent in each workflow step with percentage breakdown
- **Bottleneck identification**: Workflow steps consuming >10% of total execution time
- **Function-level analysis**: Top CPU-consuming functions within each bottleneck
- **Call statistics**: Function call counts and timing distribution
- **CPU utilization patterns**: Detailed breakdown of computational efficiency
- **Targeted recommendations**: Specific optimization suggestions for each bottleneck

#### Profiling Output

Profiling generates a performance report displayed after scenario execution:

```
================================================================================
NETGRAPH PERFORMANCE PROFILING REPORT
================================================================================

1. SUMMARY
----------------------------------------
Total Execution Time: 12.456 seconds
Total CPU Time: 11.234 seconds
CPU Efficiency: 90.2%
Total Workflow Steps: 3
Average Step Time: 4.152 seconds
Total Function Calls: 1,234,567
Function Calls/Second: 99,123

1 performance bottleneck(s) identified

2. WORKFLOW STEP TIMING ANALYSIS
----------------------------------------
Step Name          Type               Wall Time    CPU Time     Calls      % Total
build_graph        BuildGraph         0.123s       0.098s       1,234      1.0%
capacity_probe     CapacityProbe      11.234s      10.987s      1,200,000  90.2%
network_stats      NetworkStats       1.099s       0.149s       33,333     8.8%

3. PERFORMANCE BOTTLENECK ANALYSIS
----------------------------------------
Bottleneck #1: capacity_probe (CapacityProbe)
   Wall Time: 11.234s (90.2% of total)
   CPU Time: 10.987s
   Function Calls: 1,200,000
   CPU Efficiency: 97.8% (CPU-intensive workload)
   Recommendation: Consider algorithmic optimization or parallelization

4. DETAILED FUNCTION ANALYSIS
----------------------------------------
Top CPU-consuming functions in 'capacity_probe':
   ngraph/lib/algorithms/max_flow.py:42(dijkstra_shortest_path)
      Time: 8.456s, Calls: 500,000
   ngraph/lib/algorithms/max_flow.py:156(ford_fulkerson)
      Time: 2.234s, Calls: 250,000
```

#### Profiling Best Practices

**When to Use Profiling:**

- Performance optimization during development
- Identifying bottlenecks in complex workflows
- Analyzing scenarios with large networks or datasets
- Benchmarking before/after optimization changes

**Development Workflow:**

```bash
# 1. Profile scenario to identify bottlenecks
python -m ngraph run scenario.yaml --profile

# 2. Combine with filtering for targeted analysis
python -m ngraph run scenario.yaml --profile --keys slow_step

# 3. Profile with results export for analysis
python -m ngraph run scenario.yaml --profile --results analysis.json
```

**Performance Considerations:**

- Profiling adds minimal overhead (~15-25%)
- Use production-like data sizes for accurate bottleneck identification
- Profile multiple runs to account for variability in timing measurements
- Focus optimization efforts on steps consuming >10% of total execution time

**Interpreting Results:**

- **CPU Efficiency**: Ratio of CPU time to wall time (higher is better for compute-bound tasks)
- **Function Call Rate**: Calls per second (very high rates may indicate optimization opportunities)
- **Bottleneck Percentage**: Time percentage helps prioritize optimization efforts
- **Efficiency Ratio**: Low ratios (<30%) suggest I/O-bound operations or external dependencies

#### Advanced Profiling Scenarios

**Profiling Large Networks:**

```bash
# Profile capacity analysis on large networks
python -m ngraph run large_network.yaml --profile --keys capacity_envelope_analysis
```

**Comparative Profiling:**

```bash
# Profile before optimization
python -m ngraph run scenario_v1.yaml --profile > profile_v1.txt

# Profile after optimization
python -m ngraph run scenario_v2.yaml --profile > profile_v2.txt

# Compare results manually or with diff tools
```

**Targeted Profiling:**

```bash
# Profile only specific workflow steps
python -m ngraph run scenario.yaml --profile --keys capacity_probe network_stats

# Profile with results export for further analysis
python -m ngraph run scenario.yaml --profile --results analysis.json
```

## Output Format

The CLI outputs results in JSON format. The structure depends on the workflow steps executed in your scenario:

- **BuildGraph**: Returns graph data in node-link JSON format
- **CapacityProbe**: Returns max flow values with descriptive labels
- **NetworkStats**: Reports capacity and degree statistics
- **Other Steps**: Each step stores its results with step-specific keys

Example output structure:

```json
{
  "build_graph": {
    "graph": {
      "graph": {},
      "nodes": [
        {
          "id": "SEA",
          "attr": {
            "coords": [47.6062, -122.3321],
            "type": "node"
          }
        },
        {
          "id": "SFO",
          "attr": {
            "coords": [37.7749, -122.4194],
            "type": "node"
          }
        }
      ],
      "links": [
        {
          "source": 0,
          "target": 1,
          "key": "SEA|SFO|example_edge_id",
          "attr": {
            "capacity": 200,
            "cost": 8000,
            "distance_km": 1600
          }
        }
      ]
    }
  },
  "capacity_probe": {
    "max_flow:[SEA -> SFO]": 200.0
  }
}
```

The exact keys and values depend on:

- Which workflow steps are defined in your scenario
- The parameters and results of each step
- The network topology and analysis performed

## Output Behavior

**NetGraph CLI output behavior changed in recent versions** to provide more flexibility:

### Default Behavior (No Output Flags)
```bash
python -m ngraph run scenario.yaml
```
- Executes the scenario
- Logs execution progress to the terminal
- **Does not create any output files**
- **Does not print results to stdout**

### Export to File
```bash
# Export to default file (results.json)
python -m ngraph run scenario.yaml --results

# Export to custom file
python -m ngraph run scenario.yaml --results my_analysis.json
```

### Print to Terminal
```bash
python -m ngraph run scenario.yaml --stdout
```
- Prints JSON results to stdout
- **Does not create any files**

### Combined Output
```bash
python -m ngraph run scenario.yaml --results analysis.json --stdout
```
- Creates a JSON file AND prints to stdout
- Useful for viewing results immediately while also saving them

**Migration Note:** If you were relying on automatic `results.json` creation, add the `--results` flag to your commands.

## Integration with Workflows

The CLI executes the complete workflow defined in your scenario file, running all steps in sequence and accumulating results. This automates complex network analysis tasks without manual intervention.

### Recommended Workflow

1. **Inspect first**: Always use `inspect` to validate and understand your scenario
2. **Debug issues**: Use detailed inspection to troubleshoot network expansion problems
3. **Run after validation**: Execute scenarios only after successful inspection
4. **Iterate**: Use inspection during scenario development to verify changes

```bash
# Development workflow
python -m ngraph inspect my_scenario.yaml --detail  # Validate and debug
python -m ngraph run my_scenario.yaml --results        # Execute after validation
```

### Debugging Scenarios

When developing complex scenarios with blueprints and hierarchical structures:

```bash
# Check if scenario loads correctly
python -m ngraph inspect scenario.yaml

# Debug network expansion issues
python -m ngraph inspect scenario.yaml --detail --verbose

# Verify workflow steps are configured correctly
python -m ngraph inspect scenario.yaml --detail | grep -A 5 "Workflow Steps"
```

The `inspect` command will catch common issues like:
- Invalid YAML syntax
- Missing blueprint references
- Incorrect node/link patterns
- Workflow step configuration errors
- Risk group and policy definition problems

## See Also

- [DSL Reference](dsl.md) - Scenario file syntax and structure
- [API Reference](api.md) - Python API for programmatic access
- [Tutorial](../getting-started/tutorial.md) - Step-by-step guide to creating scenarios
