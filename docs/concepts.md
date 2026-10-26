# How NetGraph computes

How a scenario becomes numbers. Each section uses only the ones before it, so read the page in order; each ends with the keys and result fields that carry its idea.

## Scenario, preparation and run

**In one line:** a scenario declares a network, its traffic and an ordered workflow; preparation turns it once into a read-only graph with one bandwidth unit; a run executes the workflow on that graph and returns typed results.

Four terms first, so that later sections can use them:

- **Network:** named nodes and the physical links between them.
- **Demand:** a volume of traffic from a set of source nodes to a set of destination nodes.
- **Workflow step:** one question the run asks, such as a maximum flow or a placement of a demand set.
- **`q`:** the size of one bandwidth unit; [Units and the resolution q](#units-and-the-resolution-q) gives the rule.

`Scenario` declares inputs. `prepare` returns prepared inputs that later edits of the scenario do not reach. `run` executes steps in declaration order and returns immutable result envelopes. Each step records the question it asked (an analysis's own typed query, or a built-in domain step's configuration), its order and seed provenance.

An editable `Network` holds immutable named nodes, physical links and risk groups. Preparation takes a read-only view of it and builds one immutable native graph, and chooses `q`. Results belong to the returned run; `Scenario` keeps declarations, and later topology edits require another preparation.

A custom step's own data is not frozen ([Records and editing](reference/api.md#records-and-editing)). A failed call publishes nothing partial ([Guarantees](reference/design.md#guarantees)).

In the reference: [Workflow Steps](reference/workflow.md); Python `Scenario`, `prepare`, `run`, `PreparedScenario` ([Python API](reference/api.md#prepare-and-query)).

## Links, directions and what is enabled

**In one line:** a physical link can carry traffic in both directions, each with the link's full capacity.

Every physical link supplies forward and reverse edges. A link's id is `source|target|n`, where `n` counts the links added between that ordered pair of nodes, from 0. A link is enabled when it and both of its end nodes are enabled.

In the reference: link keys in [Scenario YAML](reference/dsl.md#network-topology); `DirectedLink` ([Python API](reference/api.md#prepare-and-query)).

## Units and the resolution q

**In one line:** Capacities and volumes are physical inputs; preparation converts them to whole bandwidth units of size `q` for native analyses. Recorded inputs, offers and designs, and `NetworkStats` capacities remain physical amounts.

Capacities, demand volumes, finite offers and designs and minimum unreserved bandwidth are physical quantities. A legal explicit resolution is one power of two from 2^-32 through 2^32. Preparation promotes each input to binary64, selects one quantum `q` and converts quantities with exact half-up rounding. Native bandwidth results are exact integer units; multiply them by `q` only when presenting physical bandwidth.

Whole units are split by fixed arithmetic. Units split equally go `I // k` to each of `k` members and one more to the first `I % k` in a fixed order (sources by node order), so 10 over 3 members gives 4, 3, 3. A weighted split hands them out one at a time to the member with the largest weight over its count plus one, ties to the earlier member, so 5 over weights 2 and 1 gives 4 and 1. The engine's exact rule: [Splitting whole units](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#splitting-whole-units).

In the reference: `units` in [Scenario YAML](reference/dsl.md#units-and-input-validation); `units_report.q` in [Results](reference/results.md).

## Routing models and admission

**In one line:** a model is a routing (how traffic chooses paths and splits) plus an admission (whether traffic that does not fit is refused before it enters, or sent and lost on the way).

Each preset names one model; a demand or MaxFlow step can instead declare the model itself. A capacity question (the MaxFlow step) asks how much one model delivers between two node sets.

| Model (YAML `routing.type`) | Python | Question |
| --- | --- | --- |
| `shortest_paths`, `allocation: equal` | `ShortestPaths` EQUAL | Static shortest-path routing with equal next-hop splitting and equal source allocation |
| `shortest_paths`, `allocation: weighted` | `ShortestPaths` WEIGHTED | Static shortest-path routing with declared native weights; the preset uses physical capacity weights |
| `shortest_paths`, `allocation: optimized` | `ShortestPaths` OPTIMIZED | Optimized flows on the union of the selected shortest supports |
| `centralized_te` without a `tunnel_count` | `CentralizedTE` without a count | Optimized traffic engineering over the eligible graph |
| `distributed_te` | `DistributedTE` | Strict per-head CSPF tunnels with setup reservations and separately forwarded traffic |
| `centralized_te` with a `tunnel_count` | `CentralizedTE` with a count | A controller selects a common tunnel size and exact or up-to per-head count |
| `pinned` | `Pinned` | A supplied native program, including named explicit routes |

A tunnel is a selected route from a head (source router) to the destination; a reservation holds setup bandwidth, separately from carried traffic ([Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)).

A program is a model's routing decision written down; named routes and native `Pinned` programs are supplied programs. Equal and weighted router splitting pool traffic where source routes meet. Shortest-path routing keeps its cost-selected support even when an edge has no capacity: equal splitting retains that member, capacity weighting gives it zero weight. Both use native equal source allocation. The two optimizing controllers (`TE_MAXFLOW_UNLIM`, `SHORTEST_PATHS_MAXFLOW`) may choose different flows and routes.

Admission, source injection, carried traffic, edge losses and reservations are separate native quantities. Lossless admission refuses what does not fit, as unadmitted traffic; lossy admission sends it, and it is lost at sources without a usable route (source drops) or on links (edge drops).

In the reference: presets in [Scenario YAML](reference/dsl.md#presets); [MaxFlow](reference/workflow.md#maxflow); `admission` and the drop fields in [Results](reference/results.md).

## Demands: how traffic enters

**In one line:** a demand's declared volume, times the step's multiplier alpha, is turned into whole units once and split over the demand's source and destination pairs by fixed arithmetic.

Alpha is the demand multiplier: a step places each declared volume times alpha (1 by default).

Demand expansion stores a fixed tree of physical parents and integer split leaves. A scaled run multiplies the original parent total, quantizes it once and distributes the resulting units in deterministic quotient/remainder order. Each declared physical total is quantized once, then split by integer quotient and remainder in canonical group and node order, after excluding self pairs and same-label group pairs. Branches whose only pairs are node-to-itself or same-label group pairs are removed recursively; the remaining hierarchy keeps its shape. Empty selections keep their reported discarded shares, which are never redistributed. A declaration with no eligible pair is reported whole as discarded with its reason. Declared units equal resolved plus discarded units; eligible zero-volume leaves remain. At q = 1, a parent of 10 split into two groups and the second into three produces 5 and (2, 2, 1), retaining the total 10.

A `combine` demand has one ordered roster of sources. A zero-capacity source keeps its share, so earlier sources in the roster can receive units before it blocks the rest. Equal/weighted shortest-path routing injects equal integer shares at reachable source heads and pools traffic at shared routers. Optimized routing can choose source injections. At q = 1, source capacities 100/10 permit the integer equal-source prefix 21 (11/10), rather than the fluid 20; the same question at a finer q can give a different final fractional prefix.

A demand's losses: units not admitted (lossless), source drops and edge drops (lossy). The reference request is the scaled declared request; the shortfall is that request minus the delivery, and the delivery ratio is the delivery over the request.

In the reference: [Traffic Modes](reference/dsl.md#traffic-modes-mode) and [Group Modes](reference/dsl.md#group-modes-group_mode); `alpha` in [TrafficMatrixPlacement](reference/workflow.md#trafficmatrixplacement); placement totals in [Results](reference/results.md).

## Precision and the choice of q

**In one line:** with `resolution: auto`, preparation picks the coarsest `q` that keeps every input and split within the precision target and every amount in range (else the finest `q` in range), and the units report records each place the target is missed.

For target `p`, each positive finite input `v` imposes `q ≤ 2pv`; a split of positive `v` over `m ≥ 2` members imposes `q ≤ pv/(m − 1)`, for expansion, source, router and tunnel splits ([Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)). Automatic selection can miss these bounds when range or the finest legal resolution prevents a finer `q`. Preparation accounts for directed graph sums, synthetic attachments, input rounding and local split precision. The units report is always returned. It records input and local-split constraints, rounding counts, missed targets and unverified supplied programs. Each finite native bandwidth input and each directed graph capacity/cost aggregate must stay below 2^62, including reverse and synthetic edges. Exact result totals can exceed 64 bits.

Capacity split precision uses the finite native delivery at each candidate unit size for an uncapped lossless question or a Core-derived first-hop experiment. The units report labels these split constraints `basis: observed` and records the exact physical incoming amount. Finite declared offers and designs use `basis: declared`. Input rounding is checked independently.

Later queries keep the prepared `q` and report their own misses; so do failure cases and the searches of maximum supported demand (see [Failures: patterns, cases and states](#failures-patterns-cases-and-states) and [Maximum supported demand](#maximum-supported-demand)).

In the reference: `units` in [Scenario YAML](reference/dsl.md#units-and-input-validation); `UnitsReportJSON` in [Results](reference/results.md#unitsreportjson).

## Tunnels and TE ingress pools

**In one line:** a tunnel model sets up tunnels from each head (a source router) toward the destination, and a tunnel count describes that layout, not how much traffic gets through.

Each head sets up its tunnels one at a time on links with enough unreserved bandwidth. A tunnel that comes up holds exactly its request; holds decide which tunnels come up, never what traffic gets through. The engine's exact rule: [T1: tunnels set up by their heads](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#t1-tunnels-set-up-by-their-heads).

One controller gives every head the same number of single-path tunnels of one common whole-unit size. It picks the largest size, then no more than the design needs, then the cheapest routes; the planned size is never held. The engine's exact rule: [T2: the controller's equal tunnels](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#t2-the-controllers-equal-tunnels).

`distributed_te` requires `tunnel_count: {per_head: N}` and accepts `min_unreserved_bandwidth` in physical units plus a cost ceiling. Tunnel counts are per head; a configured count is a layout, not a delivery guarantee. A reservation is not carried traffic and is not added to the carried vector. Exact tunnel count describes a layout; it does not promise that every offered unit is delivered.

`design_demand` sizes the layout; `offer` is the traffic forwarded through it. Counts are per head: a row's `count` is the requested count or `up_to` limit, while `plan.tunnels_per_head` is the chosen count. With `up_to`, the controller chooses the smallest count that carries the live heads' design shares, rather than the count that delivers most of the offer.

Private traffic-engineering ingresses (TE ingress pools) connect the selected physical heads with finite capacity bounds and cost 1. They belong to their declared demand or MaxFlow question, are labelled as synthetic and cannot become ordinary transit endpoints. Combined sources asked with `TE_ECMP_16_LSP` or `TE_ECMP_UP_TO_256_LSP` share one private head, for placement and capacity alike: preparation builds it for each such demand and MaxFlow step (one pool per source set for a MaxFlow step), and a library `CapacityQuery` with that preset as its `declaration` uses the prepared pool of exactly its sources, or is refused. `resolve_demands` refuses a pool id whose sources differ from its prepared ingress.

A pool's offer budget is 0 unless a step gives it a known lossy offer; [Ordered and simultaneous placement](#ordered-and-simultaneous-placement) adds a second source of one. A `TunnelCountAnalysis` step's offer is a known lossy offer for the TE ingress pools of its set: each pool's attachments widen to carry it (the headroom penalty prices them), and a library `tunnel_counts` query above that budget is refused. The offer and design take part in choosing `q`, and so can make `q` finer for every step of the run.

In the reference: [TunnelCountAnalysis](reference/workflow.md#tunnelcountanalysis); `edge_reservations` in [Output selection](reference/workflow.md#output-selection); `pool` in [Results](reference/results.md).

## Routing domains and the WCMP controller

**In one line:** a WCMP controller computes one weight table per demand set and destination for the routers of a routing domain, and every `SHORTEST_PATHS_WCMP` demand toward that destination forwards on it.

A WCMP controller (`wcmp_controller`) programs `SHORTEST_PATHS_WCMP` demands toward one BGP-edge router: one DAG of routes per destination through one IGP domain, and one weight table per demand set and destination. `routing` constrains the controller only; ECMP and TE demands keep their native models. Toward a destination t the routes are one DAG: one reverse shortest-path search inside the IGP domain from the exits (domain nodes with an eligible link to t), every eligible exit link, and every eligible uplink from another BGP-edge router into a domain node that reaches an exit. Nothing enters a BGP-edge router but t, so no other one carries transit. With no exit the DAG is empty and the demand finds no route.

A programmed demand has one destination, in `bgp_edge`, and its sources lie in either population. The scopes:

- `next_hop`: the source routers of demands with a positive volume split over their next hops by progressive filling: each next hop grows in proportion to what it carries alone, and stops when a link it uses fills. Routers are processed downstream first, so a programmed router's integer weights shape the loads of routers above it.
- `group`: each programmed source router splits by its declared tree ([Forwarding groups and their caps](#forwarding-groups-and-their-caps)).
- `all_routers`: every router on the sources' walks is programmed from one native flow over the DAG whose sources send in proportion to the demands' exact nominal volumes (a multi-source demand divides its volume over its sources that reach t).

Every other router splits equally over its members, zero-capacity ones included (ECMP). Each demand forwards on the shared table through its own native program; the controller forwards nothing itself. The tables are computed on the network without failures and do not change with alpha.

In the reference: [Routing domains and the WCMP controller](reference/dsl.md#routing-domains-and-the-wcmp-controller); `controller` in [Results](reference/results.md).

## Forwarding groups and their caps

**In one line:** under the `group` scope, a programmed router splits by a declared tree whose root shares are fixed caps.

Root shares are fixed caps, normalized once; child shares split within their parent. A member that can carry nothing alone (it meets a zero-capacity link or a dead branch) gets 0 and its group re-flattens over its live members within its cap. A root group with no live member is refused: the preset's lossless admission would stop the demand at the first unit sent into it. Weights too large for the engine are approximated and reported ([Weight approximation](reference/dsl.md#weight-approximation)).

In the reference: `forwarding_groups` in [Scenario YAML](reference/dsl.md#routing-domains-and-the-wcmp-controller).

## Failures: patterns, cases and states

**In one line:** a failure policy draws sets of failed nodes and links; each distinct set is one failure case, evaluated once, and a placement reports each case in the failure states it was asked for.

Selectors resolve on the nominal physical population. A failure changes eligibility and native source rosters, while declared demand volume remains unchanged: failures do not remove the declared volume of a failed endpoint. A failed physical link excludes both directions.

Sampling consumes rules in declaration order over sorted entity identifiers. Expanded physical patterns are deduplicated before execution, preserving multiplicities and optional first traces. No failure request means one baseline. The work is linear in the requested iterations. With sampling, `occurrences` sum to the requested iterations, including sampled empty patterns on the baseline. The baseline comes first; unique expanded physical patterns follow in first-observed order. Baseline presence and sampled multiplicity are separate: sampled empty patterns count toward the baseline's `occurrences`, without an extra baseline trial. Optional traces describe the first sampled cause of each pattern. Drawing occurs before worker execution, and seeds follow [Seeds](reference/dsl.md#seeds). Each case keeps the prepared `q` and reports its own precision misses.

Stale forwarding replays a demand's program unchanged while failed elements swallow what reaches them; repair drops the failed routes and re-splits over the survivors, with no new search. The engine's exact rule: [Forwarding programs](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#forwarding-programs).

Each case reports its states through a common states mapping: capacity its converged state, placement its requested failure states (`[converged]` by default; `stale` and `repair` only when listed), each computed on its own ledger:

- `converged`: the demands computed again on the failed network. Controller tables are rebuilt for the case; declared forwarding-group shares stay fixed caps. A root group with no live member keeps its fixed cap and is listed in the state's `dead_caps`. Lossless admission stops before the first unit assigned to a dead member; lossy forwarding drops the units assigned to that group at its router. A case whose program would forward that share differently is refused with the group, case and state.
- `stale`: each demand's program from the case without failures, forwarded unchanged and lossy at that baseline's admitted total; traffic that reaches a failed node or link is lost there.
- `repair`: the same programs with failed routes removed and survivors re-split (no new route search), at the declared request and admission; group shares stay caps.

`reference_request_units` stays the scaled request in every state; the native `requested` and `offered` describe each call. Cost reports and precision misses come from converged rows only. For an explicit-route demand alone, converged and repair forward the same program. The bounded forwarding calculation can cycle or reach its round limit. That case and state then reports a forwarding failure, with no rows; this does not prove that no stable answer exists. In the baseline it stops the step when stale or repair needs its programs. Group scope refuses converged and repair under a failure policy when it programs a router inside the IGP domain, where other demands can transit the router after a failure and a dead group's dropped share would cut them too; `stale` works there.

In the reference: [`failures`](reference/dsl.md#failures-failure-policies); `failure_policy`, `iterations`, `failure_trace` and `failure_states` in [Workflow Steps](reference/workflow.md#keys-common-to-analysis-steps); `cases`, `occurrences` and `states` in [Results](reference/results.md).

## Ordered and simultaneous placement

**In one line:** ordered placement places demands one after another by priority; simultaneous placement forwards every demand at once, sharing losses on common links.

Simultaneous forwarding sends every lossy fixed program at the same time, shares losses on common links, and reports one residual for the whole list. The engine's exact rule: [Several demands at once](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#several-demands-at-once).

`interaction: simultaneous` forwards every demand at once in one native list, sharing losses on common links, as a lossy question on fixed programs: each model that can be lossy forwards a lossy copy of itself (tunnel models are set up first and keep their reservations), and a live controller (`TE_MAXFLOW_UNLIM`, `SHORTEST_PATHS_MAXFLOW`) is computed, then its program forwarded lossy. Its lossy copy is created after the other participants, in every state, so it loses one-unit ties to them. Rows are not comparable with the default `ordered` rows. Under ordered placement a row's residual is the capacity left after that row; under simultaneous placement every row reports the one final residual.

A TE ingress pool in a simultaneous step gets a lossy offer budget, its largest known request, reported as the row's `pool.offer_limit_units`. Budgets are prepared once for the scenario: every placement step on that preparation reports them, and they count in the choice of `q`.

In the reference: `interaction` in [TrafficMatrixPlacement](reference/workflow.md#trafficmatrixplacement); `residual` in [Output selection](reference/workflow.md#output-selection).

## Maximum supported demand

**In one line:** MSD searches for the largest alpha at which the demand set is placed in full, and reports every alpha it tested.

The search checks exact native-unit feasibility. It retains all probes and the best tested feasible rows. `alpha_feasible` is null if no probe was feasible. `search_status` distinguishes `feasible`, `none_feasible`, `range`, `stagnation`, `limit` and `trivial`; `stop_reason` records the precise boundary. A range refusal is not an infeasible congestion sample. An MSD probe with a positive physical leaf rounded to zero requested units has outcome `below_resolution`; it is never feasible or a certificate endpoint. Probes keep the prepared `q` and report their own misses.

Only a proved downward-closed class receives an upper certificate. Fixed programs (equal or weighted splitting on static routes, supplied programs and WCMP controller tables, which are built once and do not change with the multiplier) and one centralized-TE demand without a tunnel count (weighted sources included), or one optimized shortest-paths demand with a static route choice (`FEWER_HOPS` or `HIGHER_CAPACITY`), alone in its set, are proved; live controllers beside other demands, tunnel layouts and TE ingress pools are not. The bounded search on an unproved composition is a heuristic. The result does not claim an untested global maximum. MSD takes no failure input.

A later step can place the set at the largest tested feasible alpha (`alpha_from_step`); a simultaneous step that takes its alpha from an MSD step cannot have pool demands.

In the reference: [MaximumSupportedDemand](reference/workflow.md#maximumsupporteddemand); `MSDAnalysisJSON` in [Results](reference/results.md#msdanalysisjson).

## Results and their units

**In one line:** Results distinguish native bandwidth units from physical amounts; other fields hold ratios, costs, counts or hardware totals. A missing key differs from a `null` value.

The numbers come in five kinds: bandwidth units (every `*_units` field and the native amounts; units × `q` is physical), physical amounts (inputs, offers and designs, `NetworkStats` capacities and the input samples, as declared), ratios (no unit), routing costs (never multiplied by `q`; `total_cost` is cost × bandwidth units, so `total_cost` × `q` is cost × physical bandwidth) and hardware money and power. Counts are plain integers. Native integer-valued configuration fields already contain units; YAML bandwidth minima are physical and are converted at preparation.

Each row's native result says what this call did (`call_` fields) and the demand's state after it (totals), and the two never mix. The engine's exact rule: [The result](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#the-result).

`write_json` writes plain records from their declared fields and the other results explicitly; the results schema is generated from the same declarations. Native integer quantities stay integer, optional outputs stay absent when unrequested, and unlimited/null values remain distinct. JSON rows default to compact exact summaries; Python results stay complete, and each optional output has its own selector ([Output selection](reference/workflow.md#output-selection)). Cost reports run only on request, and an unsupported cost report carries an explicit reason. Unrestricted optimized capacity reports native marginal cost pieces; determined shortest-path or tunnel delivery reports use tagged path-cost bins. Opt-in cost reports distinguish analysis-graph cost from physical-network cost.

In the reference: [Results](reference/results.md); [Output Format](reference/cli.md#output-format).

## Glossary

The terms these sections define, each in the section named:

- resolution `q`, unit: [Units and the resolution q](#units-and-the-resolution-q)
- alpha: [Demands: how traffic enters](#demands-how-traffic-enters)
- physical link, direction: [Links, directions and what is enabled](#links-directions-and-what-is-enabled)
- admission: [Routing models and admission](#routing-models-and-admission)
- source roster: [Demands: how traffic enters](#demands-how-traffic-enters)
- program, table: [Routing models and admission](#routing-models-and-admission), [Routing domains and the WCMP controller](#routing-domains-and-the-wcmp-controller)
- TE ingress pool: [Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)
- failure pattern, failure case: [Failures: patterns, cases and states](#failures-patterns-cases-and-states)
- hold, carried traffic: [Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)
