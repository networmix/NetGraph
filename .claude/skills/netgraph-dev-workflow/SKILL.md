---
name: netgraph-dev-workflow
description: >
  NetGraph development workflow for running tests, linting, and validation.
  Use when: setting up dev environment, running tests or lint, fixing CI failures,
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
