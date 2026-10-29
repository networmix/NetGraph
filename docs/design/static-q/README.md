# Static q in NetGraph 0.26.0

This directory explains the bandwidth quantum for maintainers: why the selector uses a static count, what its proof assumes, and which small networks distinguish it from plausible wrong rules. It is internal documentation. The user-facing contract has one home in [Precision and the choice of q](../../concepts.md#precision-and-the-choice-of-q); report fields have one home in [UnitsReportJSON](../../reference/results.md#unitsreportjson).

NetGraph converts physical bandwidth to whole units of a power-of-two quantum `q`. A smaller unit reduces conversion error but cannot remove discontinuities in tunnel setup or make a theorem about one routing program apply to another. Preparation chooses the quantum once. Every placement, failure case, maximum-supported-demand (MSD) probe and later library question uses that same quantum.

## The selector

The precision target is `p = units.precision`, with `0 < p ≤ 1/2`, default `0.001`. The selector compares exact ratios of the binary64 input values.

| Quantity | Meaning |
| --- | --- |
| `v_min` | Smallest positive prepared bandwidth input: link capacities, declared root demand volumes at alpha 1, workflow offers, design demands and minimum unreserved bandwidth. It is not an apportioned leaf volume. |
| `c_min` | Smallest positive original link capacity, including disabled links. |
| `L` | Number of network nodes plus twice the number of links, including disabled elements. Private TE ingress pool heads and attachments do not count. |
| `k_g` | Expanded leaves in group `g` with lossless shortest-path routing, equal router splits and equal source shares. |
| `t_g` | For each tunnel leaf in group `g`, heads times tunnels per head, summed over those leaves. A pool is one head; otherwise count all selected source endpoints of the expansion leaf or capacity pair, including sources with no static route to a destination. |

A demand-set group counts its declared models when any workflow use other than simultaneous placement names it, or when a library caller requests it with `prepare(..., demand_sets=...)`. An ordered placement, MSD or tunnel-count step therefore makes the set count. A simultaneous-only set contributes nothing. A set used in both ways counts once. Each built-in MaxFlow pair is a separate one-leaf group. Each tunnel-count row is a separate group.

Tunnel presets count 16 or 256 tunnels per head. An explicit `per_head` uses its count; `up_to` uses its limit. A count step uses the maximum of its counts and limit. Weighted, optimized, lossy, pinned, supplied and controller-programmed leaves contribute no equal-split leaf count; a tunnel leaf still contributes its declared tunnels.

For each group,

```text
Γ_g = max(k_g, 1) · (L/4 + 2) + t_g
Γ   = max(L/4 + 2, max_groups Γ_g)
B_in    = 2p · v_min
B_split = p · c_min / Γ
```

A bound is omitted when its positive amount does not exist. The selected `q` is the largest power of two in `[2^-32, 2^32]` satisfying both bounds. No bounds gives `2^32` and `limited_by = unbounded`. A bound below the legal floor gives `2^-32` and `resolution_floor`. Otherwise the smaller bound decides `limited_by`; an exact tie names `input`.

The range check covers every converted input and the augmented directed capacity sum, including pool attachments and offer budgets, strictly below `2^62` units. If the chosen quantum fails, preparation scans coarser powers and takes the first passing one (`limited_by = range`), recording the next finer refusal. If none passes, preparation refuses. A manually declared legal power of two receives the same range check and reports `limited_by = declared`.

The achieved input/count budget is

```text
p' = max(q/(2v_min), qΓ/c_min)
```

with absent terms omitted and null when both are absent. `target_met` means that this scalar is absent or at most `p`. It is not an error measurement of arbitrary answers. Missing denominators provide no relative guarantee. Range, floor and manual choices can leave the target unmet.

Input-label ties keep preparation insertion order: workflow step inputs first, network link capacities second, then expansion-plan root volumes and their minima. Active sets bind in first-use order, then explicitly requested sets; demands keep their order inside each set. Group ties keep demand-set binding order then workflow order, with the floor winning an equal count. These choices affect the reported label, not the quantum.

The implementation reads expansion plans and built-in workflow declarations before compiling the graph. Opaque custom capacity/count callbacks contribute only the floor for their unknown questions; named sets and declared input atoms still participate. Their unknown tunnels have the same qualification as later library counts. Preparation compiles and binds once, then validates materialized questions without eligible traffic. No candidate preparation, split propagation or traffic solve selects `q`. Bound controller approximation records attach to the final report independently of the selector.

## Why the count is sufficient within its scope

A split context is one independent division of traffic among a router's outgoing members, or among source heads. For equal quotient/remainder splitting over `m` members, the largest aligned deviation is `floor(m/2)·ceil(m/2)/m ≤ m/4` units. A shared acyclic hop-by-hop program splits merged traffic once per router. Counting its edges and source roster therefore bounds its total deviation by `L/4`. The extra constant budgets capacity rounding and integer admission. [The lemmas and count proof](PROOFS.md#1-lemmas) give the derivation.

The [single-demand theorem](PROOFS.md#2-theorem-a-one-in-scope-demand-lossless) requires all of these premises: one fixed shared acyclic program, equal router and source splits, lossless admission, a nonempty roster whose every share reaches a destination, positive original carrying capacities independently rounded to units, and a directly converted finite request. It applies to a demand alone, first, or on links unused by earlier demands. A failure-case program can use the same count only if those premises still hold. The public delivery and link-flow inequalities remain in the [concepts page](../../concepts.md#precision-and-the-choice-of-q).

The [conditional MSD derivation](PROOFS.md#3-theorem-b-conditional-msd-derivation-not-the-public-delivery-promise) additionally requires positive aggregate capacities, finite normal or exact binary64 products, no relevant below-resolution probe and a completed feasible/infeasible bracket. The [optimized-flow theorem](PROOFS.md#4-theorem-c-one-optimised-maximum-flow) instead uses integral max-flow/min-cut on fixed support with optimized source allocation. A finite offer needs its own input bound. Neither result certifies arbitrary route vectors, costs or ratios.

The [tunnel term](PROOFS.md#6-the-tunnel-term) prevents a capacity-limited controller layout on full positive capacities from having zero whole units per tunnel for the covered count. It does not bound the layout's accuracy or cover design-limited sizes and later larger counts.

## Counterexamples outside the scope

The independent computations and native witnesses use the names below. Full derivations are in [PROOFS.md](PROOFS.md#7-counterexamples-and-limits). Comparisons on multi-demand scaled failure cases are observations at a stated threshold, not extensions of the theorem.

| Missing premise | Counterexample and consequence |
| --- | --- |
| Original capacities | `ordered_residual`: capacity 10, requests 9.9999 then 10. At `q=2^-10` the second gets zero instead of about .0001. `large_residual` accumulates 500 units of error from 1000 prior requests even with both residuals above 1. No finite q gives a uniform relative error on arbitrarily small later residuals. |
| Direct request | `expanded_leaf`: parent volume 1 becomes eight units at `q=1/8`, apportioned `(2,2,1,1,1,1)`. The first leaf delivers 1/4 versus 1/6; the direct-conversion allowance fails. |
| Exact scaled product | `scaled_product`: `(2^28+1)·(1-2^-28+2^-53)` rounds in binary64 to `2^28`, before conversion. Its exact excess is `234881025/2^53`. Making q finer cannot undo multiplication rounding; the MSD allowance includes it. |
| Positive carrying capacities / live shares | `zero_member`: equal splitting over links of capacity 5 and 0 admits one whole unit on the first member; fluid lossless delivery is zero. A dead source share has the same relative-error obstruction. |
| One shared DAG | `supplied_dags`: 100 repeated route entries on four nodes align 500 remainders although the graph count is 14. Delivery is `253/128` versus fluid 2 at `q=2^-14`. Graph size cannot bound arbitrarily repeated program contexts. |
| Equal lossless allocation | `weighted_lossy`: weights `(1000,1,…,1)` over 20 members give error `57361/2038`, beyond an equal-split estimate. `lossy_sharing`: offers `(5,1,1)` on capacity 3 get `(3,0,0)`, versus proportional `(15/7,3/7,3/7)`. |
| Fixed controller program | `controller`: exits 30.0007 and 10 produce weights `(3,1)` at q=1 and `(30721,10240)` at q=2^-10. A bound for a fixed program does not bound controller construction. |
| Continuous tunnel setup | `tunnel_threshold`: capacities 6 and 4, volume `8+2^-12`, two head-established tunnels. Exact setup delivers 6; automatic `q=2^-11` delivers `8+2^-11`. Any finite q has nearby setup thresholds; no uniform precision theorem follows. |
| Prepared count and full capacities | `later_count`: capacity 1, q=1/8, one prepared tunnel has size 8 units; sixteen later tunnels have size zero. The prepared count cannot protect arbitrary later counts or depleted capacities. |
| Uncapped or prepared offer | `finite_offer`: capacity 100 and offer 1 at q=2^-9 return 512 units, versus uncapped 51200. `later_offer`: a new offer 1/128 at q=1/32 rounds to zero. No positive q gives a uniform relative input bound for arbitrarily small new offers. |
| Numeric bounds met | `floor_input`: 2^-40 at q=2^-32 rounds to zero. `range`: two links of 2^41 and volume .001 force q=2^-18 and miss p=.001. Legal exponent and native range limits can prevent the requested target. |
| Closed MSD bracket | `msd_limit`: capacity 10, volume 1 and alpha_max=1 return limit 1 although the physical threshold is 10. A finer q cannot close a search stopped at its configured limit. |

Adding delivery error budgets gives a budget for their total. A failure delivery divided by baseline delivery (BAC) needs a separate ratio bound and a positive baseline; [the ratio calculation](PROOFS.md#2-theorem-a-one-in-scope-demand-lossless) explains why a delivery target is not the same ratio target. No q defines a relative error against a zero denominator. Route choice, total cost and several ordered optimized flows have no general certificate here.

## Why 0.26.0 uses this rule

In 0.25, preparation tries powers of two and propagates exact `Fraction` split bounds through each candidate. Placements, MSD probes and failure cases repeat that propagation to report misses. The local bound concerns an amount at each split rather than the final bottleneck: the `fanin50` example delivers 2.953125 versus fluid 3 at the old q=2^-10, a 1.5625% shortfall despite meeting the old local target. At the static q=2^-17 it delivers 393172 units, or 2.999664306640625.

Historical profiling on 2026-10-28, using released NetGraph 0.25.0/Core 0.12.0 with one worker, attributes roughly 80–90% of DC-BB and large leaf-spine runs to repeated split checks. These are rough attribution observations, partly on battery, rather than controlled release timing:

| Workload | 0.25 preparation | 0.25 run | Same run with repeated checks off after preparation |
| --- | --- | --- | --- |
| DC-BB, 12 sources, MSD and 40 failure draws | 2.87 s | 8.47 s | 0.80 s |
| DC-BB, 96 sources, MSD and 40 failure draws | 11.04 s | 23.45 s | 4.42 s |
| Leaf-spine, 512 leaves / 32 spines, MSD and 40 draws | 3.44 s | 2.83 s | 0.33 s |

The results on these inputs are byte-identical when only the post-preparation repeats are disabled. The Python propagation holds the GIL; removing it restores useful worker parallelism. Disabling preparation's old checks as well changes q and answers, so deleting repeated work alone does not justify choosing an arbitrary quantum. The released performance effect is recorded in [0.26.0, Fixed](../../../CHANGELOG.md#0260---2026-10-29).

| Alternative | Why it is not the selector |
| --- | --- |
| Finest range-valid q | Simple and very fine on ordinary inputs, but abandons the explicit target/count tradeoff and may add probes to searches whose depth depends on integer magnitudes. A finer q does not monotonically improve actual answers at discontinuities. The static rule supplies a useful scoped theorem without per-case propagation. |
| Per-link remainder counts | Tighter for one DAG, but needs reachability work over that program. Failure cases can change the DAG, requiring counts again or a separate conservative envelope. The graph-wide count avoids that repeated machinery. |
| Exact rational bandwidth | Split denominators can grow without bound along successive fan-outs. This replaces whole-unit forwarding and tunnel semantics and changes every native kernel; it is a different model. |
| Certified floating point | Correct decisions at ties still require exact work or certified intervals with refinement. That reintroduces exactness machinery throughout native kernels rather than choosing a unit once. |

## Worked selector checks

`reference.py` is standard-library-only and imports no product code. `examples.py` holds literal expected values and recomputes them independently. The core selector examples derive as follows; the remaining boundary calculations appear above and in the proofs.

| Example | Independent calculation |
| --- | --- |
| `readme` | 12 nodes, 18 links: L=48, Γ=14, c_min=50. q=2^-9, p'=7/12800. Four sources each get 12800 of 51200 units; the two spine links each carry their full 25600 units. MSD returns 1. Counting links once gives the wrong q=2^-8. |
| `square_mesh` | 4 nodes, 6 links and 12 pair leaves: L=16, Γ=72, q=2^-17, p'=9/16384. The capacity-1 direct pair saturates at alpha 1. Counting declarations gives the wrong q=2^-13. |
| `set_uses` | Two nodes, one capacity-1 link, two leaves and p=1/4: simultaneous-only Γ=3 gives q=1/16; explicitly requested Γ=6 gives q=1/32. |
| `binary64_precision` | On one capacity-10 link, Γ=3 and p=.3: the binary64 value is below 3/10, so `p·10/3 < 1` selects q=1/2. Treating p as exact 3/10 incorrectly selects q=1. |
| `fanin50` | L=360, Γ=92. The first spine load is `22·2622+28·2621=131072`; one more source remainder overflows. Thus the maximum admitted total is `50·7863+22=393172`. MSD returns 491/16384. |
| `docs_paths`, `docs_paths_q1` | L=20, Γ=7. The bottleneck receives `ceil(floor(I/2)/2)`: capacity 8192 at q=2^-12 admits I=32769. At declared q=1 it admits 9, versus fluid 8, with p'=7/2 and target unmet. |
| `input_rounding` | Capacity 100 and volume 1.0156: input bound .0020312 selects q=2^-9 and 520 units. Ignoring the volume selects q=2^-5 and 32 units. |
| `te_link` | Capacity 1.00015, Γ=3, q=2^-12: 4096.6144 units round to max flow 4097. |
| `tunnels_p01` | 14 nodes, 13 links, 12 heads × 16 tunnels at p=.1: Γ=12+192=204, q=2^-8 and 2560 delivered units. Omitting tunnels selects q=2^-4. |
| `selected_tunnel_endpoints` | Nodes S1, S2, T with only a capacity-1 link S1–T: L=5 and the floor is 13/4. With 16 tunnels per head and p=1/2, selecting S1 gives t=16, Γ=77/4 and q=1/64; selecting S1 and unreachable S2 gives t=32, Γ=141/4 and q=1/128. Both head-established and controller-planned tunnels have the same runtime roster containing only S1 in either selection. |
| `dcbb12` | 3077 nodes, 20992 links, two combine leaves: L=45061, Γ=45069/2, q=2^-16, p'=45069/52428800. Fluid MSD alpha is 1152/125; the conditional band and bracket permit `{589/64,1179/128,295/32}`. |
| `unbounded` | No positive input or capacity: q=2^32, both bounds and achieved budget absent, target_met true. |
| `validation_case` | An explicit weight vector with two entries prepares on a two-direction graph and delivers 100; one entry is refused at preparation with workflow context. |

The DC-BB runtime scenario `scenarios/dcbb12.yml.gz` and compressed expanded graph fixture are both used: the example reader decompresses the YAML for NetGraph; the independent reference reads the graph's physical capacities, costs and names. The fixture is the expansion of the bundled YAML. It is a synthetic regression topology, not a claim to reproduce a deployed network. The YAML hash checks its decompressed bytes; the graph hash checks its compressed payload. The scenario is stored with `gzip -9n` for reproducible compression. Each failure comparison uses the run's actual excluded nodes and links. The three helpers and these inputs form a self-contained bundle.

## Running the examples

From the repository root, activate the repository's development environment, then run:

```sh
python -B docs/design/static-q/examples.py reference
python -B docs/design/static-q/examples.py plants
python -B docs/design/static-q/examples.py mutants
python -B docs/design/static-q/examples.py ngraph
```

Each mode prints checked values and a final `SUMMARY`, and exits nonzero on a mismatch. Native mode asserts NetGraph 0.26.0 imports from this checkout and Core 0.12.0 from the interpreter's environment; it prints their actual origins and hashes. It arms a timeout for each runtime scenario. Reference and native modes check independently derived expected values; plants poison expected values to check rejection; mutants change one reference rule at a time, including removal of only the binary64 allowance.

For a production plant, copy the checkout and this bundle to an isolated development checkout, then change `floor = Fraction(nodes + directed_links, 4) + 2` to `floor = Fraction(nodes + directed_links, 4) + 1` in `ngraph/analysis/units.py`. Run native mode with that copy's editable environment. The `readme` split count is then 13 instead of 14; native mode must fail. Restore the isolated copy after the experiment. The reference mode remains unchanged and passes because it imports no production code.

## Open questions

- What inexpensive bound covers arbitrary supplied programs with repeated split contexts? Physical graph counts alone cannot do so.
- Can weighted, controller-built or interacting lossy programs get useful bounds without restoring per-case propagation?
- What answer-specific diagnostics would help with ordered residuals, tunnel setup thresholds and near-zero BAC baselines without implying a universal certificate?
- Would a per-link count or finest-range policy improve consumer-relevant cost enough to justify its complexity? Correct answers and repeated measurements on the same quiet machine are needed before changing the policy.
