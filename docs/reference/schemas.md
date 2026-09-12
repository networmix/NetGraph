# JSON Schema Validation

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [Workflow Reference](workflow.md) — analysis workflow configuration and execution
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

A JSON Schema describes the scenario YAML. It drives load-time validation, IDE completion, and tests.

## Schema Location

The schema is packaged with the library at: **`ngraph/schemas/scenario.json`**.

This file validates NetGraph scenario YAML structure including network topology, blueprints, risk groups, failure policies, traffic matrices, workflows, and components.

## Validation Scope

The schema validates:

- YAML syntax and data types
- Required fields and property structure
- Top-level section organization
- Basic constraint checking

`Scenario.from_yaml` always validates against the schema (in `ngraph.dsl.loader.load_scenario_yaml`) before expansion. Rules the schema cannot express, such as blueprint parameter names or risk-group references, are checked in code and raise `ValueError`.

## IDE Integration (VS Code)

Add to `.vscode/settings.json` (not committed to the repository):

```json
{
  "yaml.schemas": {
    "./ngraph/schemas/scenario.json": [
      "scenarios/**/*.yaml",
      "scenarios/**/*.yml"
    ]
  }
}
```

Provides real-time validation, autocompletion, inline documentation, and error highlighting.

## Automated Validation

### Development Workflow

```bash
# Validate all scenarios
make validate

# Full validation and tests
make check
```

### Integration Points

- Pre-commit hooks: Runs `make validate` when `scenarios/*.yaml` files change
- CI pipeline: Validates scenarios on push/PR
- Test suite: Validation exercised in integration tests

### Python API

```python
import json
import yaml
import jsonschema

# Load and validate
from importlib import resources as res

with res.files('ngraph.schemas').joinpath('scenario.json').open('r', encoding='utf-8') as f:
    schema = json.load(f)

with open('scenarios/square_mesh.yaml') as f:
    data = yaml.safe_load(f)

jsonschema.validate(data, schema)
```

## Schema Structure

**Top-level sections** (only these keys allowed):

- `network` - Network topology definition
- `blueprints` - Reusable network templates
- `risk_groups` - Risk group definitions
- `failures` - Named failure policies
- `demands` - Named demand sets
- `workflow` - Workflow step definitions
- `components` - Hardware component library
- `vars` - YAML anchors and variables for reuse
- `seed` - Master random seed for reproducibility

## Schema Maintenance

Update the schema whenever a top-level section, a field's type, or a workflow step type changes, then run `make test` (the integration tests load every bundled scenario and the DSL examples). The code is authoritative: `ngraph/dsl/loader.py` validates, and `ngraph/dsl/blueprints/expand.py` and the model classes enforce what the schema cannot express.
