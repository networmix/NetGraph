# Command Line Interface

Quick links:

- [Design](design.md) - architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) - YAML syntax for scenario definition
- [Workflow Reference](workflow.md) - analysis workflow configuration and execution
- [API Reference](api.md) - Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) - complete class and method documentation

The `ngraph` command inspects and runs scenarios from the terminal.

## Basic Usage

Two commands:

- `inspect`: Load and validate a scenario and print its structure without running the workflow
- `run`: Run the workflow and write results

**Global options** (must be placed before the command):

- `--verbose`, `-v`: Enable debug logging
- `--quiet`: Show only warnings and errors in logs (command output is still printed)

### Quick Start

```bash
# Inspect a provided scenario
ngraph inspect scenarios/square_mesh.yaml

# Run a scenario (creates square_mesh.results.json by default)
ngraph run scenarios/square_mesh.yaml

```

## Command Reference

### `inspect`

Load and validate a scenario and print its structure without running the workflow.

**Syntax:**

```bash
ngraph [--verbose|--quiet] inspect <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to inspect

**Options:**

- `--detail`, `-d`: Show detailed information including complete node/link tables and step parameters

**Output:**

After loading and validating the scenario file, `inspect` reports:

- **Scenario metadata**: seed, and whether the run is reproducible
- **Network structure**: node/link counts, enabled vs. disabled, hierarchy
- **Capacity statistics**: link and node capacity min/max/mean/median/total
- **Risk groups**: defined groups, each enabled or disabled
- **Components library**: components available to the scenario
- **Failure policies**: each policy's mode count (modes and rules in detail mode)
- **Demand sets**: demand patterns and volumes, capacity-vs-demand summary
- **Workflow steps**: the steps that would run, in order

**Examples:**

```bash
# Basic inspection
ngraph inspect scenarios/backbone_clos.yml

# Detailed inspection with complete node/link tables and step parameters
ngraph inspect scenarios/nsfnet.yaml --detail

# Inspect with verbose logging (note: global option placement)
ngraph --verbose inspect scenarios/square_mesh.yaml
```

### `run`

Run the workflow of a scenario file and write the results.

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
- `--keys`, `-k`: Space-separated list of workflow step names to include in output; an unknown name is an error
- `--profile`: Profile the run and print a per-step CPU report to stderr
- `--profile-memory`: Also track peak memory per step (requires `--profile`)
- `--output`, `-o`: Output directory for generated artifacts: the results file and, with `--profile`, the `<scenario_name>.profiles` directory of worker profiles

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

`--keys` restricts the `steps` section to the named workflow steps; the `workflow` metadata section lists every step that ran. Unknown step names abort the run before any step executes:

```bash
# Only include results from the MSD step
ngraph run scenarios/square_mesh.yaml --keys msd_baseline --stdout

# Include multiple specific steps and save to custom file
ngraph run scenarios/backbone_clos.yml --keys network_statistics tm_placement --results filtered.json

# Filter and print to stdout while using default file
ngraph run scenarios/backbone_clos.yml --keys network_statistics --stdout
```

The names are the `name` fields of the steps in the scenario's `workflow` section.

### Performance Profiling

`--profile` reports where the run spends its time:

```bash
# Run scenario with profiling
ngraph run scenarios/backbone_clos.yml --profile

# Combine profiling with results export
ngraph run scenarios/backbone_clos.yml --profile --results analysis.json

# Track memory too, and export only the tm_placement step's results
ngraph run scenarios/backbone_clos.yml --profile --profile-memory --keys tm_placement
```

The report lists total execution time, time per step, the steps that take more than 10% of the total, and the top CPU-consuming functions within those steps.

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

| Command | Writes | Prints JSON |
|---------|--------|-------------|
| `ngraph run scenario.yaml` | `<scenario_name>.results.json` | no |
| `ngraph run scenario.yaml --results out.json` | `out.json` | no |
| `ngraph run scenario.yaml --stdout` | `<scenario_name>.results.json` | yes |
| `ngraph run scenario.yaml --results out.json --stdout` | `out.json` | yes |
| `ngraph run scenario.yaml --no-results` | nothing | no |
| `ngraph run scenario.yaml --no-results --stdout` | nothing | yes |

`run` writes logs and status messages to stderr in every case. Exit status is 0 on success, 1 when the scenario cannot be loaded or run, and 2 for invalid command-line arguments.

## Debugging Scenarios

Inspect a scenario before running it. When blueprint expansion does not produce the nodes or links you expect, add `--verbose` and `--detail`:

```bash
ngraph inspect scenarios/square_mesh.yaml
ngraph --verbose inspect scenarios/backbone_clos.yml --detail
ngraph inspect scenarios/backbone_clos.yml --detail | grep -A 5 "WORKFLOW STEPS"
```

`inspect` reports YAML and schema errors, unknown blueprint or risk-group references and invalid workflow step parameters, and its node and demand tables show whether selectors matched what you expected.
