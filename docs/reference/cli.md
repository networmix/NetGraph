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
# Run a scenario and output results to stdout as JSON
python -m ngraph run scenario.yaml

# Run a scenario and save results to a file
python -m ngraph run scenario.yaml --results output.json
python -m ngraph run scenario.yaml -r output.json
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
- `--help`, `-h`: Show help message

## Examples

### Basic Execution

```bash
# Run a scenario with output to console
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

## Output Format

The CLI outputs results in JSON format. The structure depends on the workflow steps executed in your scenario:

- **BuildGraph**: Returns graph information as a string representation
- **CapacityProbe**: Returns max flow values with descriptive labels
- **Other Steps**: Each step stores its results with step-specific keys

Example output structure:
```json
{
  "build_graph": {
    "graph": "StrictMultiDiGraph with 6 nodes and 20 edges"
  },
  "capacity_probe": {
    "max_flow:[SEA|SFO -> JFK|DCA]": 150.0
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
