# Proofs for static q

These derivations explain the static count in NetGraph 0.26.0. The public contract lives in
[Precision and the choice of q](../../concepts.md#precision-and-the-choice-of-q);
[the maintainer overview](README.md) defines the selector and how to run its witnesses.
Whole-unit forwarding and rounding use the rules documented in
[Units and the resolution q](../../concepts.md#units-and-the-resolution-q) and
[Routing models and admission](../../concepts.md#routing-models-and-admission).

## 0. Terms

- **Units.** A physical binary64 amount `v` becomes `round(v/q)` units, half up:
  `|q·round(v/q) − v| ≤ q/2`. Capacities `C_e = round(c_e/q)`.
- **In-scope demand.** A demand whose model is shortest-path routing with equal splits at every router and equal
  source shares (`SHORTEST_PATHS_ECMP`, or `routing: {type: shortest_paths, allocation: equal}` with equal source
  allocation) and lossless admission. Its program is one shared acyclic hop-by-hop DAG: at each router the traffic of
  every source that passes is added and split once. The public delivery promise adds the original-capacity and directly converted request conditions of §2.
  The separate optimized-throughput statement is §4; §3 is a conditional derivation, not a blanket MSD promise.
- **Fluid reference.** The same routes, roster and destinations, with every split exactly equal: a total `T` puts
  `T·f_e` on member `e`. Lossless fluid answer `X = min(R_phys, X_c)`, `X_c = min_e a_e/f_e` over the members with
  `f_e > 0`, `a_e` an original physical carrying capacity independently rounded to `C_e`. The public comparison
  does not use residuals depleted by earlier independently rounded requests.
- **Split.** The roster split (`S` members) and each router with `k ≥ 2` members. `m(k) = ⌊k/2⌋⌈k/2⌉/k ≤ k/4`.
  `Γ_P = Σ_splits m(k)`.
- **Graph count.** `L` = nodes plus directed edges of the physical network (each link counts twice).

**Conversion and report derivation.** For `n = floor(v/q + 1/2)`, `n-1/2 ≤ v/q < n+1/2`, hence
`|qn-v| ≤ q/2`. If `v ≥ v_min > 0` and `input_bound.met`, `q/2 ≤ p·v_min ≤ p·v`. Missing denominators have
no relative meaning. A floor/range/manual choice can leave either bound unmet. Exact-ratio comparisons and range
scanning implement the definitions in the selector in [README.md](README.md#the-selector): coarsening cannot increase any nonnegative rounded amount or
capacity sum, so the first passing range choice is the finest permitted by that scan. The report's scalar is the
maximum of the two numeric ratios, not an answer-error measurement. Fixed q and the count/report fields are
definitions. `scaled_units` converts `fl(alpha·V)`; the conversion inequality concerns that value, not exact `alpha·V`.
All examples here use finite normal scaled products; no relative normal-product lemma is asserted for underflow.

## 1. Lemmas

**Lemma 1 (deviation identity).** For an in-scope program and any integer total `I`,
`L_e(I) − I·f_e = Σ_σ Σ_i r_{σ,i}·F(σ,i → e)`: `r_{σ,i}` is member `i`'s whole-unit share at split `σ` minus the
exact equal share of what `σ` divided (`Σ_i r_{σ,i} = 0`, each in `(−1, 1)`), and `F(σ,i → e) ∈ [0, 1]` the fluid
fraction of a unit entering member `(σ,i)` that crosses `e`.

*Proof.* At router `v` with integer inflow `n_v` and fluid inflow `I·φ_v`, member `e` at position `i` carries
`n_v/k_v + r_{v,i} = I·f_e + (n_v − Iφ_v)/k_v + r_{v,i}`, and `n_v − Iφ_v` is the roster remainder at `v` (if `v` is
a source) plus the deviations of the members entering `v`. `F` obeys the same recursion with one unit in place of a
remainder. Induction over the members in topological order (positive costs make the program acyclic). ∎

**Lemma 2 (one round-robin split).** With `ρ = n mod k`, `r_i = 1 − ρ/k` on the first `ρ` members and `−ρ/k` on the
others. For any `F_i ∈ [a, b]`, `|Σ_i r_i F_i| ≤ ρ(k − ρ)/k·(b − a) ≤ m(k)(b − a)`, with equality when `F_i = b` on
the first `ρ` members and `a` on the rest.

*Proof.* `Σ r_i F_i = (1 − ρ/k)Σ_{i<ρ} F_i − (ρ/k)Σ_{i≥ρ} F_i`; extremes at the stated assignment. ∎

**Corollary 1.** `|L_e(I) − I·f_e| ≤ Δ_e := Σ_σ m(k_σ)·(max_i F(σ,i→e) − min_i F(σ,i→e)) ≤ Γ_P`. `Δ_e` depends on
the routes only: not on `I`, `q` or any amount.

## 2. Theorem A: one in-scope demand, lossless

**Preconditions.** (a) One in-scope demand with a nonempty roster and every injected share reaching a destination. (b) Every member with
`f_e > 0` has original physical capacity `a_e > 0` and its available units are `C_e = round(a_e/q)`; write
`a_min` for the smallest. (Equal splitting sends every member its share; a zero-capacity member makes the fluid answer
0: remark 2.) (c) Its finite request is `R = round(R_phys/q)` units, converted directly from binary64 `R_phys`. It is neither an
expanded leaf nor a binary64 scaled product compared against the exact mathematical product.

**Statement.** If `q(Γ_P + 3/2) ≤ p·a_min`, the delivery `A = q·min(R, I*)` satisfies
`|A − X| ≤ p·X + q/2`; if moreover `|qR − R_phys| ≤ p·R_phys` (a directly converted request at or above `v_min` when the input bound is met), `|A − X| ≤ p·X`.

**Proof.** If no edge carries positive fluid share, all roster shares are already at destinations: both models
only convert the request. The absolute error is at most q/2; the input condition gives the relative bound. Otherwise `a_min` and `X_c` below exist.
Let `H = min_e (a_e − q(Δ_e + ½))/f_e`. Every integer `I ≤ H/q` fits: `L_e(I) ≤ I f_e + Δ_e ≤
(a_e − q/2)/q ≤ C_e` (with `C_e` the available units, `q C_e ≥ a_e − q/2`). The fitting totals are an initial
segment (each quotient/remainder share is nondecreasing in its integer total), so `qI* ≥ H − q`. Since `f_e ≤ 1`, `X_c ≥ a_min`, so
`H − q ≥ X_c(1 − q(Γ_P + ½)/a_min) − q ≥ X_c(1 − q(Γ_P + 3/2)/a_min) ≥ X_c(1 − p)`. Upper: at `I*` every member has
`I* f_e − Δ_e ≤ C_e`; at the fluid binding member `b`, `qI* ≤ (a_b + q/2 + qΔ_b)/f_b ≤ X_c(1 + p)`. The request:
`qR ∈ [R_phys − q/2, R_phys + q/2]`. `min` is monotone in both arguments, so
`A ∈ [min(R_phys − q/2, X_c(1 − p)), min(R_phys + q/2, X_c(1 + p))] ⊆ [X(1 − p) − q/2, X(1 + p) + q/2]`; with the
request condition the `q/2` terms become `±p·R_phys` and the interval `[X(1 − p), X(1 + p)]`. ∎

**Tightness.** `S` sources, two members each, every first member toward a link of capacity `c`: at totals where every
share is odd that link receives `S/2` units above fluid, `Δ = S/2`, and the answer is `qS/(2c)` below fluid (the
50-source fan-in of the examples reaches this up to rounding).

**Remarks.**
1. *Above fluid.* Whole units can deliver more: the `docs_paths_q1` example delivers 9 at `q = 1` where the fluid
   answer is 8; the upper side is needed.
2. *Zero capacity or a dead share.* Fluid gives 0; whole units admit every total whose remainders keep the dead
   member at 0, at most `qΔ_e/f_e`. Example: two parallel members, the second of capacity 0: one unit is admitted. No
   relative bound exists.
3. *Later demands.* The independently rounded-capacity premise holds for a demand placed alone/first or on links
   earlier demands have not used. A positive lower residual, even `a_min ≥ c_min`, does not bound the discrepancy
   between integer and fully proportional residuals. `large_residual`: 1000 requests of `1051/131072` consume
   526000 units at q=2^-16, instead of fluid 525500; the final residuals are 129360q and 129860q, both above 1.
   The error 500q exceeds `pX+q/2`. A theorem applied to a common fixed residual would be a different reference.
4. *Link flows.* Write `J = min(R, I*)` for the admitted units, not the uncapped total `I*`.
   `|q L_e(J) − X·f_e| ≤ qΔ_e + f_e|A − X| ≤ qΓ_P + p f_e X + q/2 ≤ 2p·a_e + q/2`,
   because `qΓ_P ≤ p a_min ≤ p a_e` and `f_e X ≤ a_e`.
5. *Totals and BAC.* A total of several deliveries adds their bounds. A ratio `D/B` of two deliveries with errors at
   most `p·D` and `p·B` errs by at most `2p/(1 − p)` relative; with absolute errors `e_D` and `e_B < B`, by
   `(e_D + (D/B)e_B)/(B − e_B)` absolute. A zero baseline has no relative bound.

## 3. Theorem B: conditional MSD derivation (not the public delivery promise)

**Preconditions.** (a) Every demand of the set is in scope, with a nonempty roster and every injected share reaching a destination. (b) Positive available capacity on every member of
positive aggregate load; the fluid threshold `α* = min_e c_e/g_e`, `g_e = Σ_d V_d f^d_e`, is finite and positive.
(c) The search ends with `search_status` `feasible` and `stop_reason` `tolerance` (a feasible and an infeasible
tested alpha at most `alpha_tolerance` apart). (d) No probe at or below the answer is `below_resolution`. (e) Every scaled root product used in this relative
argument is finite and normal (or exact); leaves come from equal apportionment of that root. These are additional
conditions, not a preparation report certificate for arbitrary MSD runs.

**Lemma (unit fit).** A probe delivers every request iff `Σ_d L^d_e(R_d(α)) ≤ C_e` on every edge (if every demand is
full the loads add and fit; conversely each request fits on the earlier demands' residual and lossless admission
takes it whole). `R_d` and `L^d_e` are monotone in `α`: feasibility is downward closed.

**Statement.** Let `u = 2^-53` and `η_B = q·max_e (Σ_d (Δ^d_e + f^d_e·b_d) + ½)/c_e`, where `b_d < 1` bounds demand
`d`'s request deviation in units (`½` for a directly rounded total; below 1 for a leaf of an equal expansion tree, by the induction below). Then
`|α_MSD − α*| ≤ α*·(η_B + u)/(1 − u) + alpha_tolerance`.

**Expansion lemma.** A once-rounded root has error at most 1/2 unit against its scaled binary64 value. If a parent
has error magnitude below 1 and splits into n equal children, a child inherits at most `|error_parent|/n` plus
`(n-1)/n` from quotient/remainder apportionment, strictly below 1. Induction gives `b_d < 1` at every leaf; n=1
just carries the parent's bound. Direct roots use `b_d=1/2`. Thus ordinary expanded leaves cannot use A's direct
`q/2` request premise.

**Proof.** Requests are formed from the binary64 product `fl(α·V_root) = αV_root(1 + δ_root)`, `|δ_root| ≤ u`, then rounded once and apportioned.
For leaf volume `V_d` (its exact share of the root), use the same root multiplier and its leaf error `b_d`:
So `|q Σ_d L^d_e − α g_e| ≤ q Σ_d (Δ^d_e + f^d_e b_d) + u·α g_e`. If `α ≤ α*(1 − η_B)/(1 + u)` every edge fits
(`α g_e(1 + u) + qΣ(...) ≤ c_e − q/2 ≤ qC_e`); if `α > α*(1 + η_B)/(1 − u)` the fluid binding edge overflows. The
unit-fit cutoff lies in between, within `α*(η_B + u)/(1 − u)` of `α*`; a closed bracket puts the reported alpha within
`alpha_tolerance` below the cutoff. ∎

**Corollary B1.** With `q·Σ_d(Γ_d + 1) + q/2 ≤ p·c_min`, `η_B ≤ p`, and `(p + u)/(1 − u) ≤ p + 2^-52` for `p ≤ ½`:
`|α_MSD − α*| ≤ α*(p + 2^-52) + alpha_tolerance`.

**Not covered.** `limit`, `range`, `stagnation`, `none_feasible` and `trivial` endings (example: a link of 10,
`V = 1`, `alpha_max = 1` stops at 1 where `α* = 10`); sets with optimised, tunnel, weighted, lossy or supplied
programs (not fixed equal-split programs).

## 4. Theorem C: one optimised maximum flow

**Preconditions.** One demand or capacity question whose model solves a maximum flow with optimised source allocation
and no tunnel count (`TE_MAXFLOW_UNLIM`, `SHORTEST_PATHS_MAXFLOW`, MaxFlow's default), over a fixed allowed support,
alone on its capacities.

**Statement.** The **uncapped** engine question returns `F_q = q·maxflow(C)` exactly (integral maximum flows exist for integer capacities;
Core's solver returns one, certified by its minimum cut). For the physical maximum flow `F`: if `q ≤ 2p·c_min`, then
`F(1 − p) ≤ F_q ≤ F(1 + p)`. With a finite request, the answer `min(q·round(V/q), F_q)` is within `p·min(V, F)` of
`min(V, F)` when `q ≤ 2p·V` as well.

**Proof.** Every positive capacity rounds within `q/2 ≤ p·c_e`, so every cut's capacity scales by a factor in
`[1 − p, 1 + p]` (zero edges stay zero); the minimum over cuts keeps the factor. The request part is the input bound
and the monotonicity of `min`. ∎

**Not covered.** Route choice, the flow vector, `total_cost`, several optimised demands placed in order (each is
exactly optimal on the residual it sees, but the earlier flows are not unique), equal or weighted source allocation
(a different objective).

## 5. Count bound: the count covers split contexts, not all answer premises

For one shared hop-by-hop DAG under any eligibility (failure case), any alpha and any roster: each router contributes
at most `outdegree/4` and the roster at most `S/4`, so `Γ_P ≤ L/4`. For `k ≥ 1` in-scope demands of a set,
`Σ_d (Γ_d + 1) + ½ ≤ k(L/4 + 1) + ½ < k(L/4 + 2)`; for one demand, `Γ_P + 3/2 ≤ L/4 + 2`. So
`q·max(k, 1)·(L/4 + 2) ≤ p·c_min` meets the numeric
split-count inequalities used by A and B when the report's split bound is met. This counting statement holds for
failure-case shared DAGs, probes and later single shared-DAG questions. It supplies none of their other premises:
independently rounded original capacities, direct request conversion, positive carrying capacity, reachability,
normal products and a closed MSD bracket must still be checked where used. Weighted, supplied, lossy and controller
programs are excluded. In particular this is not a theorem about arbitrary later offers or tunnel counts. ∎

**False beyond this scope.** A supplied program with repeated DAG entries keeps one split context per entry: 100
copies of one DAG on a 4-node graph (`L = 48`, `Γ = 14`) align 500 remainders on one link, and at `q = 2^-14` the
delivery is 253/128 against a fluid 2. Lossy forwarding with weighted
splits exceeds an equal-split lossy estimate (20 parallel members, weights 1000:1×19: error 28.15 units against a
budget of 24 at `q = 1`).

## 6. The tunnel term

**Statement.** If `q·t ≤ p·c_min`, where `t ≥ 1` counts the tunnels of the demands placed together (each head times its
tunnels per head), then every link of positive capacity holds at least `t/p − ½ ≥ 1/p − ½` units, so a controller
layout (T2) for a head with an allowed positive-capacity path, planned on the full capacities, whose `K ≤ t` tunnels cross any link at most `K` times, has a
capacity-limited common size of at least `⌊1/p − ½⌋ ≥ 1` unit per tunnel for `p ≤ ½`.

**Proof.** `C_e ≥ c_e/q − ½ ≥ c_min/q − ½ ≥ t/p − ½`. Routing every tunnel on any live path gives a layout whose
common size is at least `min_e C_e/K`; the planner's largest common size is no smaller. ∎

The premise uses the **actual** count `t` and full capacities. The prepared tunnel term counts all selected source
endpoints of each expansion leaf or capacity pair, including sources with no static route to a destination; a pool
counts as one head. It can therefore exceed the runtime tunnel count and supplies a conservative upper bound for
covered prepared counts, not for arbitrarily larger later counts. In `selected_tunnel_endpoints`, S1 and S2 are
selected but only S1 reaches T: preparation counts 32 tunnels while the runtime roster contains only S1 with 16.
With capacity 1, p=1/2, one prepared tunnel, Γ=4 and q=1/8,
the prepared size is 8 units; 16 later tunnels have size floor(8/16)=0 (`later_count`).

This protects only against a live head planned with zero units per tunnel (example: at `p = 0.1`, 12 heads × 16
tunnels on a link of 10 deliver 0 without the term at `q = 2^-4` and 10 with it at `2^-8`). It is not a precision
bound: a design-limited size, setup thresholds (E1) and later demands on a residual are outside it.

## 7. Counterexamples and limits

- **E1. Tunnel setup thresholds.** Links of 6 and 4, one demand of volume `8 + 2^-12` with two tunnels set up by the
  head (T1). Exact amounts: each tunnel asks `4 + 2^-13`, the second finds 4 free on the link of 4 and stays down, and
  the first carries 6. With the tunnel term omitted, `q = 2^-10`, and the request rounds to 8192 units, each tunnel asks exactly 4096,
  both come up, and 8 is delivered. At automatic `q = 2^-11` the request is 16385 units, split 8193 and 8192, and `8 + 2^-11`
  is delivered, which no request within `q/2` of the declared one gives with exact amounts (6 or at most 8).
- **E2. A later demand on a shared link.** One link of 10; demands of 9.9999 and 10 in order. Exact: the second gets
  0.0001. At automatic `q = 2^-10` the first rounds to exactly 10 and the second gets 0. This is the stated p=0.001 case, not an assertion that q is unchanged for every p.
- **E3. Supplied programs, weighted and lossy sharing.** §5.
- **E4. The WCMP controller.** Its table reads capacities in units: exits of 30.0007 and 10 get weights 3:1 at `q = 1`
  and 30721:10240 at `q = 2^-10`. A table recomputed per failure
  case can change discretely; no bound against a fluid controller is proved.
- **E5. Range.** When the rule's `q` leaves the native range, a coarser `q` misses the target (two links of `2^41`
  and a demand of 0.001: `q = 2^-18`, achieved precision `2^-18/0.002 ≈ 0.0019 > p`); the count term alone would
  report a tiny figure.

- **E6. Expanded positive pair leaves.** Six independent one-hop pairs share parent volume 1. L=7+12=19,
  Γ=6(19/4+2)=81/2, p=1/10 gives q=1/8. Parent 8 units splits (2,2,1,1,1,1); the first delivery 1/4 differs
  from 1/6 by 1/12, exceeding p/6+1/16=19/240. This is an apportionment example, not direct conversion.
- **E7. Scaled-product boundary and single-term mutant.** Let V=2^28+1, p=2^-57 and
  alpha=1-2^-28+2^-53. Then exact alpha*V=2^28+234881025/2^53. The binary64 product rounds down to 2^28:
  its excess is less than half the upper binade's ulp 2^-24. L=4, Γ=3 gives automatic q=2^-31 with both numeric
  bounds met. The rounded product is already whole units, so conversion error is zero. Total error exceeds
  p*X+q/2 but lies within `(p+2^-52)*X+q/2`. `scaled_product.binary64_band_covers` is true; removing **only**
  2^-52 makes it false. No unrelated perturbation is present in the mutant.
- **E8. Finite and later offers.** On capacity 100 with declared offer 1, Γ=3 and v_min=1 give q=2^-9:
  finite throughput is 512 units; uncapped throughput is 51200. With no declared offer, q=1/32, and later offer
  1/128 rounds from 1/4 unit to 0, a relative error of 1. Preparation's input flag does not cover this new input.
- **E9. Resolution floor and incomplete MSD.** A declared input 2^-40 at legal floor q=2^-32 is 1/256 unit,
  rounds to zero, and has relative error 1. Capacity 10, volume 1 and alpha_max=1 return MSD limit 1 instead of
  fluid threshold 10. No search-bracket precision theorem applies to that limit.
- **E10. Weighted and lossy examples.** On 20 parallel members, weights (1000,1*19), offer
  1000*24002+19*24001=24458019, and capacities (2*offer,24000.5*19), half-up q=1 capacities admit all integer
  weighted shares (24002000,24001*19). Fluid shares on the small links exceed 24000.5; delivery is
  offer*1000/1019 + 19*24000.5, smaller by 57361/2038. For simultaneous offers (5,1,1) on capacity 3, the three
  highest averages are 5,5/2,5/3, all from the first offer, giving (3,0,0). Fluid proportional shares are
  (15/7,3/7,3/7). These are excluded classes, not counterexamples to A.

**Executable witnesses.** `boundaries.py` computes E6–E10 without importing production and exercises them against
the current checkout and its native runtime. E1, E2, E4 and the zero-member example are in `examples.py`/`boundaries.py` as well.
For the supplied program in §5, `supplied_dags` derives its load by two nested quotient/remainder splits and builds
the native 100-entry program. With I=32384, 84 entries get 324 units and 16 get 323; each sends 164 or 163 units to
the bottleneck, for 16384 units exactly. At I=32385 that bottleneck gets 16385. Thus delivery is 32384/16384=253/128
against fluid 2. Controller weights follow gcd-reduction of rounded exits: gcd(30,10)=10 and
gcd(30721,10240)=1. Their distinct tables explain why a fixed-program theorem cannot certify controller construction.

The other public exclusions are statements of scope, not extra impossibility theorems: no general route-vector,
optimized-cost, multiple-optimized-demand, stale/lossy-sharing or ratio precision certificate is claimed. The
conditional ratio formula in §2 explains why a delivery budget alone would not be the same ratio budget.
