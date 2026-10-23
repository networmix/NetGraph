# API Reference

NetGraph accepts typed model and query values. YAML dictionaries end at parsing. The [generated reference](api-full.md) lists the public declarations; [DSL](dsl.md), [workflow](workflow.md) and [CLI](cli.md) describe the file and command boundaries.

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

`PreparedScenario` holds the read-only scenario view, its `topology`, the bound `demand_sets` and the preparation's `units_report`. `PreparedTopology` holds the graph and its labels: `graph`, physical node names, read-only node-name and physical-link mappings, `edge_refs` in native edge order, nominal disabled eligibility, `q` and `pool_heads` (each finite TE ingress pool's synthetic head node). Every analysis takes the prepared scenario, holds it as `prepared` and returns its own precision `misses`; its `units_report` is the preparation's report with those misses appended. A physical link has two native directions; `DirectedLink(link, direction)` identifies one. Returned native results retain their graph and remain readable after working policies are removed.

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

Shortest-path routing keeps its cost-selected support even when an edge has no capacity. Equal splitting retains that member; capacity weighting gives it zero weight. Both use native equal source allocation. An optimized controller may choose different flows and routes. The normalized question records the effective model, finite offer/design inputs and failure request.

Physical offers are optional. The analysis labels the actual question `lossless_bound`, `fixed_offer_delivery` or `first_hop_experiment`, with its offer source. Native integer-valued configuration fields already contain units; YAML bandwidth minima are physical and are converted at preparation.

## Demands, placement and MSD

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

`DemandSpec` accepts a declared preset, native configuration or named `PinnedRoutes`. Priorities sort ascending; declaration and canonical expansion order break ties. IDs are unique throughout a run. Missing IDs use the set name and source declaration ordinal, with stable indices for explicit expansion and resolved leaves. Grouped splitting preserves each quantized parent total, including reported discarded shares.

`maximum_supported_demand(prepared, MSDQuery(resolved_set))` keeps one native ledger and the same owners throughout the probe series. Each probe scales the original physical parent totals, quantizes once and removes every previous owner before submitting the complete matrix. Feasibility uses exact integer accounting.

Read `alpha_feasible` as the largest tested feasible factor, or `None` when none was found. `history` contains every actual probe. `search_status` is one of `feasible`, `none_feasible`, `range`, `stagnation`, `limit`, `trivial`; `stop_reason` explains the termination. An upper certificate exists only for a proved downward-closed class. Multiple controllers and tunnel redesigns are conservatively unproved. Python callers may request `export_probe_rows=True`; YAML has no such input.

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

The baseline comes first; unique expanded physical patterns follow in first-observed order. Sampled empty patterns count toward the baseline's `occurrences`, without an extra baseline trial. A failed physical link excludes both directions. Risk-group membership uses one shared resolver, including unregistered descendants. Optional traces describe the first sampled cause of each pattern.

`failure_cases(prepared, request)` exposes the same typed cases to custom analyses. Drawing occurs before worker execution. For capacity and placement, `workers="auto"` resolves to the CPU count (one fixed rule per analysis kind). Seven paired 1-versus-N measurements on the shipped callers selected N: NSF capacity and backbone placement save more time than the small cases spend on thread start-up. Sensitivity also resolves auto to the CPU count; the shipped scenarios have no sensitivity caller to screen. MSD remains serial. Explicit worker values must be positive integers. Query seeds override policy seeds. Each draw uses a fresh `random.Random(base_seed + draw_index)`.

## Paths and sensitivity

`paths(prepared, PathQuery(source, target))` returns named rows retaining native `Path` values. Default SPF uses forward search; selectors supply endpoints. SPF combine keeps only concrete pairs at the global minimum cost. `costs_only=True` omits path expansion; no route has `cost=None`, distinct from a singleton self row with cost zero.

Use `options=ngc.KspOptions(k, cost_ceiling=...)` for KSP. Candidates merge by `(cost, concrete pair ordinal, native rank)` and then truncate to `k`. Native `AbsoluteCost` is inclusive; `CostStretch` accepts exact fractions. Masks and residual vectors belong to the prepared graph. The question records the effective SPF `min_residual`; KSP records `None`.

`edge_sensitivity(prepared, SensitivityQuery(source, target, config, ...))` asks directed edge-deletion questions and retains the native baseline and signed integer reductions, including raw zero entries. JSON omits exact-zero entries. It accepts uncapped lossless capacity or fixed finite lossy traffic; it does not perform a second baseline solve.

## Results and export

`run(prepare(scenario))` returns `RunResult` with an ordered tuple of steps, one units report (the preparation's report with each step's misses, labelled by step) and producer metadata. Every analysis records its own typed query (`CapacityQuery`, `PlacementQuery`, `SensitivityQuery`, `PathQuery`, `MSDQuery`) as `query`, and a step records it as its `question`; a built-in domain step records itself. The JSON export writes each question in normalized form (selectors, the effective native model, failures, alpha and its source). A case has `states={"converged": ...}`. Rows retain native values and add endpoint identity, declared request accounting and optional reports.

`write_json(result, file)` is the export path. It writes each plain record as its declared constants and fields, in declaration order, and encodes before writing; `ngraph/schemas/results.json` is generated from the same declarations. CLI file output uses an atomic replacement. Edge arrays, cuts and cost reports are opt-in; unsupported cost histograms carry an explicit reason. Unrestricted optimized capacity returns a tagged marginal curve; determined path costs return delivered-unit bins. Integer units remain exact in JSON.

Custom steps implement `run(StepContext) -> StepOutput`, read earlier successful steps through `context.prior_results`, and return their question (a finite JSON mapping of their parameters) plus a result. A step that needs a demand set bound, or asks a numerical question, says so with `needs()`, which returns a `StepNeeds` record (`ngraph.analysis.preparation`); the default `None` asks preparation for nothing. A custom result registers exactly one `register_result_exporter(Type, encoder)`; plain JSON domain data is also accepted. Unknown result types refuse. The encoder runs once per requested export. Published results are immutable for later steps: plain JSON results and questions are stored read-only, and NetGraph's own records are immutable. A registered result is published as it is, with any native Core values it holds, so make its type immutable. A custom step type parses its own YAML keys by overriding the `yaml_arguments(arguments, name)` class method.

## Domain tools and logging

`BuildGraph` exports the physical network in NetworkX node-link form. `NetworkStats`, `CostPower` and `NetworkExplorer` retain their domain analysis roles. Risk-group editing methods on `Network` resolve current membership for each mutation.

Importing the package installs a `NullHandler`. Applications can call `ngraph.logging.set_global_log_level(level)` or configure their own handler. Import the CLI explicitly when it is needed.


## Compact rows and requested details

`CapacityQuery`, `PlacementQuery`, `SensitivityQuery` and `MSDQuery` accept `export_details=False`. It controls JSON projection; `row.result` and the sensitivity baseline remain complete native objects for Python access. The analysis `outputs.details` records the effective value. MSD applies it to best rows and any explicitly retained probe rows without changing history retention.

Compact native-result JSON contains `request_kind`, `requested_units`, `offered_units`, `delivered_units`, `unadmitted_units`, `source_drop_units`, `edge_drop_units`, `termination` and `total_cost`. Values retain native null/infinite applicability and exact integer units. `edge_drop_units` sums native losses on physical and synthetic edges. Row ids/endpoints/reference values and nullable `pool` metadata remain present; a pool names the private ingress and its cost contribution. Combined sources asked with `TE_ECMP_16_LSP` or `TE_ECMP_UP_TO_256_LSP` share one private head, for placement and capacity alike: preparation builds it for each such demand and MaxFlow step (one pool per source set for a MaxFlow step), and a library `CapacityQuery` with that preset as its `declaration` uses the prepared pool of exactly its sources, or is refused. `resolve_demands` refuses a pool id whose sources differ from its prepared ingress.

With `export_details=True`, rows additionally project call delivery/undelivered/delta/drop fields, admitted units, named sparse drops, per-source and per-tunnel values, and the native plan. Unrequested detail fields are absent. Native optional arrays/cuts and `export_cost_distribution` keep their independent controls: requesting details performs no extra solve or cost-report preparation.

Domain records are immutable from construction: nodes, links, risk groups, components, conditions, selectors, failure rules, modes and policies, demand declarations and built-in workflow steps. Each constructor checks its fields once. A scalar is stored as its built-in value: a subclass of `str`, `int` or `float` becomes its plain value, ignoring overridden conversions, and NumPy or other non-built-in scalars are refused with the field's label. `attrs` and condition operands must be finite JSON data and are stored read-only; tuples and sets in them are refused, so use lists. Record collections are stored as tuples and frozensets. Edit through the `Network` methods (`add_node`, `add_link`, `replace_node`, `replace_link`, the enable/disable and risk-group toggles) or `dataclasses.replace`: assigning a record field raises `dataclasses.FrozenInstanceError`, and editing read-only attrs raises `TypeError`. `Network.add_link` assigns a link's id once; a link already in a network is refused by another, so add `dataclasses.replace(link)` there. `replace_link` keeps a link's endpoints; to move a link, add a new one. A YAML declaration's identity is declared data that `dataclasses.replace` keeps: `DemandSpec.yaml_label`, `declaration_ordinal` and `expand_leaf_index`, and a step's `yaml_label` and `derived_seed` (its `seed_source` is `scenario-derived` while its seed equals that derived seed).

`Network` and `ComponentsLibrary` keep editable dicts. `prepare` changes nothing in its input: the returned `PreparedScenario` holds read-only views of those dicts, each copied on its own under plain string keys, that share the immutable records, so later edits of the caller's collections never reach it, and editing a prepared view raises `TypeError`. A failed `prepare` leaves its input as it was.

A custom step's own data is its own: it is neither copied nor frozen, and the step can change it and its later answers. `prepare` records each step's name and seed, so a later edit of those does not reach the prepared scenario. `copy.copy`, `copy.deepcopy` and pickle of a record give an equal immutable value; records that hold native values are shared by copies, and native values cannot be pickled.
