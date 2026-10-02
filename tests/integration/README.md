# Integration Tests

End-to-end tests that load full scenarios, run their workflows, and check the resulting network, demands, failure policies and flows.

## Files

| File | Contents |
|------|----------|
| `scenario_1.yaml` .. `scenario_4.yaml` | The reference scenarios below |
| `test_scenario_1.py` .. `test_scenario_4.py` | One test class per scenario |
| `expectations.py` | Expected node and edge counts and blueprint expansions per scenario (`SCENARIO_*_EXPECTATIONS`) |
| `helpers.py` | `ScenarioTestHelper` (validation methods), `NetworkExpectations`, `ScenarioDataBuilder`, `load_scenario_from_file`, `create_scenario_helper` |
| `test_data_templates.py` | Topology, blueprint, failure, demand and workflow templates, and `ScenarioTemplateBuilder` |
| `test_template_examples.py` | Tests that exercise every template |
| `test_error_cases.py` | Invalid scenarios that must fail to load or run |
| `test_schema_modes.py` | Schema validation of failure-policy `modes` and `weight_by` |

## Scenarios

| Scenario | Nodes | Links | Exercises |
|----------|-------|-------|-----------|
| 1: L3 backbone | 6 | 10 | Explicit nodes and links, demands, single-link failures |
| 2: Hierarchical DSL | 19 | 56 | Blueprints with `params` overrides, mesh patterns, nesting four levels deep |
| 3: 3-tier Clos | 64 | 144 | Nested blueprints, `one_to_one` wiring, node and link rules, risk groups, MaxFlow steps |
| 4: Data center fabric | 80 | 92 | Components and hardware, variable expansion, node and link rules, risk groups, a disabled rack |

Edge counts in the expectations are twice the link counts, because the exported graph holds a forward and a reverse edge per link.

## Writing a scenario test

```python
from .expectations import SCENARIO_1_EXPECTATIONS
from .helpers import create_scenario_helper, load_scenario_from_file

scenario = load_scenario_from_file("scenario_1.yaml")
scenario.run()

helper = create_scenario_helper(scenario)  # attaches the graph exported by BuildGraph
helper.validate_network_structure(SCENARIO_1_EXPECTATIONS)
helper.validate_topology_semantics()
```

`create_scenario_helper` reads the graph from the step named `build_graph`, so the scenario's workflow needs a `BuildGraph` step with that name.

## Which tool to use

- **Scenario tests** load the static YAML files with `load_scenario_from_file()`; they are the integration references.
- **Error case tests** build invalid configurations with `ScenarioDataBuilder`, and use raw YAML only for syntax errors a builder cannot produce.
- **Template examples** exercise the template classes in `test_data_templates.py`.

```python
from .test_data_templates import ScenarioTemplateBuilder

scenario_yaml = (
    ScenarioTemplateBuilder("test", "1.0")
    .with_linear_backbone(["A", "B", "C"])
    .with_uniform_traffic(["A", "C"], 25.0)
    .with_single_link_failures()
    .build()
)
```

Add a template only when a test uses it; templates without callers are removed.

## Running

```bash
pytest tests/integration/ -v
pytest tests/integration/test_scenario_1.py -v
```
