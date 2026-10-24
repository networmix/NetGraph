# Bundled Scenarios

Four scenarios under `scenarios/` exercise the DSL, workflow steps and results export. They are starting points for your own models; `readme_example.yml` is the smallest.

## How to run

Inspect first, then run:

```bash
# Inspect (structure, steps, demands, failure policies)
ngraph inspect scenarios/backbone_clos.yml --detail

# Run and write JSON results in the current directory (or under --output)
ngraph run scenarios/backbone_clos.yml --output out
```

You can filter output by workflow step names with `--keys` (see each scenario section for step names).

## `scenarios/square_mesh.yaml`

- **Purpose**: Toy 4-node full mesh to exercise MSD search, TM placement, and pairwise MaxFlow.
- **Contents**:

  - Failure policy: single link choice (`failures.single_link_failure`)
  - Demand set: pairwise demands across all nodes (`baseline_traffic_matrix`)
  - Workflow steps: `msd_baseline`, `tm_placement`, `node_to_node_capacity_matrix`

Run:

```bash
ngraph inspect scenarios/square_mesh.yaml --detail
ngraph run scenarios/square_mesh.yaml --output out

# Filter to MSD only and print to stdout
ngraph run scenarios/square_mesh.yaml --keys msd_baseline --stdout
```

## `scenarios/backbone_clos.yml`

- **Purpose**: Small Clos/metro fabric with components, SRLG-like risk groups, and multi-step workflow.
- **Contents**:

  - Uses `blueprints`, attribute-based link selectors, and hardware component attrs
  - Failure policy: weighted multi-mode (`failures.weighted_modes`)
  - Demand set: inter-metro DC flows with unrestricted optimized TE
  - Workflow steps: `network_statistics`, `msd_baseline`, `tm_placement`, `cost_power`

Run:

```bash
ngraph inspect scenarios/backbone_clos.yml --detail
ngraph run scenarios/backbone_clos.yml --output out

# Export only selected steps
ngraph run scenarios/backbone_clos.yml --keys network_statistics tm_placement --results clos_filtered.json
```

## `scenarios/nsfnet.yaml`

- **Purpose**: Historic NSFNET T3 (1992) backbone with parallel circuits and SRLG-style risk groups.
- **Contents**:

  - Explicit nodes and links with capacities and costs; one risk group per circuit pair
  - Failure policies: single-link and availability-based random failures
  - Workflow steps: `node_to_node_capacity_matrix_1`, `node_to_node_capacity_matrix_2`

Run:

```bash
ngraph inspect scenarios/nsfnet.yaml --detail
ngraph run scenarios/nsfnet.yaml --output out

# Filter to a specific matrix computation
ngraph run scenarios/nsfnet.yaml --keys node_to_node_capacity_matrix_1 --stdout
```

## Reading the results

`--stdout` prints only the JSON, so it pipes into `jq`:

```bash
# The largest traffic multiplier actually tested feasible, with its probe history
ngraph run scenarios/square_mesh.yaml --no-results --stdout --keys msd_baseline \
  | jq '.steps[] | select(.name == "msd_baseline") | .result | {alpha_feasible, search_status, history}'

# One line per distinct failure pattern: which links failed, how many
# iterations drew it, and the fraction of demand still placed
ngraph run scenarios/square_mesh.yaml --no-results --stdout --keys tm_placement \
  | jq -c '.steps[] | select(.name == "tm_placement") | .result.cases[]
           | {links: .case.pattern.excluded_links, n: .case.occurrences, ratio: .states.converged.totals.delivery_ratio}'

# Pairwise capacity matrix: 676 source/destination pairs in the no-failure baseline
ngraph run scenarios/nsfnet.yaml --no-results --stdout --keys node_to_node_capacity_matrix_1 \
  | jq '.steps[] | select(.name == "node_to_node_capacity_matrix_1") | .result.cases[0].states.converged.rows | length'

# Capex and power per metro from the components library
ngraph run scenarios/backbone_clos.yml --no-results --stdout --keys cost_power \
  | jq -c '.steps[] | select(.name == "cost_power") | .result.levels[] | select(.level == 1) | .rows[] | {path, capex_total, power_total_watts}'
```

## Notes on results

Every run exports producer metadata, the units report and an ordered `steps` array. Each step records its normalized question and actual execution order. `--keys` filters that array after execution; retained orders may have gaps.

Capacity and placement results contain a baseline case followed by distinct sampled physical failure patterns. Each case records occurrences and a `states` mapping: `converged` for capacity, the requested failure states (by default `converged`) for placement. Without sampling there is only the baseline. Demand totals and delivery ratios remain exact integers and rational pairs. Native flow arrays, cuts and tagged cost distributions appear only when requested. MSD reports the largest tested feasible alpha and the complete compact probe history. The [Workflow Reference](../reference/workflow.md) describes the settings and the [API guide](../reference/api.md) shows typed access.
