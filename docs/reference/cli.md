# Command Line Interface

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [Workflow Reference](workflow.md) — analysis workflow configuration and execution
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

NetGraph provides a command-line interface for inspecting, running, and analyzing scenarios from the terminal.

## Basic Usage

The CLI provides two primary commands:

- `inspect`: Analyze and validate scenario files without running them
- `run`: Execute scenario files and generate results

**Global options** (must be placed before the command):

- `--verbose`, `-v`: Enable debug logging
- `--quiet`: Suppress console output (logs only)

### Quick Start

```bash
# Inspect a provided scenario
ngraph inspect scenarios/square_mesh.yaml

# Run a scenario (creates square_mesh.results.json by default)
ngraph run scenarios/square_mesh.yaml

```

## Command Reference

### `inspect`

Analyze and validate a NetGraph scenario file without executing it.

**Syntax:**

```bash
ngraph [--verbose|--quiet] inspect <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to inspect

**Options:**

- `--detail`, `-d`: Show detailed information including complete node/link tables and step parameters
- `--output`, `-o`: Output directory for generated artifacts (e.g., profiles)

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
ngraph inspect scenarios/backbone_clos.yml

# Detailed inspection with complete node/link tables and step parameters
ngraph inspect scenarios/nsfnet.yaml --detail

# Inspect with verbose logging (note: global option placement)
ngraph --verbose inspect scenarios/square_mesh.yaml
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
ngraph [--verbose|--quiet] run <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to execute

**Options:**

- `--results`, `-r`: Path to export results as JSON (default: `<scenario_name>.results.json`)
- `--no-results`: Disable results file generation
- `--stdout`: Print results to stdout in addition to saving file
- `--keys`, `-k`: Space-separated list of workflow step names to include in output
- `--profile`: Enable performance profiling with CPU analysis and bottleneck detection
- `--profile-memory`: Also track peak memory per step
- `--output`, `-o`: Output directory for generated artifacts

## Examples

### Basic Execution

```bash
# Run a scenario (creates square_mesh.results.json by default)
ngraph run scenarios/square_mesh.yaml

# Run a scenario and save results to custom file
ngraph run scenarios/backbone_clos.yml --results clos_analysis.json

# Run a scenario without creating any files
ngraph run scenarios/nsfnet.yaml --no-results
```

### Save Results to File

```bash
# Save results to a custom JSON file
ngraph run scenarios/backbone_clos.yml --results analysis.json

# Save to file AND print to stdout
ngraph run scenarios/backbone_clos.yml --results analysis.json --stdout

# Use default filename and also print to stdout
ngraph run scenarios/square_mesh.yaml --stdout
```

### Running Test Scenarios

```bash
# Run one of the provided scenarios with results export
ngraph run scenarios/backbone_clos.yml --results results.json
```

### Filtering Results by Step Names

You can filter the output to include only specific workflow steps using the `--keys` option:

```bash
# Only include results from the MSD step
ngraph run scenarios/square_mesh.yaml --keys msd_baseline --stdout

# Include multiple specific steps and save to custom file
ngraph run scenarios/backbone_clos.yml --keys network_statistics tm_placement --results filtered.json

# Filter and print to stdout while using default file
ngraph run scenarios/backbone_clos.yml --keys network_statistics --stdout
```

The `--keys` option filters by the `name` field of workflow steps defined in your scenario YAML file. For example, if your scenario has:

```yaml
workflow:
  - type: NetworkStats
    name: network_statistics
  - type: MaximumSupportedDemand
    name: msd_baseline
```

Then `--keys network_statistics` will include only the results from the NetworkStats step, and `--keys msd_baseline` will include only the MaximumSupportedDemand results.

### Performance Profiling

Enable performance profiling to identify bottlenecks and analyze execution time:

```bash
# Run scenario with profiling
ngraph run scenarios/backbone_clos.yml --profile

# Combine profiling with results export
ngraph run scenarios/backbone_clos.yml --profile --results analysis.json

# Profile specific workflow steps and track memory
ngraph run scenarios/backbone_clos.yml --profile --profile-memory --keys tm_placement
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

### Output Format

The CLI outputs results as JSON with a fixed top-level shape:

```json
{
  "workflow": { "<step>": { "step_type": "...", "execution_order": 0, "step_name": "..." } },
  "steps": {
    "network_statistics": { "metadata": {}, "data": { "node_count": 42, "link_count": 84 } },
    "msd_baseline": { "metadata": {}, "data": { "alpha_star": 1.23, "context": { "demand_set": "baseline_traffic_matrix" } } },
    "tm_placement": { "metadata": { "iterations": 1000 }, "data": { "flow_results": [ { "flows": [], "summary": {} } ], "context": { "demand_set": "baseline_traffic_matrix" } } }
  },
  "scenario": { "seed": 42, "failures": { }, "demands": { } }
}
```

- **BuildGraph**: stores `data.graph` in node-link JSON format
- **MaxFlow** and **TrafficMatrixPlacement**: store `data.flow_results` as lists of per-iteration results (flows + summary)
- **NetworkStats**: stores capacity and degree statistics under `data`

## Output Behavior

NetGraph CLI generates results by default for analysis workflows:

### Default Behavior (Results Generated)

```bash
ngraph run scenarios/square_mesh.yaml
```

- Executes the scenario
- Logs execution progress to the terminal
- **Creates `<scenario_name>.results.json` by default**
- Shows success message with file location

### Custom Results File

```bash
# Save to custom file
ngraph run scenarios/square_mesh.yaml --results my_analysis.json
```

- Creates specified JSON file instead of results.json
- Useful for organizing multiple analysis runs

### Print to Terminal

```bash
ngraph run scenarios/square_mesh.yaml --stdout
```

- Creates results.json AND prints JSON to stdout
- Useful for viewing results immediately while also saving them

### Combined Output

```bash
ngraph run scenarios/square_mesh.yaml --results analysis.json --stdout
```

- Creates custom JSON file AND prints to stdout
- Provides flexibility for different workflows

### Disable File Generation (Edge Cases)

```bash
ngraph run scenarios/square_mesh.yaml --no-results
```

- Executes scenario without creating any output files
- Only shows execution logs and completion status
- Useful for testing, CI/CD validation, or when only logs are needed

## Integration with Workflows

The CLI executes the complete workflow defined in your scenario file, running all steps in sequence and accumulating results. This runs complex network analysis tasks without manual intervention.

### Recommended Workflow

1. **Inspect first**: Always use `inspect` to validate and understand your scenario
2. **Debug issues**: Use detailed inspection to troubleshoot network expansion problems
3. **Run after validation**: Execute scenarios after successful inspection
4. **Iterate**: Use inspection during scenario development to verify changes

```bash
# Development workflow
ngraph inspect scenarios/backbone_clos.yml --detail
ngraph run scenarios/backbone_clos.yml
```

### Debugging Scenarios

When developing complex scenarios with blueprints and hierarchical structures:

```bash
# Check if scenario loads correctly
ngraph inspect scenarios/square_mesh.yaml

# Debug network expansion issues (note: global option placement)
ngraph --verbose inspect scenarios/backbone_clos.yml --detail

# Verify workflow steps are configured correctly
ngraph inspect scenarios/backbone_clos.yml --detail | grep -A 5 "WORKFLOW STEPS"
```

The `inspect` command will catch common issues like:

- Invalid YAML syntax
- Missing blueprint references
- Incorrect node/link patterns
- Workflow step configuration errors
- Risk group and policy definition problems
