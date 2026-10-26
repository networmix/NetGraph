# Basic Example

The network below has two parallel links on each hop of the cheap route, and one longer route:

```text
    capacity 1+2, cost 1    capacity 1+2, cost 1
  A --------------------- B --------------------- C
   \                                             /
    +---------------- D ------------------------+
      capacity 3, cost 2      capacity 3, cost 2
```

## Build and prepare

```python
import netgraph_core as ngc
from ngraph import (
    CapacityQuery, Link, Network, Node, Scenario, Selector, UnitsSettings,
    capacity, prepare,
)

network = Network()
for name in ("A", "B", "C", "D"):
    network.add_node(Node(name))
for source, target, amount, cost in (
    ("A", "B", 1, 1), ("A", "B", 2, 1),
    ("B", "C", 1, 1), ("B", "C", 2, 1),
    ("A", "D", 3, 2), ("D", "C", 3, 2),
):
    network.add_link(Link(source, target, amount, cost))
prepared = prepare(Scenario(network, units=UnitsSettings(resolution=1)))
source, target = Selector("^A$"), Selector("^C$")
```

`UnitsSettings(resolution=1)` sets the bandwidth unit `q` to 1, so result units equal physical bandwidth here ([Units and the resolution q](../concepts.md#units-and-the-resolution-q)). For capacities this small, `q` = 1 misses the default precision target although nothing is rounded, so `prepared.units_report.target_met` is false ([Precision and the choice of q](../concepts.md#precision-and-the-choice-of-q)). `netgraph_core`, imported as `ngc`, is the engine; its native objects configure the models below ([Native models and capacity](../reference/api.md#native-models-and-capacity)). The prepared scenario keeps a read-only view of the network; later edits of the network require a new preparation ([Scenario, preparation and run](../concepts.md#scenario-preparation-and-run)).

## Ask distinct capacity questions

```python
ideal = capacity(prepared, CapacityQuery(source, target))
shortest = capacity(prepared, CapacityQuery(source, target, config=
    ngc.FlowPolicyConfig(routing=ngc.ShortestPaths(
        allocation=ngc.RouteAllocation.OPTIMIZED,
    )),
))
equal = capacity(prepared, CapacityQuery(source, target, config=
    ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
))
assert ideal.cases[0].states["converged"].rows[0].result.delivered == 6
assert shortest.cases[0].states["converged"].rows[0].result.delivered == 3
assert equal.cases[0].states["converged"].rows[0].result.delivered == 2
```

The default question, optimized traffic engineering, uses both routes: 3 units on each. Optimized shortest-path routing uses only the cheap route, whose parallel links sum to 3. Equal splitting admits 2, because each capacity-1 parallel link receives half the traffic. Capacity-weighted splitting (`SHORTEST_PATHS_WCMP`) carries the full 3 on the cheap route. Each `ngc.FlowPolicyConfig` names one model ([Routing models and admission](../concepts.md#routing-models-and-admission)).

## Request cost information

```python
reported = capacity(prepared, CapacityQuery(
    source, target, export_cost_distribution=True,
    outputs=ngc.OutputOptions(min_cut=True),
))
row = reported.cases[0].states["converged"].rows[0]
assert row.cost_distribution.kind == "marginal_curve"
assert [(piece.marginal_cost, piece.units)
        for piece in row.cost_distribution.bins] == [(2, 3), (4, 3)]
assert row.result.delivered == 6
assert [prepared.topology.edge_refs[edge].link for edge in row.result.min_cut] == [
    "A|B|0", "A|B|1", "A|D|0",
]
```

The minimum-cost objective is 3×2 + 3×4 = 18. The cut lists engine edge ids; `prepared.topology.edge_refs` names their links: the two A→B members and A→D, capacity 1 + 2 + 3 = 6. `export_cost_distribution=True` asks for the cost report, here the optimized question's marginal cost pieces, and `ngc.OutputOptions(min_cut=True)` for the cut; both are requested explicitly ([Results and their units](../concepts.md#results-and-their-units); [Results and export](../reference/api.md#results-and-export)).

## Sample failures on the same prepared graph

```python
from ngraph import FailureMode, FailurePolicy, FailureRequest, FailureRule

policy = FailurePolicy(modes=[FailureMode(1, [
    FailureRule("node", mode="all", path="^B$"),
])])
result = capacity(prepared, CapacityQuery(
    source, target, failures=FailureRequest(policy, iterations=3, seed=42),
))
baseline, failed = result.cases
assert baseline.states["converged"].rows[0].result.delivered == 6
assert failed.states["converged"].rows[0].result.delivered == 3
assert failed.case.pattern.excluded_nodes == ("B",)
assert (baseline.case.occurrences, failed.case.occurrences) == (0, 3)
```

`FailureRequest(policy, iterations=3, seed=42)` draws the policy three times. All three draws give one physical pattern, evaluated once, and the baseline has zero sampled occurrences ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states)).

## Read native paths

```python
from ngraph import PathQuery, paths

found = paths(prepared, PathQuery(source, target))
assert found.rows[0].cost == 2
assert found.rows[0].paths[0].cost() == 2
alternatives = paths(prepared, PathQuery(
    source, target, options=ngc.KspOptions(3, parallel_edges=False),
))
assert [path.cost() for path in alternatives.rows[0].paths] == [2, 4]
```

Each path lists its hops by the engine's edge ids; `prepared.topology.edge_refs` maps them to physical links and directions. Native options control parallel-edge choices, cost ceilings, residuals and masks: `ngc.KspOptions(3, parallel_edges=False)` asks for up to three paths that differ in their nodes ([Paths and sensitivity](../reference/api.md#paths-and-sensitivity)).

## Place declared traffic and export

```python
from ngraph import DemandSet, DemandSpec, PlacementQuery, place, write_json
from io import StringIO

traffic = DemandSet("traffic", (
    DemandSpec(source, target, volume=6),
))
loaded = prepare(Scenario(network, demand_sets={"traffic": traffic},
                          units=UnitsSettings(resolution=1)),
                 demand_sets=("traffic",))
placed = place(loaded, PlacementQuery(loaded.demand_sets["traffic"]))
state = placed.cases[0].states["converged"]
assert state.totals.reference_request_units == 6
assert state.totals.delivered_units == 2
assert state.totals.reference_shortfall_units == 4
output = StringIO()
write_json(placed, output)
```

A `PlacementQuery` places a resolved demand set ([Demands: how traffic enters](../concepts.md#demands-how-traffic-enters); [Demands and placement](../reference/api.md#demands-and-placement)). The default demand model is lossless shortest-path ECMP. The remaining 4 units are unadmitted: lossless admission refuses them before they enter the network ([Routing models and admission](../concepts.md#routing-models-and-admission)). See the [tutorial](../getting-started/tutorial.md) for workflow execution and the [API](../reference/api.md) for the other native models.
