# Command Line Interface

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [Workflow Reference](workflow.md) — analysis workflow configuration and execution
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

The `ngraph` command inspects, runs, and analyzes scenarios from the terminal.

## Basic Usage

Two commands:

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
- `--output`, `-o`: Output directory for generated artifacts (accepted for CLI consistency; `inspect` itself writes no files)

**What it does:**

Loads and validates the scenario file, then reports:

- **Scenario metadata**: seed, and whether the run is reproducible
- **Network structure**: node/link counts, enabled vs. disabled, hierarchy
- **Capacity statistics**: link and node capacity min/max/mean/median/total
- **Risk groups**: defined groups, each enabled or disabled
- **Components library**: components available to the scenario
- **Failure policies**: each policy's mode count (modes and rules in detail mode)
- **Demand sets**: demand patterns and volumes, capacity-vs-demand summary
- **Workflow steps**: the steps that would run, in order

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

- `--results`, `-r`: Path to export results as JSON (default: `<scenario_name>.results.json`; relative paths are placed under `--output` when provided)
- `--no-results`: Disable results file generation
- `--stdout`: Print results to stdout in addition to saving file. Log output, status banners, the `--profile` performance report, and run error messages all go to stderr, so stdout contains only the JSON results (safe to pipe to `jq`)
- `--keys`, `-k`: Space-separated list of workflow step names to include in output
- `--profile`: Enable performance profiling with CPU analysis and bottleneck detection
- `--profile-memory`: Also track peak memory per step
- `--output`, `-o`: Output directory for generated artifacts

## Examples

### Basic Execution

```bash
# Default output file (square_mesh.results.json)
ngraph run scenarios/square_mesh.yaml

# Custom results path
ngraph run scenarios/backbone_clos.yml --results analysis.json

# Save and also print JSON to stdout
ngraph run scenarios/backbone_clos.yml --results analysis.json --stdout

# Run without writing any files
ngraph run scenarios/nsfnet.yaml --no-results
```

### Filtering Results by Step Names

`--keys` restricts the `steps` section to the named workflow steps; the `workflow` metadata section still lists every step that ran:

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
    "tm_placement": { "metadata": { "iterations": 1000 }, "data": { "baseline": { "flows": [], "summary": {} }, "flow_results": [ { "flows": [], "summary": {} } ], "context": { "demand_set": "baseline_traffic_matrix" } } }
  },
  "scenario": { "seed": 42, "failures": { }, "demands": { } }
}
```

- **BuildGraph**: stores `data.graph` in node-link JSON format
- **MaxFlow** and **TrafficMatrixPlacement**: store the no-failure reference under `data.baseline` and unique failure patterns (deduplicated, each with `occurrence_count`, flows + summary) under `data.flow_results`
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

- Creates specified JSON file instead of the default `<scenario_name>.results.json`
- Useful for organizing multiple analysis runs

### Print to Terminal

```bash
ngraph run scenarios/square_mesh.yaml --stdout
```

- Creates `<scenario_name>.results.json` AND prints JSON to stdout
- Useful for viewing results immediately while also saving them

### Combined Output

```bash
ngraph run scenarios/square_mesh.yaml --results analysis.json --stdout
```

- Creates custom JSON file AND prints to stdout

### Disable File Generation (Edge Cases)

```bash
ngraph run scenarios/square_mesh.yaml --no-results
```

- Executes scenario without creating any output files
- Only shows execution logs and completion status
- Useful for testing, CI/CD validation, or when only logs are needed

## Integration with Workflows

`ngraph run` executes every step of the workflow defined in the scenario file, in sequence, accumulating results as it goes.

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

`inspect` catches common issues:

- Invalid YAML syntax
- Missing blueprint references
- Incorrect node/link patterns
- Workflow step configuration errors
- Risk group and policy definition problems
