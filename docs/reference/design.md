# Design

NetGraph owns network meaning: physical topology, selectors, grouped demands, risk groups, scenarios and workflow questions. NetGraph-Core owns graph searches, allocation, forwarding, reservations and numerical results. A query declares which native model to run.

## Preparation

An editable `Network` holds immutable named nodes, physical links and risk groups. Preparation takes a read-only view of it and builds one immutable native graph. Every physical link supplies forward and reverse edges. A label table maps native edge order back to `DirectedLink`; numerical arrays remain native.

Costs are positive integers. Bandwidth quantities are promoted binary64 physical inputs, converted to integer units at one power-of-two quantum `q`. Preparation accounts for directed graph sums, synthetic attachments, input rounding and local split precision. The report describes the chosen q, target, constraints, misses and any unverified supplied program. Later queries and failures keep that q.

Selectors resolve on the nominal physical population. A failure changes eligibility and native source rosters, while declared demand volume remains unchanged. Named explicit routes compile on nominal enabled links; a node hop selects the minimum `(cost, DirectedLink)`. Explicitly disabled links and hops with no enabled link refuse. Sampled failures never re-resolve a compiled route.

## Traffic models

| Model | Question |
| --- | --- |
| ShortestPaths EQUAL | Static shortest-path routing with equal next-hop splitting and equal source allocation |
| ShortestPaths WEIGHTED | Static shortest-path routing with declared native weights; the preset uses physical capacity weights |
| ShortestPaths OPTIMIZED | Optimized flows on the union of the selected shortest supports |
| CentralizedTE without a count | Optimized traffic engineering over the eligible graph |
| DistributedTE | Strict per-head CSPF tunnels with setup reservations and separately forwarded traffic |
| CentralizedTE with a count | A controller selects a common tunnel size and exact or up-to per-head count |
| Pinned | A supplied native program, including named explicit routes |

Equal and weighted router splitting pool traffic where source routes meet. Admission, source injection, carried traffic, edge losses and reservations are separate native quantities. A reservation is not carried traffic and is not added to the carried vector. Exact tunnel count describes a layout; it does not promise that every offered unit is delivered.

A WCMP controller (`wcmp_controller`) programs `SHORTEST_PATHS_WCMP` demands toward one BGP-edge router: one DAG of
routes per destination through one IGP domain, and one weight table per demand set and destination. `next_hop`
weights source routers by progressive filling, `group` by declared trees whose root shares are fixed caps, and
`all_routers` every router from one native flow in demand proportions; other routers keep ECMP. Each demand forwards
on the shared table through its own native program; the controller forwards nothing itself.

Demand expansion stores a fixed tree of physical parents and integer split leaves. A scaled run multiplies the original parent total, quantizes it once and distributes the resulting units in deterministic quotient/remainder order. Filtered, empty-selection and singleton-self shares remain accounted rather than silently redistributed.

Private traffic-engineering ingresses connect the selected physical heads with finite capacity bounds and cost 1. They belong to their declared demand or MaxFlow question, are labelled as synthetic and cannot become ordinary transit endpoints. Their pool budget is zero; the supported pool question is lossless. Opt-in cost reports distinguish analysis-graph cost from physical-network cost.

## Execution and ownership

Placement creates one private ledger and stable policy roster per case. The complete priority-ordered matrix is submitted as native Replace actions. Returned results and record snapshots remain valid after every owner is explicitly removed. Any exception cleans all owners and publishes no partial analysis or run.

MSD keeps that ledger and roster over the entire bounded search. Before every probe it removes all prior owners, scales physical inputs, then applies the new full matrix. The result reports the largest tested feasible alpha and every probe. A monotonicity classifier controls whether an upper certificate may be emitted; it never turns observed samples into a theorem. Fixed programs (equal or weighted splitting on static routes, supplied programs and WCMP controller tables, which are built once and do not change with the multiplier) and one centralized-TE demand without a tunnel count, or one optimized shortest-paths demand with a static route choice (`FEWER_HOPS` or `HIGHER_CAPACITY`), alone in its set, are proved; live controllers beside other demands, tunnel layouts and TE ingress pools are not. MSD takes no failure input.

Capacity uses native scalar or pair evaluators. Directed sensitivity uses the evaluator's own baseline. Paths use native SPF/KSP and one declared group merge. Numerical results retain native objects; there is no second Python numerical representation between execution and export.

## Failures

One membership resolver supplies editable network mutations and prepared failure exclusions. It keeps node and link namespaces separate, traverses unregistered descendants and refuses cycles. Identical inline group declarations share a resolution; conflicts name both parent paths. A registered top-level declaration is authoritative.

Sampling consumes rules in declaration order over sorted entity identifiers. Random rules use per-entity Bernoulli. Expanded physical patterns are deduplicated before execution, preserving multiplicities and optional first traces. Baseline presence and sampled multiplicity are separate. Each case reports its states through a common states mapping: capacity its converged state, placement its requested failure states (converged by default, stale and repair on request), each on its own ledger; stale and repair replay the baseline case's programs.

Independent cases can have private ledgers on worker threads. Native pair evaluators can use native workers. Drawing and output order do not depend on worker completion. Failed work does not run through an alternative engine.

## Workflow and output

`Scenario` declares inputs. `prepare` returns owned prepared inputs. `run` executes steps in declaration order and returns immutable result envelopes. Each step records the question it asked (an analysis's own typed query, or a built-in domain step's configuration), its order and seed provenance. Custom workflow steps use the same typed context/output boundary and explicit exporter registration.

`write_json` writes plain records from their declared fields and the other results explicitly; the results schema is generated from the same declarations. Native integer quantities stay integer, optional outputs stay absent when unrequested, and unlimited/null values remain distinct. Cost reports run only on request. CLI output is encoded fully before replacing a destination file.

Domain exports remain separate product operations: `BuildGraph` provides physical NetworkX node-link data, `NetworkStats` describes topology, and `CostPower`/`NetworkExplorer` present hardware metrics.

See [API](api.md), [workflow](workflow.md), [DSL](dsl.md) and [CLI](cli.md).

Domain records are immutable from construction: nodes, links, risk groups, components, conditions, selectors, failure rules, modes and policies, demand declarations and built-in workflow steps. Each constructor checks its fields once. A scalar is stored as its built-in value: a subclass of `str`, `int` or `float` becomes its plain value, ignoring overridden conversions, and NumPy or other non-built-in scalars are refused with the field's label. `attrs` and condition operands must be finite JSON data and are stored read-only; tuples and sets in them are refused, so use lists. Record collections are stored as tuples and frozensets. Edit through the `Network` methods (`add_node`, `add_link`, `replace_node`, `replace_link`, the enable/disable and risk-group toggles) or `dataclasses.replace`: assigning a record field raises `dataclasses.FrozenInstanceError`, and editing read-only attrs raises `TypeError`. `Network.add_link` assigns a link's id once; a link already in a network is refused by another, so add `dataclasses.replace(link)` there.

`Network` and `ComponentsLibrary` keep editable dicts. `prepare` changes nothing in its input: the returned `PreparedScenario` holds read-only views of those dicts that share the immutable records, so later edits of the caller's collections never reach it, and editing a prepared view raises `TypeError`. A failed `prepare` leaves its input as it was.

A custom step's own data is its own: it is neither copied nor frozen, and the step can change it and its later answers. `prepare` records each step's name and seed, so a later edit of those does not reach the prepared scenario. `copy.copy`, `copy.deepcopy` and pickle of a record give an equal immutable value; records that hold native values are shared by copies, and native values cannot be pickled.
