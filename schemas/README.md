# NetGraph JSON Schemas

This directory contains JSON Schema definitions for NetGraph YAML scenario files.

## Files

- `scenario.json` - JSON Schema for NetGraph scenario YAML files

## Documentation

For complete documentation on schema usage, validation, IDE setup, and troubleshooting, see:

**[docs/reference/schemas.md](../docs/reference/schemas.md)**

## Quick Start

### VS Code Setup
Add to `.vscode/settings.json`:
```json
{
  "yaml.schemas": {
    "./schemas/scenario.json": ["scenarios/**/*.yaml"]
  }
}
```

### Validation

Schema validation is automatically integrated into all development workflows:

**Manual validation:**

```bash
make validate
```

**Automatic validation** is included in:

- **Pre-commit hooks** - Validates scenarios when changed files include `scenarios/*.yaml`
- **Make check** - Full validation as part of `make check`
- **CI/CD** - GitHub Actions workflow validates scenarios on every push/PR

This ensures all scenario files are validated against `schemas/scenario.json` before code is committed or merged.

## Schema Limitations

The JSON schema validates structure and basic types but has some limitations due to JSON Schema constraints. NetGraph's runtime validation in `ngraph/scenario.py` is the authoritative source for all validation rules. See the [detailed documentation](../docs/reference/schemas.md) for complete limitations and troubleshooting.
