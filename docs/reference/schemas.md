# JSON Schema Validation

Quick links:

- [Design](design.md) - architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) - YAML syntax for scenario definition
- [Workflow Reference](workflow.md) - analysis workflow configuration and execution
- [CLI Reference](cli.md) - command-line tools for running scenarios
- [API Reference](api.md) - Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) - complete class and method documentation

Packaged JSON Schemas describe scenario inputs and exported results. They drive validation, IDE completion, and tests.

## Schema Location

`ngraph/schemas/scenario.json` covers scenario inputs; `ngraph/schemas/results.json` covers the single JSON export path. Both ship in the installed package.

## Validation Scope

The schema checks value types, required fields, allowed keys and simple constraints such as enumerations and minimums.

`Scenario.from_yaml` always validates against the schema (in `ngraph.dsl.loader.load_scenario_yaml`) before expansion. Rules the schema cannot express are checked in code and raise `ValueError`: blueprint parameter names, risk-group references, and unrecognized keys in sections whose schema allows additional properties, such as workflow step parameters.

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

The YAML extension then validates and completes scenario files as you type.

## Validation in Development

```bash
# Validate all scenarios
make validate

# Full validation and tests
make check
```

`ngraph/schemas/results.json` is generated: `python dev/generate_results_schema.py` writes it from the result record declarations (plain records and their `Annotated` refinements) and the explicit fragments in `dev/explicit_results_schema.json`; `make validate` fails when the committed file differs. The pre-commit hook runs `make validate` when scenario or integration YAML files, or the schema, change; CI runs it on every push and pull request, and the integration tests load every bundled scenario.

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
- `routes` - Named explicit routes
- `supports` - Named forwarding supports
- `weights` - Named edge weights
- `units` - Automatic or manual quantum and precision target
- `routing`, `wcmp_controller`, `forwarding_groups` - The WCMP controller's domain, scope and group trees

Unknown input keys are refused with their location. Stale/repair states, simultaneous forwarding and tunnel-count queries are not accepted inputs. Native tunnel-count settings inside a supported flow model remain valid.

## Schema Maintenance

Update the schema whenever a top-level section, a field's type, or a workflow step type changes, then run `make validate` (checks every bundled scenario and integration YAML against the schema) and `make test`. The code is authoritative: `ngraph/dsl/loader.py` validates, and `ngraph/dsl/blueprints/expand.py` and the model classes enforce what the schema cannot express.


## Result detail selection

The result schema checks the enclosing analysis `outputs.details` against its rows: false forbids native detail fields, true requires the complete selected field group. Scalar drop totals remain exact in compact rows. Nullable row `pool` metadata is required in both modes; per-source/tunnel/plan detail lists keep their native applicability when selected. Native array/cut flags and cost-report selection remain independent. MSD history remains compact regardless of detail selection. Question models carry `controller` (the scope of a
controller-programmed demand, null otherwise); placement and MSD analyses of a controlled demand set add a
`controller` list of tables; every units report carries `weight_approximations`, empty unless controller weights
reached 2^62.
