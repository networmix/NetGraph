# Bundled Scenarios

Four scenarios under `scenarios/` exercise the DSL, workflow steps and results export. They are starting points for your own models; each file's opening comment says what it demonstrates, and `square_mesh.yaml` is the smallest.

## How to run

Inspect first, then run:

```bash
# Inspect (structure, steps, demands, failure policies)
ngraph inspect scenarios/backbone_clos.yml --detail

# Run and write JSON results in the current directory (or under --output)
ngraph run scenarios/backbone_clos.yml --output out
```

`--detail` adds full node and link tables and step parameters to `inspect`. `--keys` exports only the named steps ([Filtering Results by Step Names](../reference/cli.md#filtering-results-by-step-names)); each scenario section lists its step names.

## `scenarios/square_mesh.yaml`

- **Purpose**: Toy 4-node full mesh to exercise MSD search, TM placement, and pairwise MaxFlow.
- **Contents**:

  - Failure policy: single link choice (`failures.single_link_failure`)
  - Demand set: pairwise demands across all nodes (`baseline_traffic_matrix`)
  - Workflow steps: `msd_baseline`, `tm_placement`, `node_to_node_capacity_matrix`

Maximum supported demand (MSD) searches for the largest tested feasible demand multiplier; traffic-matrix placement sends the declared demands at a chosen multiplier ([Maximum supported demand](../concepts.md#maximum-supported-demand); [Demands: how traffic enters](../concepts.md#demands-how-traffic-enters)).

Run:

```bash
ngraph inspect scenarios/square_mesh.yaml --detail
ngraph run scenarios/square_mesh.yaml --output out

# Filter to MSD only and print to stdout
ngraph run scenarios/square_mesh.yaml --keys msd_baseline --stdout
```

## `scenarios/readme_example.yml`

- **Purpose**: The README's scenario: two Clos sites built from one blueprint, with MSD and placement under failures.
- **Contents**:

  - Failure policy: one random link per draw (`failures.random_link`)
  - Demand set: site-to-site leaf traffic with ECMP (`global_traffic`)
  - Workflow steps: `max_demand`, `placement_at_max`

Run:

```bash
ngraph inspect scenarios/readme_example.yml --detail
ngraph run scenarios/readme_example.yml --output out
```

## `scenarios/backbone_clos.yml`

- **Purpose**: A five-metro backbone of Clos and single-router PoPs with hardware components, generated risk groups and a four-step workflow.
- **Contents**:

  - Uses `blueprints`, attribute-based link selectors, and hardware component attrs
  - Failure policy: weighted multi-mode (`failures.weighted_modes`)
  - Demand set: inter-metro DC flows with unrestricted optimized TE (`baseline_traffic_matrix`)
  - Workflow steps: `network_statistics`, `msd_baseline`, `tm_placement`, `cost_power`

Run:

```bash
ngraph inspect scenarios/backbone_clos.yml --detail
ngraph run scenarios/backbone_clos.yml --output out

# Export only selected steps
ngraph run scenarios/backbone_clos.yml --keys network_statistics tm_placement --results clos_filtered.json
```

## `scenarios/nsfnet.yaml`

- **Purpose**: The NSFNET T3 backbone in mid-1992 as its sources show it: the map "New T3 Backbone Service, 1992" (in Merit's final report, [NSFNET: A Partnership for High-Speed Networking](https://www.merit.edu/wp-content/uploads/2024/10/Merit-Network_NSFNET-A-Partnership-for-High-Speed-Networking.pdf)) and Merit's [node list of 22 May 1992](https://lists.nanog.org/archives/list/nanog@lists.nanog.org/thread/KG32YBM5M4DNVD6V4ZQEOVJN7KZBMDLN/). A historic network with parallel circuits, risk groups and failure policies.
- **Contents**:

  - 12 core sites (`core/<city>`, `site_type: core`) joined by 15 connections, each site standing for the backbone routers at one MCI junction; 16 end sites at regional networks (`end/<place>`, `site_type: end`), each on a single circuit to its core site
  - Capacities in kbit/s. Every circuit of the time was a DS-3 of 44736 kbit/s, and so is each end site's circuit. Each core connection, one DS-3 in 1992, is modelled as a pair of parallel circuits of 22368 kbit/s, the pair in its own risk group, so every connection carries its 1992 capacity
  - Cost 1 on every circuit: every T3 circuit then had routing metric 1, whatever its length
  - Failure policies: one random circuit per draw (`failures.single_link_failure`; on a core connection, half of it), independent random circuit and site failures at assumed rates, since no source gives the rates of the time (`failures.assumed_random_failures`), and one random risk group per draw (`failures.single_connection_failure`: both circuits of a core connection, the loss of its DS-3)
  - Workflow steps: `node_to_node_capacity_matrix_1`, `node_to_node_capacity_matrix_2`, `node_to_node_capacity_matrix_3`, one per policy in that order
  - Not modelled: the T1 "Safety Net" between core routers, the backup T1 circuits added to end sites later that year, the FIX-West and FIX-East interchanges and ANS's own sites (in the node list, not on the map), and the routers' forwarding limits and the sites' Ethernet and FDDI access: capacities are line rates

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
# The largest tested feasible alpha, its search status and probe history
ngraph run scenarios/square_mesh.yaml --no-results --stdout --keys msd_baseline \
  | jq '.steps[] | select(.name == "msd_baseline") | .result | {alpha_feasible, search_status, history}'

# One line per distinct failure pattern: which links failed, how many
# draws gave it, and the fraction of the demand delivered
ngraph run scenarios/square_mesh.yaml --no-results --stdout --keys tm_placement \
  | jq -c '.steps[] | select(.name == "tm_placement") | .result.cases[]
           | {links: .case.pattern.excluded_links, n: .case.occurrences, ratio: .states.converged.totals.delivery_ratio}'

# Pairwise capacity matrix: 784 rows in the no-failure baseline, one per ordered pair
# of the 28 sites, each site paired with itself included
ngraph run scenarios/nsfnet.yaml --no-results --stdout --keys node_to_node_capacity_matrix_1 \
  | jq '.steps[] | select(.name == "node_to_node_capacity_matrix_1") | .result.cases[0].states.converged.rows | length'

# Capex and power per metro from the components library
ngraph run scenarios/backbone_clos.yml --no-results --stdout --keys cost_power \
  | jq -c '.steps[] | select(.name == "cost_power") | .result.levels[] | select(.level == 1) | .rows[] | {path, capex_total, power_total_watts}'
```

`alpha_feasible` is the largest tested feasible alpha (the demand multiplier), `search_status` names the search outcome and `history` lists every probe ([Maximum supported demand](../concepts.md#maximum-supported-demand)). `delivery_ratio` is delivered traffic divided by the scaled declared request ([Demands: how traffic enters](../concepts.md#demands-how-traffic-enters)); `capex_total` is capital cost and `power_total_watts` is power in watts ([CostPower](../reference/workflow.md#costpower)). Every field is in [Results](../reference/results.md); cases and their occurrences in [Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states), and the kinds of numbers in [Results and their units](../concepts.md#results-and-their-units).
