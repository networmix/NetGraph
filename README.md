# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph computes how much traffic a network can carry: the capacity between sites, how much of a traffic matrix fits, and how both change when links or nodes fail. You describe the network in Python or in YAML; the graph algorithms run in C++ ([NetGraph-Core](https://github.com/networmix/NetGraph-Core)). Results come back as Python objects and export to JSON. If you are building your own tool and want to call the graph algorithms directly, on integer capacities you convert yourself, use [NetGraph-Core](https://github.com/networmix/NetGraph-Core) instead.

## Install

```bash
pip install ngraph
```

NetGraph needs Python 3.11 or later. NetGraph-Core, the C++ engine, is installed with it.

## First example: shortest path versus traffic engineering

Router A reaches router C directly over a 10 Gbit/s link, or through B over two 20 Gbit/s links. Capacities are plain numbers; here they mean Gbit/s. Every link has cost 1. Cost is the routing metric, and the cost of a route is the sum of its link costs: the direct route costs 1, the route through B costs 2.

```text
                B
    20 Gbit/s  / \  20 Gbit/s
              /   \
             A-----C
            10 Gbit/s

         every link: cost 1
```

With no other traffic and nothing failed, how much can A send to C when routers forward only on the lowest-cost route, and how much when traffic engineering may use both routes? The engine counts bandwidth in whole units of a size `q` that NetGraph chooses for the network, so the example multiplies each result by `prepared.topology.q` to print Gbit/s.

```python
import netgraph_core as ngc
from ngraph import CapacityQuery, Link, Network, Node, Scenario, Selector, capacity, prepare

network = Network()
for name in ("A", "B", "C"):
    network.add_node(Node(name))
network.add_link(Link("A", "C", capacity=10, cost=1))
network.add_link(Link("A", "B", capacity=20, cost=1))
network.add_link(Link("B", "C", capacity=20, cost=1))

prepared = prepare(Scenario(network))
a, c = Selector("^A$"), Selector("^C$")
shortest_path = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
for label, query in (
    ("Shortest path", CapacityQuery(a, c, config=shortest_path)),
    ("Optimized TE", CapacityQuery(a, c)),  # the default model
):
    result = capacity(prepared, query)
    # A result has one case per failure pattern. cases[0] is the network with nothing
    # failed, and its one row is the A-to-C answer.
    row = result.cases[0].states["converged"].rows[0]
    print(f"{label}: {row.result.delivered * prepared.topology.q:g} Gbit/s")
```

<!-- example: output -->

```text
Shortest path: 10 Gbit/s
Optimized TE: 30 Gbit/s
```

In the shortest-path model, each router forwards to its lowest-cost next hops and splits traffic equally when several tie. Here the direct link is the only lowest-cost route, so nothing is split: A delivers 10 Gbit/s to C, and the route through B, with twice the capacity, carries nothing because it costs more.

Optimized traffic engineering may put traffic on any route in any split, as an ideal central controller would. It sends 10 Gbit/s over A-C and 20 Gbit/s over A-B-C. That fills both links leaving A, 10 + 20 Gbit/s, so no routing can deliver more than 30.

`prepare` builds the engine's graph once, and each `capacity` call asks one question of it; `ngc.FlowPolicyConfig` selects the routing model. Preparation chooses one `q` for the whole scenario from its physical capacities and traffic, the network size, the traffic splits it prepares and the requested precision; the engine's integer range can force a different `q`. `prepared.units_report` reports that choice and whether the preparation's precision bounds were met, not the accuracy of every result. [Precision and the choice of q](https://networmix.github.io/NetGraph/concepts/#precision-and-the-choice-of-q) gives the exact rule.

## Scenario YAML

A study you want to rerun and share goes into a YAML file: the network, its traffic and the workflow steps that analyse it. This file asks a different question of the same triangle. A has 15 Gbit/s of traffic for C, routed by optimized traffic engineering (`TE_MAXFLOW_UNLIM`, the model a `CapacityQuery` uses by default), and the `max_demand` step finds how far that traffic can be scaled up and still fit. Save it as `triangle.yml`:

```yaml
network:
  nodes: {A: {}, B: {}, C: {}}
  links:
    - {source: A, target: C, capacity: 10, cost: 1}
    - {source: A, target: B, capacity: 20, cost: 1}
    - {source: B, target: C, capacity: 20, cost: 1}
demands:
  traffic:
    - {source: ^A$, target: ^C$, volume: 15, preset: TE_MAXFLOW_UNLIM}
workflow:
  - type: MaximumSupportedDemand
    name: max_demand
    demand_set: traffic
```

Run it in the directory where you saved it:

```bash
ngraph run triangle.yml --output results/
```

The run writes `results/triangle.results.json`. The `max_demand` step records the largest multiplier of the declared traffic that it tested and found to fit, alpha, as an exact fraction: `numerator` and `denominator` under `.result.alpha_feasible`. With jq installed, read it like this:

```bash
jq '.steps[] | select(.name == "max_demand") | .result.alpha_feasible | .numerator / .denominator' results/triangle.results.json
```

<!-- example: output -->

```text
2
```

An alpha of 2 means the 15 Gbit/s fits twice over: 30 Gbit/s, the optimized TE capacity of the first example. `run(prepare(scenario))` returns the same results in Python. Larger studies build networks from blueprints, sample failures and place whole traffic matrices; [Clos Fabric](https://networmix.github.io/NetGraph/examples/clos-fabric/) and [Bundled Scenarios](https://networmix.github.io/NetGraph/examples/bundled-scenarios/) show them, and [How NetGraph computes](https://networmix.github.io/NetGraph/concepts/) explains maximum supported demand, failure sampling and the result fields.

## Capabilities

- **Scenarios**: schema-validated YAML, with blueprints for repeated structures such as Clos fabrics.
- **Failures**: weighted failure modes, shared-risk groups, and exclusions applied at analysis time, so the base topology is never edited.
- **Routing models**: cost-only IP routing with ECMP or WCMP splits, and capacity-aware traffic engineering.
- **Analyses**: maximum flow, maximum supported demand and traffic-matrix placement.
- **Reproducibility**: seeded random sampling and stable link ids.
- **Engine**: graph algorithms in C++ that release the Python GIL, via [NetGraph-Core](https://github.com/networmix/NetGraph-Core).

## Documentation

- [**Tutorial**](https://networmix.github.io/NetGraph/getting-started/tutorial/): run a scenario from the CLI and from Python
- [**How NetGraph computes**](https://networmix.github.io/NetGraph/concepts/): how a scenario becomes numbers
- [**Examples**](https://networmix.github.io/NetGraph/examples/basic/): from a four-node network to the bundled scenarios
- [**Scenario YAML**](https://networmix.github.io/NetGraph/reference/dsl/): every scenario key
- [**Python API**](https://networmix.github.io/NetGraph/reference/api/): the library by task

## License

[MIT License](LICENSE)
