# JSON Schema Validation

> **📚 Quick Navigation:**
>
> - **[DSL Reference](dsl.md)** - YAML syntax for scenario definition
> - **[Workflow Reference](workflow.md)** - Analysis workflow configuration and execution
> - **[CLI Reference](cli.md)** - Command-line tools for running scenarios
> - **[API Reference](api.md)** - Python API for programmatic scenario creation
> - **[Auto-Generated API Reference](api-full.md)** - Complete class and method documentation

NetGraph includes JSON Schema definitions for YAML scenario files, providing IDE validation, autocompletion, and automated testing.

## Schema Location

**`schemas/scenario.json`**: Main schema file validating NetGraph scenario YAML structure including network topology, blueprints, risk groups, failure policies, traffic matrices, workflows, and components.

## Validation Scope

The schema validates:

- YAML syntax and data types
- Required fields and property structure
- Top-level section organization
- Basic constraint checking

**Limitations**: Runtime validation in `ngraph/scenario.py` is authoritative. Some YAML may pass schema validation but fail at runtime due to business logic constraints.

## Schema Validation Rules

### Group Properties

- Groups with `use_blueprint`: Allow only `{use_blueprint, parameters, attrs, disabled, risk_groups}`
- Groups without `use_blueprint`: Allow only `{node_count, name_template, attrs, disabled, risk_groups}`

### Network Links

- Direct links: `source`, `target`, `link_params`, optional `link_count`
- Link overrides: Support `any_direction` for bidirectional matching
- Invalid: `any_direction` in direct links

### Required Fields

- Risk groups: `name` field
- Links: `source` and `target` fields
- Workflow steps: `step_type` field
- Traffic demands: `source_path`, `sink_path`, `demand` fields

## IDE Integration

### VS Code Setup

Automatic configuration via `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "./schemas/scenario.json": [
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
- CI/CD pipeline: Validates scenarios on push/PR
- Test suite: `tests/test_schema_validation.py`

### Python API

```python
import json
import yaml
import jsonschema

# Load and validate
with open('schemas/scenario.json') as f:
    schema = json.load(f)

with open('scenarios/example.yaml') as f:
    data = yaml.safe_load(f)

jsonschema.validate(data, schema)
```

## Schema Structure

**Top-level sections** (only these keys allowed):

- `network` - Network topology definition
- `blueprints` - Reusable network templates
- `risk_groups` - Risk group definitions
- `failure_policy_set` - Named failure policies
- `traffic_matrix_set` - Named traffic matrices
- `workflow` - Workflow step definitions
- `components` - Hardware component library

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

**Authority**: Code implementation in `ngraph/scenario.py` and `ngraph/blueprints.py` is authoritative, not the schema.
