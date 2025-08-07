# Command Line Interface

> **📚 Quick Navigation:**
>
> - **[DSL Reference](dsl.md)** - YAML syntax for scenario definition
> - **[API Reference](api.md)** - Python API for programmatic access
> - **[Auto-Generated API Reference](api-full.md)** - Complete class and method documentation

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

**Global options** (must be placed before the command):

- `--verbose`, `-v`: Enable verbose (DEBUG) logging
- `--quiet`, `-q`: Enable quiet mode (WARNING+ only)

### Quick Start

```bash
# Inspect a scenario to understand its structure
python -m ngraph inspect my_scenario.yaml

# Run a scenario (generates results.json by default)
python -m ngraph run my_scenario.yaml

# Generate analysis report from results
python -m ngraph report results.json --notebook analysis.ipynb
```

## Command Reference

### `inspect`

Analyze and validate a NetGraph scenario file without executing it.

**Syntax:**

```bash
python -m ngraph [--verbose|--quiet] inspect <scenario_file> [options]
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

# Detailed inspection with complete node/link tables and step parameters
python -m ngraph inspect my_scenario.yaml --detail

# Inspect with verbose logging (note: global option placement)
python -m ngraph --verbose inspect my_scenario.yaml
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
python -m ngraph [--verbose|--quiet] run <scenario_file> [options]
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
python -m ngraph [--verbose|--quiet] report [results_file] [options]
```

**Arguments:**

- `results_file`: Path to the JSON results file (default: "results.json")

**Options:**

- `--notebook`, `-n`: Output path for Jupyter notebook (default: "analysis.ipynb")
- `--html`: Generate HTML report (default: "analysis.html" if no path specified)
- `--include-code`: Include code cells in HTML output (default: report without code)
- `--help`, `-h`: Show help message

**What it does:**

The `report` command generates analysis reports from results files created by the `run` command. It creates:

- **Jupyter notebook**: Interactive analysis notebook with code cells, visualizations, and explanations (default: "analysis.ipynb")
- **HTML report** (optional): Static report for viewing without Jupyter, optionally including code (default: "analysis.html" when --html is used)

The report detects and analyzes the workflow steps present in the results file, creating appropriate sections and visualizations for each analysis type.

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

# Generate HTML report without code cells
python -m ngraph report results.json --html

# Generate HTML report with code cells included
python -m ngraph report results.json --html --include-code
```

**Use cases:**

- **Analysis documentation**: Create shareable notebooks documenting network analysis results
- **Report generation**: Generate HTML reports for stakeholders who don't use Jupyter
- **Iterative analysis**: Create notebooks for further data exploration and visualization
- **Presentation**: Generate HTML reports for presentations and documentation

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
python -m ngraph run scenarios/simple.yaml --results results.json
```

### Filtering Results by Step Names

You can filter the output to include only specific workflow steps using the `--keys` option:

```bash
# Only include results from the capacity_analysis step
python -m ngraph run scenario.yaml --keys capacity_analysis --stdout

# Include multiple specific steps and save to custom file
python -m ngraph run scenario.yaml --keys build_graph capacity_analysis --results filtered.json

# Filter and print to stdout while using default file
python -m ngraph run scenario.yaml --keys capacity_analysis --stdout
```

The `--keys` option filters by the `name` field of workflow steps defined in your scenario YAML file. For example, if your scenario has:

```yaml
workflow:
  - step_type: BuildGraph
    name: build_graph
  - step_type: CapacityEnvelopeAnalysis
    name: capacity_analysis
    # ... other parameters
```

Then `--keys build_graph` will include only the results from the BuildGraph step, and `--keys capacity_analysis` will include only the CapacityEnvelopeAnalysis results.

### Performance Profiling

Enable performance profiling to identify bottlenecks and analyze execution time:

```bash
# Run scenario with profiling
python -m ngraph run scenario.yaml --profile

# Combine profiling with results export
python -m ngraph run scenario.yaml --profile --results analysis.json

# Profile specific workflow steps
python -m ngraph run scenario.yaml --profile --keys capacity_analysis
```

The profiling output includes:

- **Summary**: Total execution time, CPU efficiency, function call statistics
- **Step timing**: Time spent in each workflow step with percentage breakdown
- **Bottlenecks**: Steps consuming >10% of total execution time
- **Function analysis**: Top CPU-consuming functions within bottlenecks
- **Recommendations**: Specific suggestions for each bottleneck

**When to use profiling:**

- Performance analysis during development
- Identifying bottlenecks in complex workflows
- Benchmarking before/after changes

## Output Format

The CLI outputs results in JSON format. The structure depends on the workflow steps executed in your scenario:

- **BuildGraph**: Returns graph data in node-link JSON format
- **CapacityEnvelopeAnalysis**: Returns capacity envelope data with statistical distributions
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
  "capacity_analysis": {
    "capacity_envelopes": {
      "^SEA$ -> ^SFO$": {"mean": 200.0, "max": 200.0, "min": 200.0}
    }
  }
}
```

The exact keys and values depend on:

- Which workflow steps are defined in your scenario
- The parameters and results of each step
- The network topology and analysis performed

## Output Behavior

NetGraph CLI generates results by default for analysis workflows:

### Default Behavior (Results Generated)

```bash
python -m ngraph run scenario.yaml
```

- Executes the scenario
- Logs execution progress to the terminal
- **Creates results.json by default**
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
- Provides flexibility for different workflows

### Disable File Generation (Edge Cases)

```bash
python -m ngraph run scenario.yaml --no-results
```

- Executes scenario without creating any output files
- Only shows execution logs and completion status
- Useful for testing, CI/CD validation, or when only logs are needed

**This design prioritizes the common case:** Most users want to save their analysis results, so this is now the default behavior.

## Integration with Workflows

The CLI executes the complete workflow defined in your scenario file, running all steps in sequence and accumulating results. This runs complex network analysis tasks without manual intervention.

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

# Debug network expansion issues (note: global option placement)
python -m ngraph --verbose inspect scenario.yaml --detail

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

- **[DSL Reference](dsl.md)** - Scenario file syntax and structure
- **[API Reference](api.md)** - Python API for programmatic access
- **[Tutorial](../getting-started/tutorial.md)** - Step-by-step guide to creating scenarios
