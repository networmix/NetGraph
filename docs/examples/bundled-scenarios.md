# Bundled Scenarios

NetGraph ships with ready-to-run scenarios that demonstrate the DSL, workflow steps, and results export. Use these to validate your environment and as starting points for your own models.

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
- **Highlights**:

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
- **Highlights**:

  - Uses `blueprints`, attribute-based link selectors, and hardware component attrs
  - Failure policy: weighted multi-mode (`failures.weighted_modes`)
  - Demand set: inter-metro DC flows with TE/WCMP policy
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
- **Highlights**:

  - Explicit nodes/links with capacities and costs; rich `risk_groups`
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
# The largest traffic multiplier that still fits (square_mesh: 1.0)
ngraph run scenarios/square_mesh.yaml --no-results --stdout --keys msd_baseline \
  | jq '.steps.msd_baseline.data.alpha_star'

# One line per distinct failure pattern: which links failed, how many
# iterations drew it, and the fraction of demand still placed
ngraph run scenarios/square_mesh.yaml --no-results --stdout --keys tm_placement \
  | jq -c '.steps.tm_placement.data.flow_results[]
           | {links: .failure_state.excluded_links, n: .occurrence_count, ratio: .summary.overall_ratio}'

# Pairwise capacity matrix: 676 source/destination pairs in the no-failure baseline
ngraph run scenarios/nsfnet.yaml --no-results --stdout --keys node_to_node_capacity_matrix_1 \
  | jq '.steps.node_to_node_capacity_matrix_1.data.baseline.flows | length'

# Capex and power per metro from the components library
ngraph run scenarios/backbone_clos.yml --no-results --stdout --keys cost_power \
  | jq -c '.steps.cost_power.data.levels["1"][] | {path, capex_total, power_total_watts}'
```

The `square_mesh` placement output looks like this (1000 iterations, six single-link patterns):

```text
{"links":["N1|N2|0"],"n":164,"ratio":0.8333333333333334}
{"links":["N3|N4|0"],"n":180,"ratio":0.8333333333333334}
{"links":["N2|N4|0"],"n":165,"ratio":1.0}
{"links":["N2|N3|0"],"n":183,"ratio":0.8333333333333334}
{"links":["N1|N3|0"],"n":164,"ratio":1.0}
{"links":["N1|N4|0"],"n":144,"ratio":0.8333333333333334}
```

## Notes on results

All runs emit a consistent JSON shape with `workflow`, `steps`, and `scenario` sections. Steps like `MaxFlow` and `TrafficMatrixPlacement` store a list under `data.flow_results` with one entry per unique failure pattern - patterns are deduplicated across iterations, so the list holds at most `iterations` entries and usually far fewer - alongside a single unfailed entry under `data.baseline`; with no `failure_policy`, `flow_results` is empty. Each entry carries a `summary` and per-flow `flows` entries whose `cost_distribution` is populated when `include_flow_details` is set (and `{}` otherwise), and with `include_min_cut` the min-cut edges appear under a flow entry's `data` (`edges` plus `edges_kind: "min_cut"`). See Reference -> Workflow for the exact schema.
