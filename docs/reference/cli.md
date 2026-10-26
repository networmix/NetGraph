# Command Line

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

```text
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
- **Workflow steps**: the steps that would run, in order, with their parameters in detail mode

A link counts as enabled when it and both of its end nodes are enabled, in every figure ([Links, directions and what is enabled](../concepts.md#links-directions-and-what-is-enabled)). The hierarchy groups nodes by the `/`-separated parts of their names, one level per part, and its counts include disabled nodes and links: a level's `Links` counts the links with an end inside it. With `--detail`, `IntLinkCap` sums the capacities of the links with both ends inside the level and `ExtLinkCap` of those with one end inside it, each link once. A selector preview reads `<label>: G groups, N nodes (E enabled)`: the label is the selector's path (`*` without one) followed by its other parts, for example `^A [match: role == edge or tier == 1]`, `* [group_by: role]` or `^A [active_only: false]`; N counts every node the selector matches with its `active_only` filter lifted, E the enabled ones among them, and G the groups of those N nodes. Each distinct selector is listed on its own, also when two share a path. A selection error during preview (for example a group key too large to write as text) prints `ERROR` with the reason, and invalid hardware prints under the hierarchy as `Unable to analyze (...)`; `inspect` still finishes. An invalid demand or workflow selector pattern is refused at load, names the field and value, and makes `inspect` exit 1.

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

```text
ngraph [--verbose|--quiet] run <scenario_file> [options]
```

**Arguments:**

- `scenario_file`: Path to the YAML scenario file to execute

**Options:**

- `--results`, `-r`: Path to export results as JSON (default: `<scenario_name>.results.json`; relative paths are placed under `--output` when provided)
- `--no-results`: Disable results file generation
- `--stdout`: Print results to stdout in addition to saving file. Log output, status banners, the `--profile` performance report, and run error messages all go to stderr, so stdout contains only the JSON results (safe to pipe to `jq`)
- `--keys`, `-k`: Space-separated list of workflow step names to include in output; an unknown name is an error
- `--profile`: Print per-step wall time, process CPU time and the Python call profile to stderr
- `--profile-memory`: Also track peak memory per step (requires `--profile`)
- `--output`, `-o`: Output directory for the results file

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

`--keys` selects entries from the ordered `steps` array after the complete workflow executes. It keeps declaration order and each step's own `execution_order`, so a filtered export may have gaps. Unknown step names abort before any step executes:

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

The report lists total elapsed time, time per step, steps taking more than 10% of the total and the Python call profile within those steps. A step's CPU time is the process's CPU time while it runs, across all threads and native work included, so CPU efficiency (CPU time over wall time) can exceed 100% when worker threads run. The function table ranks cProfile's internal time on the profiled thread; work on other threads appears only in the CPU totals, and work inside native routines is not split by C++ function. The report is printed to stderr.

### Output Format

The top-level fields are `metadata`, `units_report` and ordered `steps`. Each step contains its name, type, order, seed provenance, normalized question and typed result. For example, list the steps' questions and the bandwidth unit `q` with:

```bash
jq '{q: .units_report.q, steps: [.steps[] | {name, execution_order, question}]}' square_mesh.results.json
```

Each step's result is described with the step in [Workflow Steps](workflow.md), and every field in [Results](results.md). Native bandwidth amounts are integer units of the run's `q`, which the units report records; [Results and their units](../concepts.md#results-and-their-units) lists the other kinds of numbers. Optional costs, cuts and edge arrays appear only when requested and applicable.

The results file and `--stdout` carry the same compact JSON: one line with no indentation or spaces after separators, non-ASCII characters kept, then a newline (`jq .` prints it indented). NaN is refused. Encoding completes before a results file is atomically replaced.

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
