---
name: netgraph-dev-workflow
description: >
  NetGraph development workflow and CLI reference. Use when: setting up dev environment,
  running tests or lint, fixing CI failures, using the ngraph CLI (inspect, run commands),
  troubleshooting venv issues, or asking about make targets.
---

# NetGraph Development Workflow

## Command Discovery

Run `make help` to see all available targets with descriptions. The Makefile is the authoritative source.

## Initial Setup

```bash
make dev  # Creates venv, installs package + dev deps, sets up pre-commit hooks
```

Requires Python 3.11+. The setup auto-detects the best available Python version.

## Workflow Patterns

### Iterating on Code

| Scenario | Command | Notes |
|----------|---------|-------|
| Quick feedback loop | `make qt` | Fast: skips slow tests, no coverage |
| Before committing | `make check` | **Mandatory.** Runs pre-commit + tests + lint |
| Full test suite | `make test` | Includes slow tests, generates coverage |
| After changing APIs | `make docs` | **Mandatory.** Regenerates API documentation |

### When to Run `make docs`

Run `make docs` when modifying:
- Public function/class signatures
- Docstrings
- Module-level documentation
- Adding new public modules

The generated `docs/reference/api-full.md` should be committed with your changes.

### Fixing Lint Failures

When `make lint` fails:

1. Run `make format` first (auto-fixes formatting issues)
2. Run `make lint` again to check remaining issues
3. Fix any type errors or code quality issues manually

### Pre-commit vs CI

| Command | Behavior | Use case |
|---------|----------|----------|
| `make check` | Auto-fixes via pre-commit, then tests + lint | Local development |
| `make check-ci` | Read-only lint + validate + test (no mutations) | CI pipelines |

### Validating Scenarios

```bash
make validate  # Validates all YAML files in scenarios/ and tests/integration/
```

## CLI Reference

The `ngraph` CLI runs and inspects network scenarios. Use `ngraph --help` or `ngraph <command> --help` for full option details.

### Commands

| Command | Purpose |
|---------|---------|
| `ngraph inspect <scenario.yaml>` | Validate scenario and show structure summary |
| `ngraph run <scenario.yaml>` | Execute workflow steps and export results |

### Common Usage Patterns

**Validate before running:**

```bash
./venv/bin/ngraph inspect scenario.yaml
./venv/bin/ngraph run scenario.yaml
```

**Detailed inspection (node/link tables, step parameters):**

```bash
./venv/bin/ngraph inspect --detail scenario.yaml
```

**Run with profiling (CPU analysis, bottleneck detection):**

```bash
./venv/bin/ngraph run --profile scenario.yaml
./venv/bin/ngraph run --profile --profile-memory scenario.yaml  # Include memory tracking
```

**Control output:**

```bash
./venv/bin/ngraph run scenario.yaml                          # Default: writes <scenario>.results.json
./venv/bin/ngraph run scenario.yaml --results out.json       # Custom results path
./venv/bin/ngraph run scenario.yaml --output ./results/      # All artifacts to directory
./venv/bin/ngraph run scenario.yaml --no-results --stdout    # Print to stdout only
./venv/bin/ngraph run scenario.yaml --keys msd placement     # Filter to specific workflow steps
```

**Debug logging:**

```bash
./venv/bin/ngraph -v inspect scenario.yaml   # Verbose (debug level)
./venv/bin/ngraph --quiet run scenario.yaml  # Suppress info, show warnings only
```

### Key Options

**Global:**
- `-v, --verbose` - Enable debug logging
- `--quiet` - Suppress console output (warnings only)

**inspect:**
- `-d, --detail` - Show complete node/link tables and step parameters
- `-o, --output DIR` - Output directory for artifacts

**run:**
- `-r, --results FILE` - Custom results JSON path
- `--no-results` - Skip writing results file
- `--stdout` - Print results to stdout
- `-k, --keys STEP [STEP...]` - Filter output to specific workflow step names
- `--profile` - Enable CPU profiling with analysis
- `--profile-memory` - Add memory tracking (requires `--profile`)
- `-o, --output DIR` - Output directory for results and profiles

### Output Interpretation

**inspect output sections:**
1. **OVERVIEW** - Quick metrics: nodes, links, capacity, demand, utilization
2. **NETWORK STRUCTURE** - Hierarchy tree, capacity statistics, validation warnings
3. **RISK GROUPS** - Failure correlation groups defined
4. **COMPONENTS LIBRARY** - Hardware definitions for cost/power modeling
5. **FAILURE POLICIES** - Failure simulation rules and modes
6. **DEMAND SETS** - Traffic demands with pattern matching summary
7. **WORKFLOW STEPS** - Execution plan with node selection preview

**run output:**
- Results JSON contains `steps.<step_name>.data` for each workflow step
- With `--profile`: performance report shows timing breakdown and bottlenecks

## Running Commands

### Prefer Direct Venv Paths

Use direct paths instead of `source venv/bin/activate`:

```bash
./venv/bin/python -m pytest tests/dsl/      # Run specific tests
./venv/bin/ngraph inspect scenario.yaml     # Validate a scenario
./venv/bin/ngraph run scenario.yaml         # Execute a scenario
```

This avoids shell state issues that agents may not maintain between commands.

### Make Targets (Alternative)

Make targets auto-detect the venv and work without activation:

```bash
make qt                    # Quick tests
make lint                  # Linting checks
```

## Troubleshooting

### Venv Missing or Broken

**Symptom**: Commands fail with "No module named..." or venv/bin/python not found

**Fix**:

```bash
make dev  # Recreates venv if missing, installs all deps
```

Or to fully reset:

```bash
make clean-venv && make dev
```

### Python Version Mismatch

**Symptom**: `make dev` warns about venv Python version != best available

**Fix**: Recreate venv with latest Python:

```bash
make clean-venv && make dev
```

### Import Errors After Pulling Changes

**Symptom**: New imports fail after git pull

**Fix**: Reinstall the package:

```bash
./venv/bin/pip install -e '.[dev]'
```

Or run `make dev` which handles this.

### Pre-commit Hook Failures

**Symptom**: Commit blocked by pre-commit hooks

**Fix**:

1. Run `make format` to auto-fix formatting
2. Run `make check` to see remaining issues
3. Fix manually and commit again

### Tests Pass Locally but Fail in CI

**Symptom**: `make qt` passes but CI fails

**Cause**: `make qt` skips slow tests; CI runs full suite

**Fix**: Run `make test` locally to match CI behavior.
