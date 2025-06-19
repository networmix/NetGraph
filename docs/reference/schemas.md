# JSON Schema Validation

NetGraph includes JSON Schema definitions for YAML scenario files to provide IDE validation, autocompletion, and documentation.

## Overview

The schema system provides:

- **IDE Integration**: Real-time validation and autocompletion in VS Code and other editors
- **Programmatic Validation**: Schema validation in tests and CI/CD pipelines
- **Documentation**: Machine-readable documentation of the NetGraph YAML format
- **Error Prevention**: Catches common YAML structure mistakes before runtime

## Schema Files

### `schemas/scenario.json`

The main schema file that validates NetGraph scenario YAML files including:

- **Network topology** (`network` section) with support for direct links, adjacency rules, and variable expansion
- **Blueprint definitions** (`blueprints` section) for reusable network templates
- **Risk groups** (`risk_groups` section) with hierarchical nesting support
- **Failure policies** (`failure_policy_set` section) with configurable rules and conditions
- **Traffic matrices** (`traffic_matrix_set` section) with extended demand properties
- **Workflow steps** (`workflow` section) with flexible step parameters
- **Component libraries** (`components` section) for hardware modeling

## Schema Validation Limitations

While the schema validates most NetGraph features, there are some limitations due to JSON Schema constraints:

### Group Validation
The schema allows all group properties but **runtime validation is stricter**:
- Groups with `use_blueprint`: only allow `{use_blueprint, parameters, attrs, disabled, risk_groups}`
- Groups without `use_blueprint`: only allow `{node_count, name_template, attrs, disabled, risk_groups}`

This means some YAML that passes schema validation may still be rejected at runtime.

### Conditional Validation
JSON Schema cannot express all NetGraph's conditional validation rules. The runtime implementation in `ngraph/scenario.py` is the authoritative source of truth for validation logic.

## IDE Setup

### VS Code Configuration

NetGraph automatically configures VS Code to use the schema for scenario files. The configuration is in `.vscode/settings.json`:

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

This enables:
- ✅ Real-time YAML validation
- ✅ IntelliSense autocompletion
- ✅ Inline documentation on hover
- ✅ Error highlighting

### Other Editors

For editors that support JSON Schema:

1. **IntelliJ/PyCharm**: Configure YAML schema mappings in Settings
2. **Vim/Neovim**: Use plugins like `coc-yaml` or `yaml-language-server`
3. **Emacs**: Use `lsp-mode` with `yaml-language-server`

## Programmatic Validation

Schema validation is integrated into all NetGraph development workflows to ensure YAML files are valid before code is committed or deployed.

### Automatic Validation

Schema validation runs automatically in:

- **Pre-commit hooks** - Validates scenarios when `scenarios/*.yaml` files are modified
- **Make check** - Full validation as part of the complete check suite
- **CI/CD pipeline** - GitHub Actions validates scenarios on every push and pull request

### Manual Validation

Validate all scenario files in the `scenarios/` directory:

```bash
make validate
```

This command automatically discovers and validates all `*.yaml` files in the `scenarios/` directory against the `schemas/scenario.json` schema. It reports the number of files validated and any validation errors found.

### Python API

```python
import json
import yaml
import jsonschema

# Load schema
with open('schemas/scenario.json') as f:
    schema = json.load(f)

# Validate a scenario file
with open('scenarios/example.yaml') as f:
    data = yaml.safe_load(f)

jsonschema.validate(data, schema)
```

### Testing

The schema is automatically tested against known good scenario files:

```bash
make test
```

### Test Suite

NetGraph includes schema validation tests in `tests/test_schema_validation.py`:

- **Valid scenario testing**: Validates `scenarios/simple.yaml` and test scenarios
- **Error detection**: Tests that invalid YAML is properly rejected
- **Consistency verification**: Ensures schema validation aligns with NetGraph runtime validation
- **Structure validation**: Tests risk groups, failure policies, and all major sections

The test suite validates both that:
1. Valid NetGraph YAML passes schema validation
2. Invalid structures are correctly rejected

## Schema Structure

The schema validates the top-level structure where only these keys are allowed:

- `network` - Network topology definition
- `blueprints` - Reusable network blueprints
- `risk_groups` - Risk group definitions
- `failure_policy_set` - Named failure policies
- `traffic_matrix_set` - Named traffic matrices
- `workflow` - Workflow step definitions
- `components` - Hardware component library

### Key Validation Rules

#### Network Links
- ✅ **Direct links**: Support `source`, `target`, `link_params`, and optional `link_count`
- ✅ **Link overrides**: Support `any_direction` for bidirectional matching
- ❌ **Invalid**: `any_direction` in direct links (use `link_count` instead)

#### Adjacency Rules
- ✅ **Variable expansion**: Support `expand_vars` and `expansion_mode` for dynamic adjacency
- ✅ **Patterns**: Support `mesh` and `one_to_one` connectivity patterns
- ✅ **Link parameters**: Full support for capacity, cost, disabled, risk_groups, and attrs

#### Traffic Demands
- ✅ **Extended properties**: Support priority, demand_placed, mode, flow_policy_config, flow_policy, and attrs
- ✅ **Required fields**: Must have `source_path`, `sink_path`, and `demand`

#### Risk Groups Location
- ✅ **Correct**: `risk_groups` at file root level
- ✅ **Correct**: `risk_groups` under `link_params`
- ❌ **Invalid**: `risk_groups` inside `attrs`

#### Required Fields
- Risk groups must have a `name` field
- Links must have `source` and `target` fields
- Workflow steps must have `step_type` field

#### Data Types
- Capacities and costs must be numbers
- Risk group names must be strings
- Boolean fields validate as true/false

## Benefits

### Developer Experience
- **Immediate Feedback**: See validation errors as you type
- **Autocompletion**: Discover available properties and values
- **Documentation**: Hover tooltips explain each property
- **Consistency**: Ensures all team members use the same format

### Code Quality
- **Early Error Detection**: Catch mistakes before runtime
- **Automated Testing**: Schema validation in CI/CD pipelines
- **Standardization**: Enforces consistent YAML structure
- **Maintainability**: Schema serves as living documentation

## Maintenance

The schema should be updated when:

- New top-level sections are added to NetGraph
- New properties are added to existing sections
- Property types or validation rules change
- New workflow step types are added
- New adjacency patterns or expansion modes are introduced
- Traffic demand properties are extended

**Important**: The implementation in `ngraph/scenario.py` and `ngraph/blueprints.py` is the authoritative source of truth. When updating the schema:

1. **Code First**: Implement the feature in NetGraph's validation logic
2. **Test**: Ensure the runtime validation works correctly
3. **Schema Update**: Extend the JSON Schema to match the implementation
4. **Test Schema**: Run `make test`
5. **Document**: Update this documentation and the DSL reference

## Troubleshooting

### Schema Not Working in IDE

1. **Check Extension**: Ensure YAML Language Support extension is installed
2. **Reload Window**: Try reloading VS Code window
3. **Check Path**: Verify the schema path in `.vscode/settings.json` is correct
4. **File Association**: Ensure `.yaml` files are associated with YAML language mode

### Validation Errors

- **"Property X is not allowed"**: The property is at the wrong level or misspelled
- **"Missing property Y"**: A required field is missing
- **"Type mismatch"**: Wrong data type (e.g., string instead of number)

### False Positives

If you see validation errors for valid NetGraph YAML:

1. **Check NetGraph Version**: Ensure schema matches your NetGraph version
2. **Runtime vs Schema**: Some valid YAML may pass schema but fail runtime validation (see Schema Validation Limitations above)
3. **Report Issue**: The schema may need updating for new features
4. **Disable Temporarily**: Add `# yaml-language-server: disable` to file top

### False Negatives

If the schema accepts YAML that NetGraph rejects:

1. **Group Properties**: Check if you're mixing `use_blueprint` with `node_count`/`name_template`
2. **Link Properties**: Verify you're not using `any_direction` in direct links
3. **Runtime Validation**: Remember that NetGraph's runtime validation is stricter than the schema

### Performance

Schema validation is lightweight and fast:

- **IDE validation**: Real-time with minimal overhead
- **Pre-commit**: Validates only changed `scenarios/*.yaml` files
- **CI/CD**: Completes in seconds for typical scenario files
- **Make validate**: Processes all scenarios quickly

Report any performance issues or false positives/negatives as GitHub issues.
