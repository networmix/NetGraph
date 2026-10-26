# Python API

NetGraph accepts typed model and query values. YAML dictionaries end at parsing. This guide shows the library by task; the [generated reference](api-full.md) lists every public name, and [Scenario YAML](dsl.md), [Workflow Steps](workflow.md) and [Command Line](cli.md) describe the file and command boundaries.

## Prepare and query

```python
from ngraph import (
    CapacityQuery, Link, Network, Node, Scenario, Selector, UnitsSettings,
    capacity, prepare,
)

network = Network()
for name in ("A", "B", "C"):
    network.add_node(Node(name))
network.add_link(Link("A", "B", capacity=10, cost=1))
network.add_link(Link("B", "C", capacity=5, cost=2))
prepared = prepare(Scenario(network, units=UnitsSettings(resolution=1)))
result = capacity(prepared, CapacityQuery(Selector("^A$"), Selector("^C$")))
row = result.cases[0].states["converged"].rows[0]
assert row.result.delivered == 5
assert prepared.topology.q == 1
```

`Network` keeps editable dicts of immutable records. `prepare` resolves the selected demand sets, builds one native graph and returns `PreparedScenario`; it does not change its input. Library callers name needed demand sets with `prepare(scenario, demand_sets=("traffic",))`; workflow-referenced sets are included automatically.

`PreparedScenario` holds the read-only scenario view, its `topology`, the bound `demand_sets` and the preparation's `units_report`. `PreparedTopology` holds the graph and its labels: `graph`, physical node names, read-only node-name and physical-link mappings, `edge_refs` in native edge order, nominal disabled eligibility, `q` (the bandwidth unit; [Units and the resolution q](../concepts.md#units-and-the-resolution-q)) and `pool_heads` (each finite TE ingress pool's synthetic head node; [Tunnels and TE ingress pools](../concepts.md#tunnels-and-te-ingress-pools)). Every analysis takes the prepared scenario, holds it as `prepared` and returns its own precision `misses`; its `units_report` is the preparation's report with those misses appended. A physical link has two native directions; `DirectedLink(link, direction)` identifies one. Returned native results retain their graph and remain readable after working policies are removed. The prepared view is read-only, and later edits need a new preparation ([Scenario, preparation and run](../concepts.md#scenario-preparation-and-run)).

## Native models and capacity

`CapacityQuery` defaults to uncapped, lossless optimized traffic engineering. `mode="combine"` asks one source-set/destination-set question; `"pairwise"` asks each canonical selector-group pair independently. `Selector(group_by="name", path="^source")` makes one group per matching node. Non-diagonal endpoint overlap refuses; a singleton self pair has its own zero-valued `SelfPair` row.

Supply a native configuration to ask another routing question:

```python
import netgraph_core as ngc

equal = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
weighted = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths(
    allocation=ngc.RouteAllocation.WEIGHTED,
    weight_basis=ngc.WeightBasis.CAPACITY,
))
query = CapacityQuery(Selector("^A$"), Selector("^C$"), config=equal)
equal_result = capacity(prepared, query)
```

The normalized question records the effective model, finite offer/design inputs and failure request. How each model routes and admits traffic: [Routing models and admission](../concepts.md#routing-models-and-admission). `offer` and `design_demand` are optional physical inputs; the analysis labels the question it actually asked ([MaxFlow](workflow.md#maxflow)). Native integer-valued configuration fields already contain units ([Results and their units](../concepts.md#results-and-their-units)).

## Demands and placement

```python
from ngraph import DemandSet, DemandSpec, PlacementQuery, place

traffic = DemandSet("traffic", (
    DemandSpec(Selector("^A$"), Selector("^C$"), volume=4, id="service"),
))
loaded = prepare(Scenario(network, demand_sets={"traffic": traffic},
                          units=UnitsSettings(resolution=1)),
                 demand_sets=("traffic",))
placement = place(loaded, PlacementQuery(loaded.demand_sets["traffic"]))
assert placement.cases[0].states["converged"].totals.delivered_units == 4
```

`DemandSpec` accepts a declared preset, native configuration or named `PinnedRoutes`. Priorities sort ascending; declaration and canonical expansion order break ties. IDs are unique throughout a run. Missing IDs use the set name and source declaration ordinal, with stable indices for explicit expansion and resolved leaves. Grouped splitting preserves each quantized parent total, including reported discarded shares ([Demands: how traffic enters](../concepts.md#demands-how-traffic-enters)).

With `routing=RoutingDomain(...)`, `wcmp_controller=WCMPController(scope)` and `forwarding_groups` of
`ForwardingGroup(router, (ControllerGroup(children, share), ...))` (children are `GroupChild(share, edge=...)` or
nested `GroupChild(share, children=...)`; shares are exact), every `SHORTEST_PATHS_WCMP` demand forwards on the
controller's table toward its destination ([Routing domains and the WCMP controller](../concepts.md#routing-domains-and-the-wcmp-controller)).
`ResolvedDemandSet.controller` holds the tables (programmed routers and their member weights, and for `all_routers`
each source's nominal volume and weight). On such a set `place` accepts failure policies, and a dead group's cap is
reported under `dead_caps` ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states)).
`capacity` refuses `SHORTEST_PATHS_WCMP` as its declaration.

## MSD

`maximum_supported_demand(prepared, MSDQuery(resolved_set))` searches for the largest tested feasible alpha (the demand-volume multiplier) of a resolved demand set ([Maximum supported demand](../concepts.md#maximum-supported-demand)). Read `alpha_feasible` as the largest tested feasible factor, or `None` when none was found. `history` contains every actual probe. `search_status` is one of `feasible`, `none_feasible`, `range`, `stagnation`, `limit`, `trivial`; `stop_reason` explains the termination. Python callers may request `export_probe_rows=True`; YAML has no such input.

## Tunnel counts

```python
from ngraph import DemandSet, DemandSpec, TunnelCountQuery, tunnel_counts

te = ngc.FlowPolicyConfig(routing=ngc.CentralizedTE(
    source_allocation=ngc.SourceAllocation.EQUAL,
    tunnel_count=ngc.TunnelCount(1),
))
tunnels = DemandSet("tunnels", (
    DemandSpec(Selector("^A$"), Selector("^C$"), volume=0, policy=te, id="te"),
))
counted = prepare(Scenario(network, demand_sets={"tunnels": tunnels},
                           units=UnitsSettings(resolution=1)),
                  demand_sets=("tunnels",))
counts = tunnel_counts(counted, TunnelCountQuery(
    counted.demand_sets["tunnels"], counts=(2, 4), design_demand=4, offer=6,
))
two, four = counts.rows
assert (two.count, two.result.plan.tunnels_per_head, two.result.delivered) == (2, 2, 5)
assert two.lossless_at_design_units == 4
```

`tunnel_counts(prepared, TunnelCountQuery(demands, counts, design_demand, offer, up_to=None, eligibility=None, ...))` evaluates each tunnelled centralized-TE demand once per count (and once up to `up_to`), each a fresh native evaluation lossy at `offer` and planned for `design_demand`, the same two amounts for every demand. Each `TunnelCountRow` holds the native result (its `plan` is the tunnel layout), the row's `count` and `up_to`, `lossless_at_design_units` (min(design, the plan's largest lossless offer)) and `physical_tunnel_cost` (a pool row's tunnel cost without its one cost-1 ingress hop per tunnel). An `eligibility` asks the question on a failed network. An offer above a TE ingress pool's prepared budget is refused: declare a `TunnelCountAnalysis` step with that offer and prepare again ([Tunnels and TE ingress pools](../concepts.md#tunnels-and-te-ingress-pools)).

## Failure cases

```python
from ngraph import FailureMode, FailurePolicy, FailureRequest, FailureRule

policy = FailurePolicy(modes=[FailureMode(1, [
    FailureRule("link", mode="choice", count=1),
])])
degraded = capacity(prepared, CapacityQuery(
    Selector("^A$"), Selector("^C$"),
    failures=FailureRequest(policy, iterations=20, seed=42, failure_trace=True),
    workers=2,
))
assert sum(case.case.occurrences for case in degraded.cases) == 20
```

`failure_cases(prepared, request)` exposes the same typed cases to custom analyses ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states); seeds: [Seeds](dsl.md#seeds)). For capacity, placement and sensitivity, `workers="auto"` resolves to the CPU count; results and errors are the same for any number of workers. MSD runs serially. Explicit worker values must be positive integers.

## Paths and sensitivity

`paths(prepared, PathQuery(source, target))` returns named rows retaining native `Path` values. Default SPF uses forward search; selectors supply endpoints. SPF combine keeps only concrete pairs at the global minimum cost. `costs_only=True` omits path expansion; no route has `cost=None`, distinct from a singleton self row with cost zero.

Use `options=ngc.KspOptions(k, cost_ceiling=...)` for KSP. Candidates merge by `(cost, concrete pair ordinal, native rank)` and then truncate to `k`. Native `AbsoluteCost` is inclusive; `CostStretch` accepts exact fractions. Masks and residual vectors belong to the prepared graph. The question records the effective SPF `min_residual`; KSP records `None`.

`edge_sensitivity(prepared, SensitivityQuery(source, target, config, ...))` asks directed edge-deletion questions and retains the native baseline and signed integer reductions, including raw zero entries. JSON omits exact-zero entries. It accepts uncapped lossless capacity or fixed finite lossy traffic; its baseline is the evaluator's own, not a second solve.

## Results and export

`run(prepare(scenario))` returns `RunResult` with an ordered tuple of steps, one units report (the preparation's report with each step's misses, labelled by step) and producer metadata. Every analysis records its own typed query (`CapacityQuery`, `PlacementQuery`, `SensitivityQuery`, `PathQuery`, `MSDQuery`) as `query`, and a step records it as its `question`; a built-in domain step records itself. The JSON export writes each question in normalized form (selectors, the effective native model, failures, alpha and its source). A capacity case has `states={"converged": ...}`; a placement case has one entry per requested failure state (`PlacementQuery.states`, default `("converged",)`, `"stale"` and `"repair"` on request), and `PlacementQuery.interaction` selects `"ordered"` or `"simultaneous"` forwarding (workflow reference: TrafficMatrixPlacement). Rows retain native values and add endpoint identity, declared request accounting and optional reports.

`write_json(result, file)` is the export path. It writes each plain record as its declared constants and fields, in declaration order; `ngraph/schemas/results.json` is generated from the same declarations. The file's format is in [Output Format](cli.md#output-format), and what its numbers mean in [Results and their units](../concepts.md#results-and-their-units).

`CapacityQuery`, `PlacementQuery`, `SensitivityQuery` and `MSDQuery` accept `export_details=False`. It controls JSON projection; `row.result` and the sensitivity baseline remain complete native objects for Python access. The analysis `outputs.details` records the effective value. MSD applies it to best rows and any explicitly retained probe rows without changing history retention.

## Custom steps and exporters

Custom steps implement `run(StepContext) -> StepOutput`, read earlier successful steps through `context.prior_results`, and return their question (a finite JSON mapping of their parameters) plus a result. A step that needs a demand set bound, or asks a numerical question, says so with `needs()`, which returns a `StepNeeds` record (`ngraph.workflow`); the default `None` asks preparation for nothing. A custom result registers exactly one `register_result_exporter(Type, encoder)`; plain JSON domain data is also accepted. Unknown result types refuse. The encoder runs once per requested export. Published results are immutable for later steps: plain JSON results and questions are stored read-only, and NetGraph's own records are immutable. A registered result is published as it is, with any native Core values it holds, so make its type immutable. A custom step type parses its own YAML keys by overriding the `yaml_arguments(arguments, name)` class method.

## Records and editing

Domain records are immutable from construction: nodes, links, risk groups, components, conditions, selectors, failure rules, modes and policies, demand declarations and built-in workflow steps. Each constructor checks its fields when the record is built, by one rule per kind of field, the same for Python and YAML: text is a `str` (a name is nonempty; whitespace is part of it), a flag a `bool`, an integer an `int` or an exactly integral float such as `2.0` (stored as `2`), and an amount or ratio any finite real number in the field's range (stored as a float); a NumPy scalar of the field's kind counts as that kind, a subclass of `str`, `int` or `float` is stored as its plain value (ignoring overridden conversions), and booleans are never numbers. Each refusal names the field and the value. What only the whole network can check (names that must exist, sums over links) is checked at preparation. `attrs` and condition operands must be finite JSON data and are stored read-only; tuples and sets in them are refused, so use lists. Record collections are stored as tuples and frozensets. Edit through the `Network` methods (`add_node`, `add_link`, `replace_node`, `replace_link`, the enable/disable and risk-group toggles) or `dataclasses.replace`: assigning a record field raises `dataclasses.FrozenInstanceError`, and editing read-only attrs raises `TypeError`. `Network.add_link` assigns a link's id once; a link already in a network is refused by another, so add `dataclasses.replace(link)` there. `replace_link` keeps a link's endpoints; to move a link, add a new one. A YAML declaration's identity is declared data that `dataclasses.replace` keeps: `DemandSpec.yaml_label`, `declaration_ordinal` and `expand_leaf_index`, and a step's `yaml_label` and `derived_seed` (its `seed_source` is `scenario-derived` while its seed equals that derived seed).

`Network` and `ComponentsLibrary` keep editable dicts. `prepare` changes nothing in its input: the returned `PreparedScenario` holds read-only views of those dicts, each copied on its own under plain string keys, that share the immutable records, so later edits of the caller's collections never reach it, and editing a prepared view raises `TypeError`. A failed `prepare` leaves its input as it was.

A custom step's own data is its own: it is neither copied nor frozen, and the step can change it and its later answers. `prepare` records each step's name and seed, so a later edit of those does not reach the prepared scenario. `copy.copy`, `copy.deepcopy` and pickle of a record give an equal immutable value; records that hold native values are shared by copies, and native values cannot be pickled.

## Domain tools and logging

`BuildGraph` exports the physical network in NetworkX node-link form. `NetworkStats`, `CostPower` and `NetworkExplorer` retain their domain analysis roles. Risk-group editing methods on `Network` resolve current membership for each mutation.

`ngraph.hardware` exports `hardware_inventory`, `HardwareInventory`, `HardwareUse`, `link_active` and `resolve_link_end`. `ngraph.workflow.step_name(step)` returns a step's effective run name. The public API is the `__all__` of `ngraph`, `ngraph.workflow`, `ngraph.hardware` and `ngraph.logging`.

Importing the package installs a `NullHandler`. Applications can call `ngraph.logging.set_global_log_level(level)` or configure their own handler. Import the CLI explicitly when it is needed.
