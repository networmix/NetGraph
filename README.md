# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph is a scenario-driven network modeling and analysis framework in Python.
Define topology, traffic, failures, and workflows in YAML; run analyses from the
CLI or Python API. It scales from small graphs to DC fabrics and WAN backbones.

## Highlights

- Declarative DSL with schema validation (topology, failures, traffic, workflow)
- Blueprints and adjacency rules for concise, reusable topologies
- Strict multidigraph with unique and stable edge IDs; subclass of NetworkX's MultiDiGraph preserving NetworkX APIs
- Read-only NetworkView overlays with node and link masking for failure simulation
- Failure policies with weighted failure modes and multiple policy rules per mode
- Max-flow and demand placement with configurable flow placement strategies to simulate ECMP/WCMP and TE behavior in IP/MPLS networks
- Export of results to structured JSON for downstream analysis
- CLI and complete Python API
- High test coverage

See [Design](https://networmix.github.io/NetGraph/reference/design/) for more details on the internal design of NetGraph.

## Example Scenario (Excerpt)

```yaml
seed: 42
blueprints:
  Clos_L16_S4:
    groups:
      spine: {node_count: 4,  name_template: spine{node_num}}
      leaf:  {node_count: 16, name_template: leaf{node_num}}
    adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_params: {capacity: 3200, cost: 1}
  DCRegion:
    groups:
      dc: {node_count: 1, name_template: dc, attrs: {role: dc}}
network:
  groups:
    metro1/pop[1-2]: {use_blueprint: Clos_L16_S4}
    metro1/dc[1-1]:  {use_blueprint: DCRegion}
  adjacency:
  - source: {path: metro1/pop1}
    target: {path: metro1/dc1}
    pattern: one_to_one
    link_params: {capacity: 2000.0, cost: 1}
workflow:
- step_type: NetworkStats
  name: network_statistics
- step_type: MaximumSupportedDemand
  name: msd_baseline
  matrix_name: baseline_traffic_matrix
- step_type: TrafficMatrixPlacement
  name: tm_placement
  matrix_name: baseline_traffic_matrix
```

See the full scenario at [scenarios/backbone_clos.yml](scenarios/backbone_clos.yml).

## Quick Start

### Install (PyPI package)

```bash
pip install ngraph
```

### Install (from source on GitHub)

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
make dev  # install in editable mode
make check  # run all checks
```

### CLI

```bash
# Inspect a scenario (validate and preview)
ngraph inspect scenarios/backbone_clos.yml --detail

# Run a scenario and save results
ngraph run scenarios/backbone_clos.yml --results clos.results.json
```

### Python API (MaxFlow quick demo)

```python
from ngraph.scenario import Scenario
from ngraph.algorithms.base import FlowPlacement

scenario_yaml = """
seed: 1234
network:
  nodes: {A: {}, B: {}, C: {}, D: {}}
  links:
    - {source: A, target: B, link_params: {capacity: 1, cost: 1}}
    - {source: A, target: B, link_params: {capacity: 2, cost: 1}}
    - {source: B, target: C, link_params: {capacity: 1, cost: 1}}
    - {source: B, target: C, link_params: {capacity: 2, cost: 1}}
    - {source: A, target: D, link_params: {capacity: 3, cost: 2}}
    - {source: D, target: C, link_params: {capacity: 3, cost: 2}}
"""
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network

print(network.max_flow("A", "C"))                          # {('A', 'C'): 6.0}
print(network.max_flow("A", "C", shortest_path=True))      # {('A', 'C'): 3.0}
print(
    network.max_flow(
        "A",
        "C",
        shortest_path=True,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
    )
)  # {('A', 'C'): 2.0}

res = network.max_flow_with_summary("A", "C")
print({k: (v[0], v[1].cost_distribution) for k, v in res.items()})
# {('A', 'C'): (6.0, {2.0: 3.0, 4.0: 3.0})}
```

## Documentation

- **Documentation site**: [networmix.github.io/NetGraph](https://networmix.github.io/NetGraph/)
- **Installation**: [Getting started — Installation](https://networmix.github.io/NetGraph/getting-started/installation/)
- **Tutorial**: [Getting started — Tutorial](https://networmix.github.io/NetGraph/getting-started/tutorial/)
- **Basic example**: [Examples — Basic](https://networmix.github.io/NetGraph/examples/basic/)
- **DSL reference**: [Reference — DSL](https://networmix.github.io/NetGraph/reference/dsl/)
- **Workflow reference**: [Reference — Workflow](https://networmix.github.io/NetGraph/reference/workflow/)
- **CLI reference**: [Reference — CLI](https://networmix.github.io/NetGraph/reference/cli/)
- **API reference**: [Reference — API](https://networmix.github.io/NetGraph/reference/api/)

## License

[GNU Affero General Public License v3.0 or later](LICENSE)
