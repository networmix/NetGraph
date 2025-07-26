# Command Line Interface

NetGraph provides a command-line interface for inspecting, running, and analyzing scenarios directly from the terminal.

## Installation

The CLI is available when NetGraph is installed via pip:

```bash
pip install ngraph
```

## Basic Usage

The CLI provides three primary commands:

- `inspect`: Analyze and validate scenario files without running them
- `run`: Execute scenario files and generate results
- `report`: Generate analysis reports from results files

### Quick Start

```bash
# Inspect a scenario to understand its structure
python -m ngraph inspect my_scenario.yaml

# Run a scenario (generates results.json by default)
python -m ngraph run my_scenario.yaml

# Generate analysis report from results
python -m ngraph report results.json --notebook analysis.ipynb
```

```bash
# Run a scenario (generates results.json by default)
python -m ngraph run scenario.yaml

# Run a scenario and save results to custom file
python -m ngraph run scenario.yaml --results output.json
python -m ngraph run scenario.yaml -r output.json

# Run a scenario without saving results (edge cases only)
python -m ngraph run scenario.yaml --no-results

# Print results to stdout in addition to saving file
python -m ngraph run scenario.yaml --stdout

# Save to custom file AND print to stdout
python -m ngraph run scenario.yaml --results output.json --stdout
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

- `--results`, `-r`: Path to export results as JSON (default: "results.json")
- `--no-results`: Disable results file generation (for edge cases)
- `--stdout`: Print results to stdout in addition to saving file
- `--keys`, `-k`: Space-separated list of workflow step names to include in output
- `--profile`: Enable performance profiling with CPU analysis and bottleneck detection
- `--help`, `-h`: Show help message

### `report`

Generate analysis reports from NetGraph results files.

**Syntax:**

```bash
python -m ngraph report <results_file> [options]
```

**Arguments:**

- `results_file`: Path to the JSON results file (default: "results.json")

**Options:**

- `--notebook`, `-n`: Path for generated Jupyter notebook (default: "analysis.ipynb")
- `--html`: Generate HTML report (default: "analysis.html" if no path specified)
- `--include-code`: Include code cells in HTML report (default: no code in HTML)
- `--help`, `-h`: Show help message

**What it does:**

The `report` command generates analysis reports from results files created by the `run` command. It creates:

- **Jupyter notebook**: Interactive analysis notebook with code cells, visualizations, and explanations (default: "analysis.ipynb")
- **HTML report** (optional): Static report for viewing without Jupyter, optionally including code (default: "analysis.html" when --html is used)

The report automatically detects and analyzes the workflow steps present in the results file, creating appropriate sections and visualizations for each analysis type.

**Examples:**

```bash
# Generate notebook from default results.json
python -m ngraph report

# Generate notebook with custom paths
python -m ngraph report my_results.json --notebook my_analysis.ipynb

# Generate both notebook and HTML report (default filenames)
python -m ngraph report results.json --html

# Generate HTML report with custom filename
python -m ngraph report results.json --html custom_report.html

# Generate HTML report without code cells (clean report)
python -m ngraph report results.json --html

# Generate HTML report with code cells included
python -m ngraph report results.json --html --include-code
```

**Use cases:**

- **Analysis documentation**: Create shareable notebooks documenting network analysis results
- **Report generation**: Generate HTML reports for stakeholders who don't use Jupyter
- **Iterative analysis**: Create notebooks for further data exploration and visualization
- **Presentation**: Generate clean HTML reports for presentations and documentation

## Examples

### Basic Execution

```bash
# Run a scenario (creates results.json by default)
python -m ngraph run my_network.yaml

# Run a scenario and save results to custom file
python -m ngraph run my_network.yaml --results analysis.json

# Run a scenario without creating any files (edge cases)
python -m ngraph run my_network.yaml --no-results
```

### Save Results to File

```bash
# Save results to a custom JSON file
python -m ngraph run my_network.yaml --results analysis.json

# Save to file AND print to stdout
python -m ngraph run my_network.yaml --results analysis.json --stdout

# Use default filename and also print to stdout
python -m ngraph run my_network.yaml --stdout
```

### Running Test Scenarios

```bash
# Run one of the included test scenarios with results export
python -m ngraph run tests/scenarios/scenario_1.yaml --results results.json
```

### Filtering Results by Step Names

You can filter the output to include only specific workflow steps using the `--keys` option:

```bash
# Only include results from the capacity_probe step
python -m ngraph run scenario.yaml --keys capacity_probe --stdout

# Include multiple specific steps and save to custom file
python -m ngraph run scenario.yaml --keys build_graph capacity_probe --results filtered.json

# Filter and print to stdout while using default file
python -m ngraph run scenario.yaml --keys capacity_probe --stdout
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

NetGraph CLI generates results by default to make analysis workflows more convenient:

### Default Behavior (Results Generated)
```bash
python -m ngraph run scenario.yaml
```
- Executes the scenario
- Logs execution progress to the terminal
- **Creates results.json automatically**
- Shows success message with file location

### Custom Results File
```bash
# Save to custom file
python -m ngraph run scenario.yaml --results my_analysis.json
```
- Creates specified JSON file instead of results.json
- Useful for organizing multiple analysis runs

### Print to Terminal
```bash
python -m ngraph run scenario.yaml --stdout
```
- Creates results.json AND prints JSON to stdout
- Useful for viewing results immediately while also saving them

### Combined Output
```bash
python -m ngraph run scenario.yaml --results analysis.json --stdout
```
- Creates custom JSON file AND prints to stdout
- Maximum flexibility for different workflows

### Disable File Generation (Edge Cases)
```bash
python -m ngraph run scenario.yaml --no-results
```
- Executes scenario without creating any output files
- Only shows execution logs and completion status
- Useful for testing, CI/CD validation, or when only logs are needed

**This design prioritizes the common case:** Most users want to save their analysis results, so this is now the default behavior.

## Integration with Workflows

The CLI executes the complete workflow defined in your scenario file, running all steps in sequence and accumulating results. This automates complex network analysis tasks without manual intervention.

### Recommended Workflow

1. **Inspect first**: Always use `inspect` to validate and understand your scenario
2. **Debug issues**: Use detailed inspection to troubleshoot network expansion problems
3. **Run after validation**: Execute scenarios after successful inspection
4. **Iterate**: Use inspection during scenario development to verify changes

```bash
# Development workflow
python -m ngraph inspect my_scenario.yaml --detail  # Validate and debug
python -m ngraph run my_scenario.yaml              # Execute (creates results.json)
python -m ngraph report results.json --notebook    # Generate analysis report
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
