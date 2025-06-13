# Command Line Interface

NetGraph provides a command-line interface for running scenarios and generating results directly from the terminal.

## Installation

The CLI is available when NetGraph is installed via pip:

```bash
pip install ngraph
```

## Basic Usage

The primary command is `run`, which executes scenario files:

```bash
# Run a scenario and write results to results.json
python -m ngraph run scenario.yaml

# Write results to a custom file
python -m ngraph run scenario.yaml --results output.json
python -m ngraph run scenario.yaml -r output.json

# Print results to stdout as well
python -m ngraph run scenario.yaml --stdout
```

## Command Reference

### `run`

Execute a NetGraph scenario file.

**Syntax:**
```bash
python -m ngraph run <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to execute

**Options:**

- `--results`, `-r`: Output file path for results (JSON format)
- `--stdout`: Print results to stdout
- `--keys`, `-k`: Space-separated list of workflow step names to include in output
- `--help`, `-h`: Show help message

## Examples

### Basic Execution

```bash
# Run a scenario (writes results.json)
python -m ngraph run my_network.yaml
```

### Save Results to File

```bash
# Save results to a JSON file
python -m ngraph run my_network.yaml --results analysis.json
```

### Running Test Scenarios

```bash
# Run one of the included test scenarios
python -m ngraph run tests/scenarios/scenario_1.yaml --results results.json
```

### Filtering Results by Step Names

You can filter the output to include only specific workflow steps using the `--keys` option:

```bash
# Only include results from the capacity_probe step
python -m ngraph run scenario.yaml --keys capacity_probe

# Include multiple specific steps
python -m ngraph run scenario.yaml --keys build_graph capacity_probe

# Filter and print to stdout
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

## Output Format

The CLI outputs results in JSON format. The structure depends on the workflow steps executed in your scenario:

- **BuildGraph**: Returns graph data in node-link JSON format
- **CapacityProbe**: Returns max flow values with descriptive labels
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

## Integration with Workflows

The CLI executes the complete workflow defined in your scenario file, running all steps in sequence and accumulating results. This allows you to automate complex network analysis tasks without manual intervention.

## See Also

- [DSL Reference](dsl.md) - Scenario file syntax and structure
- [API Reference](api.md) - Python API for programmatic access
- [Tutorial](../getting-started/tutorial.md) - Step-by-step guide to creating scenarios
