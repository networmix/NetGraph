# Bundled Scenarios

NetGraph ships with ready-to-run scenarios that demonstrate the DSL, workflow steps, and results export. Use these to validate your environment and as starting points for your own models.

## How to run

Inspect first, then run:

```bash
# Inspect (structure, steps, matrices, failure policies)
ngraph inspect scenarios/backbone_clos.yml --detail

# Run and write JSON results next to the scenario (or under --output)
ngraph run scenarios/backbone_clos.yml --output out
```

You can filter output by workflow step names with `--keys` (see each scenario section for step names).

## `scenarios/square_mesh.yaml`

- **Purpose**: Toy 4-node full mesh to exercise MSD search, TM placement, and pairwise MaxFlow.
- **Highlights**:

  - Failure policy: single link choice (`failure_policy_set.single_link_failure`)
  - Traffic matrix: pairwise demands across all nodes (`baseline_traffic_matrix`)
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

  - Uses `blueprints`, attribute-based adjacency selectors, and hardware component attrs
  - Failure policy: weighted multi-mode (`failure_policy_set.weighted_modes`)
  - Traffic matrix: inter-metro DC flows with TE/WCMP policy
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

## Notes on results

All runs emit a consistent JSON shape with `workflow`, `steps`, and `scenario` sections. Steps like `MaxFlow` and `TrafficMatrixPlacement` store per-iteration lists under `data.flow_results` with `summary` and optional `cost_distribution` or `min_cut` fields. See Reference → Workflow for the exact schema.
