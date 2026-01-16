# JSON Schema Validation

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [Workflow Reference](workflow.md) — analysis workflow configuration and execution
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

NetGraph includes JSON Schema definitions for YAML scenario files, providing IDE validation, autocompletion, and automated testing.

## Schema Location

The schema is packaged with the library at: **`ngraph/schemas/scenario.json`**.

This file validates NetGraph scenario YAML structure including network topology, blueprints, risk groups, failure policies, traffic matrices, workflows, and components.

## Validation Scope

The schema validates:

- YAML syntax and data types
- Required fields and property structure
- Top-level section organization
- Basic constraint checking

Runtime: The schema is applied unconditionally during load in `ngraph.scenario.Scenario.from_yaml`. Additional business rules are enforced in code (e.g., blueprint expansion) and may still raise errors for semantically invalid inputs.

## IDE Integration (VS Code)

Automatic configuration via `.vscode/settings.json`:

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

- Pre-commit hooks: Validates modified `scenarios/*.yaml` files
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

**Update triggers**:

- New top-level sections added
- Property types or validation rules change
- New workflow step types

**Update process**:

1. Implement feature in `ngraph/scenario.py` validation logic
2. Test runtime validation
3. Update JSON Schema to match implementation
4. Run `make test` to verify schema tests
5. Update documentation

Authority: code implementation in `ngraph/scenario.py` and `ngraph/dsl/blueprints/expand.py` is authoritative, not the schema.
