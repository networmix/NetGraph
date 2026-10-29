# How NetGraph computes

How a scenario becomes numbers. Each section explains one idea in plain words, then states the exact rule, then runs one small example; the documentation tests run every example and check its numbers. Each section uses only the ones before it, so read the page in order.

The examples are Python. Most build their scenario from YAML text, so YAML users can read the scenario as they would write it. Most also fix `q` to 1, so that units equal physical bandwidth; for amounts this small that misses the default precision target, and their units reports say so ([Precision and the choice of q](#precision-and-the-choice-of-q)). They share this setup:

```python
from ngraph import Scenario, prepare, run


def converged(result, step=0):
    """One step's answer without failures: its baseline case, converged state (see Failures below)."""
    return result.steps[step].result.cases[0].states["converged"]


def forward_flows(prepared, vector):
    """A per-edge vector (one entry per link direction) as {link id: units}, forward only."""
    return {
        ref.link: int(units)
        for ref, units in zip(prepared.topology.edge_refs, vector)
        if units and ref is not None and ref.direction == "forward"
    }
```

## Scenario, preparation and run

A scenario is a description: a network, the traffic on it and an ordered list of questions. Preparation reads it once and builds the graph that every question runs on, read-only, with one bandwidth unit. A run asks the questions in order and returns immutable result envelopes. Editing the network after preparation does not change a prepared graph: prepare again to see the edit.

Four terms first, so that later sections can use them:

- **Network:** named nodes and the physical links between them.
- **Demand:** a volume of traffic from a set of source nodes to a set of destination nodes.
- **Workflow step:** one question the run asks, such as a maximum flow or a placement of a demand set.
- **`q`:** the size of one bandwidth unit; [Units and the resolution q](#units-and-the-resolution-q) gives the rule.

**The rule.**

- `Scenario` declares inputs. `prepare` takes a read-only view of the scenario, builds one immutable native graph, chooses `q` and binds the demand sets the steps need. It changes nothing in its input, and later edits of the scenario or its network do not reach the prepared scenario.
- `run` executes the steps in declaration order and returns immutable result envelopes that belong to that run. Each step records the question it asked (an analysis's own typed query, or a built-in domain step's configuration), its order and where its seed came from. Built-in results and plain JSON custom results are read-only. A registered custom result is published as it is, so its own type controls whether it can change.
- A custom step's own data is not frozen ([Records and editing](reference/api.md#records-and-editing)). A failed call publishes nothing partial ([Guarantees](reference/design.md#guarantees)).

**Example.** A capacity question asks how much can flow from one set of nodes to another. The prepared scenario keeps the capacity it was prepared with:

```python
from ngraph import CapacityQuery, Link, Network, Node, Selector, UnitsSettings, capacity

network = Network()
for name in ("A", "B", "C"):
    network.add_node(Node(name))
network.add_link(Link("A", "B", capacity=10))
network.add_link(Link("B", "C", capacity=10))
question = CapacityQuery(Selector("^A$"), Selector("^C$"))


def most_from_a_to_c(prepared):
    return capacity(prepared, question).cases[0].states["converged"].rows[0].result.delivered


prepared = prepare(Scenario(network, units=UnitsSettings(resolution=1)))
network.replace_link("A|B|0", capacity=4)
assert most_from_a_to_c(prepared) == 10
assert most_from_a_to_c(prepare(Scenario(network, units=UnitsSettings(resolution=1)))) == 4
```

In the reference: [Workflow Steps](reference/workflow.md); Python `Scenario`, `prepare`, `run`, `PreparedScenario` ([Python API](reference/api.md#prepare-and-query)).

## Links, directions and what is enabled

A physical link is a cable: traffic can cross it both ways, and each way has the link's full capacity. Traffic from A to B therefore never competes with traffic from B to A.

**The rule.** Every physical link gives the graph a forward edge (source to target) and a reverse edge, each with the link's capacity and cost. A link's id is `source|target|n`, where `n` counts the links added between that ordered pair of nodes, from 0. A link is enabled when it and both of its end nodes are enabled.

**Example.** Two opposing demands of 10 on one link of 10 both arrive in full:

```python
prepared = prepare(Scenario.from_yaml("""
units: {resolution: 1}
network:
  nodes: {A: {}, B: {}}
  links: [{source: A, target: B, capacity: 10}]
demands:
  both_ways:
    - {source: ^A$, target: ^B$, volume: 10}
    - {source: ^B$, target: ^A$, volume: 10}
workflow:
  - {type: TrafficMatrixPlacement, name: place, demand_set: both_ways}
"""))
assert list(prepared.scenario.network.links) == ["A|B|0"]
assert converged(run(prepared)).totals.delivered_units == 20
```

In the reference: link keys in [Scenario YAML](reference/dsl.md#network-topology); `DirectedLink` ([Python API](reference/api.md#prepare-and-query)).

## Units and the resolution q

The engine counts bandwidth in whole units, never in fractions, so that every answer is exact and repeatable. Preparation picks the size of one unit, `q`, and converts every capacity and volume to a whole number of units by rounding. What the engine computes (delivered traffic, losses, flows on links) comes back in units: multiply by `q` for physical bandwidth. The inputs themselves, and NetworkStats capacities, stay physical.

**The rule.**

- A legal `q` is one power of two from 2^-32 through 2^32; `units: {resolution: auto}` (the default) lets preparation choose it ([Precision and the choice of q](#precision-and-the-choice-of-q)).
- Capacities, demand volumes and every other bandwidth amount a scenario declares are physical amounts. Preparation reads each as a binary64 number (a Python float) and converts it to units with exact half-up rounding: an amount of 10.5 units becomes 11.
- Native bandwidth results are exact integer units; multiply them by `q` only when presenting physical bandwidth. Recorded inputs, offers and designs, and `NetworkStats` capacities remain physical amounts.
- Whole units are split by fixed arithmetic. Units split equally (round robin) go `I // k` to each of `k` members and one more to the first `I % k` in a fixed order, so 10 over 3 members gives 4, 3, 3. A weighted split (highest averages) hands them out one at a time to the member with the largest weight over its count plus one, ties to the earlier member, so 5 over weights 2 and 1 gives 4 and 1. The engine's exact rule: [Splitting whole units](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#splitting-whole-units).

**Example.** At `q` = 0.25 a link of 10 is 40 units, and a volume of 2.625 is 10.5 units, rounded up to 11:

```python
prepared = prepare(Scenario.from_yaml("""
units: {resolution: 0.25}
network:
  nodes: {A: {}, B: {}}
  links: [{source: A, target: B, capacity: 10}]
demands:
  small: [{source: ^A$, target: ^B$, volume: 2.625}]
workflow:
  - {type: NetworkStats, name: stats}
  - {type: TrafficMatrixPlacement, name: place, demand_set: small}
"""))
result = run(prepared)
totals = converged(result, step=1).totals
assert prepared.topology.q == 0.25
assert totals.reference_request_units == 11
assert totals.delivered_units * prepared.topology.q == 2.75
assert result.steps[0].result.total_capacity == 10
```

The demand delivers 11 units, 2.75 physical; NetworkStats reports the link's physical capacity, 10.

In the reference: `units` in [Scenario YAML](reference/dsl.md#units-and-input-validation); `units_report.q` in [Results](reference/results.md).

## Routing models and admission

A model says two things about a demand: how its traffic chooses routes and divides among them (the routing), and what happens to traffic that does not fit (the admission). Shortest-path routing works like IP routing: each router sends traffic toward the destination over its lowest-cost next hops, the neighbours on a lowest-cost route. Equal-cost multipath (ECMP) divides the traffic equally among those next hops at each router, not equally over whole paths: a router with two next hops gives each half, however many paths lie behind them. Lossless admission refuses before it enters whatever the routes cannot carry; lossy admission sends everything and loses what does not fit on the way.

**The rule.** Each preset names one model; a demand or MaxFlow step can instead declare the model itself. A capacity question (the MaxFlow step) asks how much one model delivers between two node sets; it can fix the traffic sent (`offer`) and the traffic the routes are planned for (`design_demand`), both physical amounts.

| Model (YAML `routing.type`) | Python | What it does |
| --- | --- | --- |
| `shortest_paths`, `allocation: equal` | `ShortestPaths` EQUAL | Each router splits equally among its lowest-cost next hops (ECMP) |
| `shortest_paths`, `allocation: weighted` | `ShortestPaths` WEIGHTED | Each router splits in proportion to declared integer weights (WCMP); the `SHORTEST_PATHS_WCMP` preset weighs each next hop by its link's physical capacity |
| `shortest_paths`, `allocation: optimized` | `ShortestPaths` OPTIMIZED | Chooses the flow itself on the lowest-cost routes only: as much as they carry, the cheapest way |
| `centralized_te` without a `tunnel_count` | `CentralizedTE` without a count | Chooses the flow itself on any route: as much as the network carries, the cheapest way |
| `distributed_te` | `DistributedTE` | Each source router sets up its own paths, setting bandwidth aside for them before traffic flows (explained in [Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)) |
| `centralized_te` with a `tunnel_count` | `CentralizedTE` with a count | A central planner gives every source router the same number of equal single paths (explained in [Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)) |
| `pinned` | `Pinned` | Routes the scenario supplies (named routes), or a native program |

- **Programs.** A program is a model's routing decision written down: the routes and how each router splits. Named routes and native `Pinned` programs are supplied programs.
- **Splitting at each router.** Equal and weighted routing split at every router of the routes by the whole-unit rules of [Units and the resolution q](#units-and-the-resolution-q): round robin over the next hops in a fixed order, or highest averages over their weights. Where the routes of several sources of one demand meet, their traffic is added and split once.
- **Members that can carry nothing.** Shortest-path routing keeps its lowest-cost routes even when a link on them has no capacity: equal splitting still gives that next hop its share, capacity weighting gives it weight 0. Both divide a demand equally over its sources ([Demands: how traffic enters](#demands-how-traffic-enters)).
- **The optimizing models.** `TE_MAXFLOW_UNLIM` and `SHORTEST_PATHS_MAXFLOW` may choose different flows and routes from each other and from the splitting models.
- **Admission.** Results keep admitted, injected, carried and lost units apart. Lossless admission admits the largest total whose splits fit everywhere and refuses the rest, as unadmitted traffic. Lossy admission sends the whole volume, and it is lost at sources without a usable route (source drops) or on links (edge drops). The optimizing models are lossless.

**Example.** A reaches D over A-B-D, A-C-X-D and A-C-Y-D, every link of cost 1 except B-D (cost 2), and C-X carries at most 2:

```python
paths = """
units: {resolution: 1}
network:
  nodes: {A: {}, B: {}, C: {}, X: {}, Y: {}, D: {}}
  links:
    - {source: A, target: B, capacity: 100}
    - {source: B, target: D, capacity: 100, cost: 2}
    - {source: A, target: C, capacity: 100}
    - {source: C, target: X, capacity: 2}
    - {source: C, target: Y, capacity: 100}
    - {source: X, target: D, capacity: 100}
    - {source: Y, target: D, capacity: 100}
demands:
  lossless: [{source: ^A$, target: ^D$, volume: 12, preset: SHORTEST_PATHS_ECMP}]
  lossy: [{source: ^A$, target: ^D$, volume: 12, preset: SHORTEST_PATHS_ECMP_LOSSY}]
workflow:
  - {type: TrafficMatrixPlacement, name: lossless, demand_set: lossless, outputs: {edge_flows: true}}
  - {type: TrafficMatrixPlacement, name: lossy, demand_set: lossy, outputs: {edge_flows: true}}
"""
prepared = prepare(Scenario.from_yaml(paths))
result = run(prepared)
lossless, lossy = converged(result, step=0), converged(result, step=1)
assert (lossless.totals.delivered_units, lossless.totals.unadmitted_units) == (9, 3)
assert forward_flows(prepared, lossless.rows[0].result.edge_flows) == {
    "A|B|0": 5, "B|D|0": 5, "A|C|0": 4, "C|X|0": 2, "C|Y|0": 2, "X|D|0": 2, "Y|D|0": 2,
}
assert (lossy.totals.delivered_units, lossy.totals.edge_drop_units) == (11, 1)
assert forward_flows(prepared, lossy.rows[0].result.edge_flows)["C|X|0"] == 2
```

A has two next hops, B and C, and C has two, X and Y. Lossless: 9 units is the most whose splits fit. A gives 5 to B (the first next hop takes the odd unit) and 4 to C, and C gives 2 each to X and Y; a tenth unit would send 3 to X. Splitting over the three paths would have put a third on each. Lossy: all 12 enter, A sends 6 each way, C sends 3 to X, and 1 unit is lost on C-X.

In the reference: presets in [Scenario YAML](reference/dsl.md#presets); [MaxFlow](reference/workflow.md#maxflow); `admission` and the drop fields in [Results](reference/results.md).

## Demands: how traffic enters

A demand's volume is multiplied by the step's multiplier, alpha, and turned into whole units once. Those units are then divided by fixed arithmetic: over the source-destination pairs the demand expands into, and, in a demand with several sources, over its sources in a fixed order. The order matters under lossless admission: every source receives its share, so one source that cannot carry its share limits the whole demand.

**The rule.**

- **Alpha** is the demand multiplier: a step places each declared volume times alpha (1 by default). The scaled physical volume is converted to units once, so 1.05 at alpha 2.5 is 2.625, 11 units at `q` = 0.25, not 2.5 × 4 units.
- **Expansion.** A demand's selectors and modes expand it into a fixed tree of physical parents and integer split leaves ([Traffic Modes](reference/dsl.md#traffic-modes-mode), [Group Modes](reference/dsl.md#group-modes-group_mode)). Each declared physical total is converted to units once, then split by integer quotient and remainder in canonical order (groups sorted by label, then nodes sorted by name), after excluding self pairs and same-label group pairs. At `q` = 1, a parent of 10 split into two groups and the second into three gives 5 and (2, 2, 1). Branches whose only pairs are node-to-itself or same-label group pairs are removed recursively; the remaining hierarchy keeps its shape. Empty selections keep their reported discarded shares, which are never redistributed, and a declaration with no eligible pair is reported whole as discarded with its reason. Declared units equal resolved plus discarded units.
- **The source roster.** A `combine` demand has one ordered roster of participating sources. For equal and weighted shortest-path routing, these are the selected, allowed sources with a static route to an allowed destination, in node order. Zero capacity does not remove a source from this roster; having no such route does. Equal and weighted shortest-path routing give each source an equal share by round robin over the roster, so the first sources take the odd units, and pool the traffic where the sources' routes meet. Under lossless admission a zero-capacity source keeps its share, so earlier sources in the roster can receive units before it blocks the rest. Optimized source allocation (`source_allocation: optimized`, as in `TE_MAXFLOW_UNLIM`) instead chooses how much each source sends.
- **Losses.** A demand loses units by not admitting them (lossless: `unadmitted_units`, traffic never sent) or by dropping them (lossy): at sources without a usable route (`source_drop_units`) and on links (`edge_drop_units`). Dropped traffic is the two together. The reference request is the scaled declared request; the shortfall is that request minus the delivery, every unit not delivered, and the delivery ratio is the delivery over the request.

**Example.** One demand from S1 and S2 to T, volume 12 at alpha 2.5, so 30 units; each source has one link to T. The capacities decide how much the equal shares admit:

```python
roster = """
units: {resolution: 1}
network:
  nodes: {S1: {}, S2: {}, T: {}}
  links:
    - {source: S1, target: T, capacity: %s}
    - {source: S2, target: T, capacity: %s}
demands:
  both: [{source: ^S, target: ^T$, volume: 12}]
workflow:
  - {type: TrafficMatrixPlacement, name: place, demand_set: both, alpha: 2.5}
"""
delivered = {}
for first, second in ((100, 10), (10, 100), (5, 0), (0, 5)):
    totals = converged(run(prepare(Scenario.from_yaml(roster % (first, second))))).totals
    assert totals.reference_request_units == 30
    delivered[first, second] = totals.delivered_units
assert delivered == {(100, 10): 21, (10, 100): 20, (5, 0): 1, (0, 5): 0}
```

S1 is first in the roster. With 100 and 10 it takes 11 units and S2 10, so 21 fit, more than twice the smaller capacity. With the order reversed, S1 would need 11 of its 10, so 20 fit. A source of capacity 0 admits nothing once its turn comes: after S1's one unit, or at once when it is first.

In the reference: [Traffic Modes](reference/dsl.md#traffic-modes-mode) and [Group Modes](reference/dsl.md#group-modes-group_mode); `alpha` in [TrafficMatrixPlacement](reference/workflow.md#trafficmatrixplacement); placement totals in [Results](reference/results.md).

## Precision and the choice of q

NetGraph accounts for bandwidth in whole units of `q`. Conversion of a nonnegative finite binary64 amount `v` uses the nearest whole unit, half up: `floor(v/q + 1/2)`. Its physical error is at most `q/2`. For positive inputs collected at preparation, relative conversion error is at most the target `p` only when the units report's `input_bound.met` is true. A scaled volume is first multiplied in binary64: `q/2` bounds conversion of that product, not its difference from the exact mathematical product.

**How q is chosen.** Preparation chooses one `q` for every placement, failure case, MSD probe and later question. The automatic choice is the largest power of two from `2^-32` through `2^32` satisfying `q ≤ 2p·v_min` and `q·Γ ≤ p·c_min`. Here `v_min` is the smallest positive prepared bandwidth input (capacity, declared volume, workflow offer, design demand or minimum unreserved bandwidth), `c_min` is the smallest positive link capacity, and `0 < p ≤ 0.5` (`0.001` by default). A bound with no positive amount is omitted.

Let `L` be the number of network nodes plus twice the number of links, including disabled ones. For each prepared group of demands placed together, `k` counts lossless shortest-path leaves with equal router and source splits; `t` counts the heads times tunnels per head of its tunnel leaves. Each bound demand set is a group, each workflow capacity pair is a separate group, and each tunnel-count row is a group. A pool is one head; presets use 16 or 256 tunnels per head, an explicit count uses that count, an `up_to` uses its limit, and a count step uses its largest count or limit. The count is `Γ = max(L/4 + 2, max_groups(max(k, 1)·(L/4 + 2) + t))`. Other leaves add nothing. Opaque custom workflow callbacks add only the floor; their unknown tunnels are uncounted, like later questions. Pool heads and attachment edges are excluded from `L`.

A demand set used only by simultaneous placement steps adds nothing to the count. A set named by any other workflow step (an ordered placement, MSD or tunnel-count step) or requested in `prepare(..., demand_sets=...)` counts its leaves by their declared models.

If either bound needs a unit below `2^-32`, preparation starts at `2^-32` and reports the unmet bound. If an input or augmented capacity sum reaches `2^62` units, it takes the finest coarser unit that fits; if none fits, it refuses. `units: {resolution: <power of two from 2^-32 through 2^32>}` declares `q` instead and is checked for range. The report gives `limited_by`, `input_bound.met`, `split_bound.met` and the scalar `achieved_precision = max(q/(2·v_min), q·Γ/c_min)` over present terms. `target_met` means that scalar is absent or at most `p`; it does not certify every analysis.

**Why this count is used.** It gives a delivery bound under these conditions, which must all hold for the comparison:

- There is one demand, placed alone on original capacities or on links no earlier demand has used.
- Its finite physical request `R` is converted directly to units, without apportioning a rounded parent or treating a binary64 scaled product as the exact mathematical product.
- Router and source allocations are equal, admission is lossless, and routing is one fixed shared acyclic hop-by-hop program, such as `SHORTEST_PATHS_ECMP`. Traffic arriving from different sources merges before each router splits it once. The source roster is nonempty and every source share reaches a destination. The proportional comparison uses the same roster, destinations, routes and member order.
- Every edge carrying a positive proportional share has positive original capacity, and the report's `split_bound.met` is true.

Let `X` be this demand's delivery with exact equal proportional splits on the original physical capacities. Then whole-unit physical delivery `A` satisfies `|A − X| ≤ p·X + q/2`. If also `q ≤ 2p·R`, the stronger bound is `|A − X| ≤ p·X`; a directly converted positive prepared request meets this condition when `input_bound.met` is true. For this same demand, each link flow differs by at most `2p` times that link's physical capacity plus `q/2`. A changed failure-case DAG can use the theorem only if all these conditions still hold, including positive carrying capacities and every source share reaching a destination.

For example, six nodes and seven links in the routes of [Routing models and admission](#routing-models-and-admission) give `L = 20`, one lossless equal-split demand and `Γ = 7`. With smallest capacity 2 and `p = 0.001`, the split bound is `0.002/7` and the input bound `0.004`, so `q = 2^-12`. The lossless demand delivers 32769 units, or 8.000244140625, against proportional delivery 8. C-X holds 8192 units; round robin sends C 16384 of 32769 units and X 8192 of those. One more unit would send X 8193. At declared `q = 1`, delivery is 9 and the split bound is unmet.

**Outside this domain.** No bound against proportional splitting is promised for these uses; the following runs show the distinctions.

- Several demands in order: on capacity 10, 1000 earlier requests of `1051/131072` each round from 525.5 to 526 units at `q = 2^-16`. The last demand gets 129360 units against proportional 129860. Both residuals exceed an unrelated smallest capacity of 1; a large residual alone does not restore the theorem.
- Expanded pair leaves: a parent request of 1 over six independent pairs, each with capacity 1000, at `p = 0.1` gives `q = 1/8`. The eight parent units split as `(2, 2, 1, 1, 1, 1)`. The first pair delivers `1/4` against proportional `1/6`, outside the directly converted request's `q/2` allowance.
- Scaled placements and MSD answers: with volume and capacity `2^28 + 1`, `p = 2^-57`, `q = 2^-31` and alpha `1 − 2^-28 + 2^-53`, binary64 multiplication gives delivery `2^28`. The exact product exceeds it by `234881025/2^53`, more than `p·X + q/2`. Conversion itself is exact in this run. MSD additionally depends on its search bracket: on capacity 10 and volume 1, `alpha_max = 1` stops at 1 though the proportional threshold is 10.
- Later questions and tunnel counts: preparation of capacity 100 alone chooses `q = 1/32`; a later finite offer `1/128` converts to zero. A capacity-1 model prepared with one tunnel at `p = 0.5`, `q = 1/8`, permits eight units per tunnel; a later request for 16 tunnels has capacity-limited size zero. Neither the new offer nor the larger count was covered by preparation's inputs and counts.
- Supplied programs: 100 repeated entries of one DAG over four nodes retain separate splits and deliver `253/128` against proportional 2 at `q = 2^-14`.
- Weighted routing: 20 parallel members with weights `(1000, 1, …, 1)`, offer 24458019, first capacity twice that offer and other capacities 24000.5 deliver the full offer with lossy admission at `q = 1`; the proportional answer is smaller by `57361/2038`. The equal-split theorem does not apply.
- Lossy service, including simultaneous sharing: three offers `(5, 1, 1)` on capacity 3 at `q = 1` deliver `(3, 0, 0)`, against proportional `(15/7, 3/7, 3/7)`. Lossy presets and stale forwarding have no certificate from this theorem.
- Tunnels: two tunnels set up by their head on parallel capacities 6 and 4 for volume `8 + 2^-12` deliver 16385 units at automatic `q = 2^-11`, or 8.00048828125, while exact setup gives 6. Setup is a discrete decision before forwarding.
- The WCMP controller: exits of 30.0007 and 10 produce weights `(3, 1)` at `q = 1` and `(30721, 10240)` at `q = 2^-10`. The routes and weights are not fixed across these units.
- Zero carrying capacity: equal splitting over parallel capacities 5 and 0 delivers one unit at `q = 2^-10`, against proportional zero.

Ratios of deliveries, optimized route choices, flow vectors, `total_cost`, and several optimized demands placed in order have no precision promise here.

**Optimized maximum flow.** Separately, one uncapped maximum-flow question with optimized source allocation, fixed allowed support and original capacities returns the exact maximum flow on the rounded capacities. If `q ≤ 2p·c_min`, its throughput is within relative `p` of the physical optimum. If that maximum is `F_C` whole units, a finite offer `V` instead returns `min(F_C, floor(V/q + 1/2))` whole units; relative `p` additionally requires `q ≤ 2p·V`. On capacity 100 with declared offer 1, `q = 2^-9` returns 512 units (1); the uncapped maximum is 51200 units (100). A later offer needs its own input condition.

In the reference: `units` in [Scenario YAML](reference/dsl.md#units-and-input-validation); `UnitsReportJSON` in [Results](reference/results.md#unitsreportjson).

## Tunnels and TE ingress pools

Traffic-engineering models send traffic over tunnels: single paths set up from a source router, the tunnel's head, to the destination before traffic flows. In `distributed_te` each head sets up its own tunnels and sets bandwidth aside on every link of each one, a hold (or reservation). In `centralized_te` with a `tunnel_count`, one controller lays out the tunnels of every head. A tunnel count is the layout, how many tunnels each head gets; it does not say how much traffic arrives.

**The rule.**

- **Set up by the heads (T1, `distributed_te`).** The design is split equally over the heads, and each head's share equally over its tunnels; each tunnel asks for its part. The tunnels are set up one at a time, each on the shortest path whose links all have enough unreserved bandwidth. A tunnel that comes up holds exactly its request on every link of its path; one that finds no such path stays down and holds nothing. Holds decide which tunnels come up, never what traffic gets through: a tunnel carries what forwarding gives it, within the free capacity. `distributed_te` requires `tunnel_count: {per_head: N}` and accepts `min_unreserved_bandwidth` (a physical amount, which filters the setup and is never held) and a cost ceiling. The engine's exact rule: [T1: tunnels set up by their heads](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#t1-tunnels-set-up-by-their-heads).
- **Laid out by the controller (T2, `centralized_te` with a `tunnel_count`).** The controller gives every head the same number of single-path tunnels of one common whole-unit size. It picks the largest size, then no more than the design needs, then the cheapest routes; the planned size is never held. The engine's exact rule: [T2: the controller's equal tunnels](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#t2-the-controllers-equal-tunnels).
- **Counts, designs and offers.** Counts are per head. `design_demand` sizes the layout; `offer` is the traffic forwarded through it. A row's `count` is the requested count or the `up_to` limit, while `plan.tunnels_per_head` is the chosen count; with `up_to`, the controller chooses the smallest count that carries the live heads' design shares, not the count that delivers most of the offer. A reservation is not carried traffic and is not added to the carried flows.
- **TE ingress pools.** Combined sources asked with `TE_ECMP_16_LSP` or `TE_ECMP_UP_TO_256_LSP` share one private head, a TE ingress pool, for placement and capacity alike. Its private attachments to the selected physical sources have finite capacity bounds and cost 1; they belong to their declared demand or MaxFlow question, are labelled as synthetic and never become ordinary transit endpoints. Preparation builds one for each such demand and MaxFlow step (one pool per source set for a MaxFlow step), and a library `CapacityQuery` with that preset as its `declaration` uses the prepared pool of exactly its sources, or is refused. `resolve_demands` refuses a pool id whose sources differ from its prepared ingress.
- **A pool's offer budget** is 0 unless a step gives it a known lossy offer; [Ordered and simultaneous placement](#ordered-and-simultaneous-placement) adds a second source of one. A `TunnelCountAnalysis` step's offer is such an offer for the pools of its set: each pool's attachments widen to carry it (the headroom penalty prices them), and a library `tunnel_counts` query above that budget is refused. The offer and design take part in choosing `q`, so they can make `q` finer for every step of the run.

**Example.** First a head with two tunnels of 5 over links of 6 and 4; then a controller's counts over links of capacity 1 (cost 1) and 100 (cost 2):

```python
head = prepare(Scenario.from_yaml("""
units: {resolution: 1}
network:
  nodes: {S: {}, T: {}}
  links:
    - {source: S, target: T, capacity: 6}
    - {source: S, target: T, capacity: 4}
demands:
  te:
    - source: ^S$
      target: ^T$
      volume: 10
      model: {routing: {type: distributed_te, tunnel_count: {per_head: 2}}}
workflow:
  - {type: TrafficMatrixPlacement, name: place, demand_set: te,
     outputs: {edge_flows: true, edge_reservations: true}}
"""))
placed = converged(run(head)).rows[0].result
assert [tunnel.status.name for tunnel in placed.by_tunnel] == ["UP", "INSUFFICIENT_BANDWIDTH"]
assert forward_flows(head, placed.edge_reservations) == {"S|T|0": 5}
assert (placed.delivered, placed.unadmitted) == (6, 4)

counts = run(prepare(Scenario.from_yaml("""
units: {resolution: 1}
network:
  nodes: {S: {}, T: {}}
  links:
    - {source: S, target: T, capacity: 1, cost: 1}
    - {source: S, target: T, capacity: 100, cost: 2}
demands:
  te:
    - source: ^S$
      target: ^T$
      volume: 0
      model:
        routing: {type: centralized_te, source_allocation: equal, tunnel_count: {per_head: 1}}
workflow:
  - {type: TunnelCountAnalysis, name: counts, demand_set: te,
     counts: [1, 2], up_to: 3, design_demand: 2, offer: 1000}
""")))
rows = counts.steps[0].result.rows
assert [(row.count, row.up_to, row.result.plan.tunnels_per_head, row.result.delivered)
        for row in rows] == [(1, False, 1, 100), (2, False, 2, 101), (3, True, 1, 100)]
```

The first tunnel holds 5 on the link of 6. The second asks 5 and finds 1 and 4 free, so it stays down. All traffic takes the one tunnel, which carries 6, more than its hold, because the link has room. The controller's one tunnel takes the wide link; two tunnels use both links and deliver 101 of the offer of 1000. Up to 3 chooses one tunnel: it carries the design of 2, so a second is not needed, though it would deliver more.

In the reference: [TunnelCountAnalysis](reference/workflow.md#tunnelcountanalysis); `edge_reservations` in [Output selection](reference/workflow.md#output-selection); `pool` in [Results](reference/results.md).

## Routing domains and the WCMP controller

A routing domain describes a fabric: interior routers that run one routing protocol (the IGP domain) and edge routers at its border (the BGP edge), toward which traffic is sent. A WCMP controller computes once, for each edge destination, weights that tell routers how to split traffic toward it, so that a fabric with uneven exits carries more than equal splitting would. Within one demand set, every `SHORTEST_PATHS_WCMP` demand toward that destination forwards on the same table; another demand set has its own table.

**The rule.**

- **The routes.** Toward a destination t the routes are one DAG (a set of routes without loops): one reverse shortest-path search inside the IGP domain from the exits (domain nodes with an eligible link to t), every eligible exit link, and every eligible uplink from another BGP-edge router into a domain node that reaches an exit. Nothing enters a BGP-edge router but t, so no other one carries transit. With no exit the DAG is empty and the demand finds no route.
- **The tables.** The controller (`wcmp_controller`) computes one weight table per demand set and destination for the `SHORTEST_PATHS_WCMP` demands toward that destination. A programmed demand has one destination, in `bgp_edge`; its sources lie in either population. `routing` constrains the controller only; ECMP and TE demands keep their own models.
- **The scopes.**
    - `next_hop` (the default): the source routers of demands with a positive volume split over their next hops by progressive filling: each next hop grows in proportion to what it carries alone, and stops when a link it uses fills. Routers are processed downstream first, so a programmed router's integer weights shape the loads of routers above it.
    - `group`: each programmed source router splits by its declared tree ([Forwarding groups and their caps](#forwarding-groups-and-their-caps)).
    - `all_routers`: every router on the sources' walks is programmed from one native flow over the DAG whose sources send in proportion to the demands' exact declared volumes (a multi-source demand divides its volume over its sources that reach t).
- Every other router splits equally over its next hops, zero-capacity ones included (ECMP). Each demand forwards on the shared table through its own native program; the controller forwards nothing itself. The tables are computed on the network without failures and do not change with alpha.

**Example.** S reaches T through two exits, X1 with 30 toward T and X2 with 10:

```python
domain = """
units: {resolution: 1}
network:
  nodes: {S: {}, X1: {}, X2: {}, T: {}}
  links:
    - {source: S, target: X1, capacity: 100}
    - {source: S, target: X2, capacity: 100}
    - {source: X1, target: T, capacity: 30}
    - {source: X2, target: T, capacity: 10}
routing:
  igp_domain: {path: '^X'}
  bgp_edge: {path: '^(S|T)$'}
wcmp_controller: {scope: next_hop}
demands:
  wcmp: [{source: ^S$, target: ^T$, volume: 40, preset: SHORTEST_PATHS_WCMP}]
  ecmp: [{source: ^S$, target: ^T$, volume: 40, preset: SHORTEST_PATHS_ECMP}]
workflow:
  - {type: TrafficMatrixPlacement, name: wcmp, demand_set: wcmp}
  - {type: TrafficMatrixPlacement, name: ecmp, demand_set: ecmp}
"""
prepared = prepare(Scenario.from_yaml(domain))
[table] = prepared.demand_sets["wcmp"].controller
[router] = table.programmed
assert router.router == "S" and [m.weight for m in router.members] == [3, 1]
result = run(prepared)
assert converged(result, step=0).totals.delivered_units == 40
assert converged(result, step=1).totals.delivered_units == 21
```

Alone, X1 carries 30 and X2 10, so both grow 3 to 1 and fill together: S's weights are 3 and 1, and all 40 arrive. Equal splitting fills X2's 10 first and admits 21 (11 and 10).

In the reference: [Routing domains and the WCMP controller](reference/dsl.md#routing-domains-and-the-wcmp-controller); `controller` in [Results](reference/results.md).

## Forwarding groups and their caps

Under the `group` scope an operator declares, per programmed router, how its traffic divides: a tree of groups whose top-level shares are fixed caps, as in a router's forwarding configuration. Inside a group, members share by their own weights. A member that cannot reach the destination gets nothing, and its group's share goes to the members that can.

**The rule.** Root shares are fixed caps, normalized once; child shares split within their parent. A member that can carry nothing alone (it meets a zero-capacity link or a dead branch) gets 0, and its group re-flattens over its live members within its cap. A root group with no live member is refused: the preset's lossless admission would stop the demand at the first unit sent into it. Weights too large for the engine are approximated and reported ([Weight approximation](reference/dsl.md#weight-approximation)).

**Example.** S splits between a group with X1 and a group with X2 and X3, half each; X3's link toward T has capacity 0 in the second run:

```python
groups = """
units: {resolution: 1}
network:
  nodes: {S: {}, X1: {}, X2: {}, X3: {}, T: {}}
  links:
    - {source: S, target: X1, capacity: 100}
    - {source: S, target: X2, capacity: 100}
    - {source: S, target: X3, capacity: 100}
    - {source: X1, target: T, capacity: 100}
    - {source: X2, target: T, capacity: 100}
    - {source: X3, target: T, capacity: %s}
routing:
  igp_domain: {path: '^X'}
  bgp_edge: {path: '^(S|T)$'}
wcmp_controller: {scope: group}
forwarding_groups:
  edge:
    router: S
    groups:
      - share: 1
        children: [{edge: {link: 'S|X1|0', direction: forward}}]
      - share: 1
        children:
          - {edge: {link: 'S|X2|0', direction: forward}}
          - {edge: {link: 'S|X3|0', direction: forward}}
demands:
  d: [{source: ^S$, target: ^T$, volume: 40, preset: SHORTEST_PATHS_WCMP}]
workflow:
  - {type: TrafficMatrixPlacement, name: place, demand_set: d, outputs: {edge_flows: true}}
"""
for x3, weights, flows in (
    (100, [2, 1, 1], {"S|X1|0": 20, "S|X2|0": 10, "S|X3|0": 10}),
    (0, [1, 1, 0], {"S|X1|0": 20, "S|X2|0": 20}),
):
    prepared = prepare(Scenario.from_yaml(groups % x3))
    [table] = prepared.demand_sets["d"].controller
    assert [m.weight for m in table.programmed[0].members] == weights
    state = converged(run(prepared))
    assert state.totals.delivered_units == 40
    assert {link: units for link, units in forward_flows(prepared, state.rows[0].result.edge_flows).items()
            if link.startswith("S|")} == flows
```

With X3 live, the second half splits between X2 and X3: weights 2, 1, 1. With X3 dead, it re-flattens onto X2 within its cap of one half: weights 1, 1, 0, and all 40 still arrive.

In the reference: `forwarding_groups` in [Scenario YAML](reference/dsl.md#routing-domains-and-the-wcmp-controller).

## Failures: patterns, cases and states

A failure policy says which nodes and links can fail together. NetGraph draws from it a number of times (`iterations`); each draw is a set of failed nodes and links, a failure pattern. Equal patterns are evaluated once, as one failure case that counts how often it was drawn. A placement reports each case in up to three failure states, which model the moments after a failure: routing has recomputed (`converged`), the old forwarding is still in place (`stale`), or routers have removed the dead routes without computing new ones (`repair`).

**The rule.**

- **Draws and cases.** A failure rule matches among all declared nodes, links or risk groups, disabled ones included, taken in sorted identifier order. A draw picks one mode by weight and applies its rules in declaration order; seeds follow [Seeds](reference/dsl.md#seeds). A draw's pattern is every node and link it fails, the members of failed risk groups included. Equal patterns are one case, computed once: `occurrences` counts the draws that gave it, and with `failure_trace` its trace is the first of them. The baseline, the case without failures, comes first and is not an extra draw: draws that fail nothing count in its `occurrences`, which can be 0, so the cases' `occurrences` sum to `iterations`. The other cases follow in the order of their first draw. A step without a failure policy makes its `iterations` draws with nothing failed; a library query without a `FailureRequest` has the baseline alone, with 0 occurrences. Every draw is made before any case is computed, so the cases are the same for any number of workers.
- **Coverage.** Draws are random and independent, so they need not produce every pattern a policy allows. A policy that fails one of `n` links (one `choice` rule of count 1 without `weight_by`) picks each link with equal chance in each draw, and `n` draws usually miss some. Each pattern drawn is one case, so every link was drawn exactly when the step has `n` failure cases besides the baseline. `n` × ln(`n`/ε) draws, rounded up, miss some link with chance at most ε: 32 draws for 5 links at ε = 1 %.
- **What a failure changes.** A failure removes the failed nodes and links, both directions of each failed link, from what the case can use, so when the demands are computed again (the converged state below), a source that failed or lost every route is out of the source roster. It never changes a declared volume, not even one whose endpoint failed. Each case keeps the prepared `q`.
- **The states.** Each case reports its states through a common states mapping: capacity its converged state, placement its requested failure states (`[converged]` by default; `stale` and `repair` only when listed), each computed separately, from a network that carries no traffic yet. Stale forwarding replays a demand's program unchanged while failed elements swallow what reaches them; repair drops the failed routes and re-splits over the survivors, with no new search. No state is guaranteed to deliver at least as much as another: for any two of them, some cases deliver more in one and some in the other, and `converged`, computed again, can deliver less than `repair`. The engine's exact rule: [Forwarding programs](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#forwarding-programs).
    - `converged`: the demands computed again on the failed network. Controller tables are rebuilt for the case; declared forwarding-group shares stay fixed caps. A root group with no live member keeps its fixed cap and is listed in the state's `dead_caps`. Lossless admission stops before the first unit assigned to a dead member; lossy forwarding (for example a simultaneous step, [Ordered and simultaneous placement](#ordered-and-simultaneous-placement)) drops the units assigned to that group at its router. A case whose program would forward that share differently is refused with the group, case and state.
    - `stale`: each demand's program from the case without failures, forwarded unchanged and lossy at that baseline's admitted total; traffic that reaches a failed node or link is lost there.
    - `repair`: the same programs with failed routes removed and survivors re-split (no new route search), at the declared request and admission; group shares stay caps.
- `reference_request_units` stays the scaled request in every state; the native `requested` and `offered` describe each call. Every case and state of a step therefore has the same request, and NetGraph does not rank them: the worst case of a state is the one that delivers least, with the largest shortfall and the lowest `delivery_ratio`. A state's shortfall is its unadmitted and dropped units; in `stale` it also counts those the baseline did not admit. Cost reports come from converged rows only. For an explicit-route demand alone, converged and repair forward the same program.
- **Forwarding failure.** The bounded forwarding calculation can cycle or reach its round limit. That case and state then reports a forwarding failure, with no rows; this does not prove that no stable answer exists. In the baseline it stops the step when stale or repair needs its programs.
- **Groups inside the domain.** Group scope refuses converged and repair under a failure policy when it programs a router inside the IGP domain, where other demands can transit the router after a failure and a dead group's dropped share would cut them too; `stale` works there.

**Example.** A centralized-TE demand of 20 from S to T over S-A-T and S-B-T (cost 2, capacity 10 each) and S-C-T (cost 3, capacity 10); one of A-T and B-T fails per draw, over five draws:

```python
failures = prepare(Scenario.from_yaml("""
seed: 1
units: {resolution: 1}
network:
  nodes: {S: {}, A: {}, B: {}, C: {}, T: {}}
  links:
    - {source: S, target: A, capacity: 10}
    - {source: A, target: T, capacity: 10}
    - {source: S, target: B, capacity: 10}
    - {source: B, target: T, capacity: 10}
    - {source: S, target: C, capacity: 10}
    - {source: C, target: T, capacity: 10, cost: 2}
failures:
  one_exit:
    modes: [{weight: 1, rules: [{scope: link, mode: choice, count: 1, path: '^(A|B)\\|T'}]}]
demands:
  te: [{source: ^S$, target: ^T$, volume: 20, preset: TE_MAXFLOW_UNLIM}]
workflow:
  - {type: TrafficMatrixPlacement, name: te, demand_set: te, failure_policy: one_exit,
     iterations: 5, failure_states: [converged, stale, repair]}
"""))
baseline, *failed = run(failures).steps[0].result.cases
assert baseline.case.occurrences == 0 and len(failed) == 2
assert sum(case.case.occurrences for case in failed) == 5
for case in failed:
    states = {name: (state.totals.delivered_units, state.totals.unadmitted_units,
                     state.totals.edge_drop_units) for name, state in case.states.items()}
    assert states == {"converged": (20, 0, 0), "stale": (10, 0, 10), "repair": (10, 10, 0)}
```

The five draws give two patterns, A-T failed and B-T failed, and the baseline is not an extra draw. Without failures the demand uses the two cost-2 routes, 10 each. Converged: the controller computes again and moves 10 to S-C-T. Stale: the old program still sends 10 into the failed link, where it is lost. Repair: the old program loses its failed route and re-splits onto the survivor, which carries 10; lossless admission refuses the other 10.

A dead cap under a failure: S splits half to X1 and half to X2 under the group scope, and X2's link to T fails:

```python
dead_cap = prepare(Scenario.from_yaml("""
units: {resolution: 1}
network:
  nodes: {S: {}, X1: {}, X2: {}, T: {}}
  links:
    - {source: S, target: X1, capacity: 100}
    - {source: S, target: X2, capacity: 100}
    - {source: X1, target: T, capacity: 100}
    - {source: X2, target: T, capacity: 100}
routing:
  igp_domain: {path: '^X'}
  bgp_edge: {path: '^(S|T)$'}
wcmp_controller: {scope: group}
forwarding_groups:
  edge:
    router: S
    groups:
      - children: [{edge: {link: 'S|X1|0', direction: forward}}]
      - children: [{edge: {link: 'S|X2|0', direction: forward}}]
failures:
  x2_exit:
    modes: [{weight: 1, rules: [{scope: link, mode: all, path: '^X2\\|T'}]}]
demands:
  d: [{source: ^S$, target: ^T$, volume: 40, preset: SHORTEST_PATHS_WCMP}]
workflow:
  - {type: TrafficMatrixPlacement, name: place, demand_set: d, failure_policy: x2_exit,
     failure_states: [converged, stale]}
"""))
baseline, failed = run(dead_cap).steps[0].result.cases
converged_state, stale_state = failed.states["converged"], failed.states["stale"]
[cap] = converged_state.dead_caps
assert (cap.router, cap.group, cap.cap) == ("S", 1, 0.5)
assert converged_state.totals.delivered_units == 1
assert (stale_state.totals.delivered_units, stale_state.totals.edge_drop_units) == (20, 20)
```

The second group has no live member, but its cap of one half stays. Lossless admission takes one unit (to X1, first) and stops before the next, which would go to the dead group. Stale forwarding sends 20 each way and loses X2's 20 on the failed link.

In the reference: [`failures`](reference/dsl.md#failures-failure-policies); `failure_policy`, `iterations`, `failure_trace` and `failure_states` in [Workflow Steps](reference/workflow.md#keys-common-to-analysis-steps); `cases`, `occurrences` and `states` in [Results](reference/results.md).

## Ordered and simultaneous placement

By default a placement places its demands one after another, by priority: each demand sees the capacity the earlier ones left. Real traffic arrives at once instead: a simultaneous placement forwards every demand at the same time, and demands that meet on a full link share its losses.

**The rule.**

- `interaction: ordered` (the default) places demands in priority order, then declaration and canonical expansion order. A row's residual is the capacity left after that row.
- `interaction: simultaneous` forwards every demand at once in one native list, sharing losses on common links, as a lossy question on fixed programs: each model that can be lossy forwards a lossy copy of itself (tunnel models are set up first and keep their holds), and a live controller (`TE_MAXFLOW_UNLIM`, `SHORTEST_PATHS_MAXFLOW`) is computed, then its program forwarded lossy. Its lossy copy is created after the other participants, in every state, so it loses one-unit ties to them. Every row reports the one final residual. Rows are not comparable with the default `ordered` rows. The engine's exact rule: [Several demands at once](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#several-demands-at-once).
- A TE ingress pool in a simultaneous step gets a lossy offer budget, its largest known request, reported as the row's `pool.offer_limit_units`. Budgets are prepared once for the scenario: every placement step on that preparation reports them, and they count in the range check of `q`.

**Example.** Two demands on one link of 10, first of 10 each, then of 3 and 5:

```python
two = """
units: {resolution: 1}
network:
  nodes: {S: {}, T: {}}
  links: [{source: S, target: T, capacity: 10}]
demands:
  two:
    - {source: ^S$, target: ^T$, volume: %s}
    - {source: ^S$, target: ^T$, volume: %s}
workflow:
  - {type: TrafficMatrixPlacement, name: ordered, demand_set: two, outputs: {residual: true}}
  - {type: TrafficMatrixPlacement, name: simultaneous, demand_set: two,
     interaction: simultaneous, outputs: {residual: true}}
"""
full = run(prepare(Scenario.from_yaml(two % (10, 10))))
ordered, simultaneous = converged(full, step=0).rows, converged(full, step=1).rows
assert [(row.result.delivered, row.result.unadmitted) for row in ordered] == [(10, 0), (0, 10)]
assert [row.result.delivered for row in simultaneous] == [5, 5]
assert converged(full, step=1).totals.edge_drop_units == 10

prepared = prepare(Scenario.from_yaml(two % (3, 5)))
small = run(prepared)
left = [
    [forward_flows(prepared, row.result.residual)["S|T|0"] for row in converged(small, step).rows]
    for step in (0, 1)
]
assert left == [[7, 2], [2, 2]]
```

Ordered, the first demand takes the link and the second is refused. Simultaneous, both send 10, the link carries 10 and each loses 5. With 3 and 5, ordered rows show the residual after each (7, then 2); simultaneous rows both show the final 2.

In the reference: `interaction` in [TrafficMatrixPlacement](reference/workflow.md#trafficmatrixplacement); `residual` in [Output selection](reference/workflow.md#output-selection).

## Maximum supported demand

Maximum supported demand (MSD) asks how far the whole demand set can grow: the largest alpha at which every demand is placed in full. It searches by probes, each a placement at one alpha: from `alpha_start` it multiplies or divides alpha by `growth_factor` until one probe fits and another does not, then halves the gap between them until it is at most `alpha_tolerance`. It reports every probe, and proves its answer only where it can.

**The rule.**

- **Probes.** A probe places the set at one alpha and checks exact native-unit feasibility: every demand delivers its whole request. Its outcome is `feasible`, `infeasible`, `below_resolution` (a resolved leaf of a positive declaration requests zero units after scaling and expansion, so the probe proves nothing; it is never feasible or a certificate endpoint, and search moves up from it) or `range` (the scaled volumes leave the native range; not an infeasible congestion sample). Probes keep the prepared `q`. MSD takes no failure input.
- **The answer.** `alpha_feasible` is the largest tested feasible alpha, null if no probe was feasible; the best rows are its rows. The result does not claim an untested global maximum.
- **Statuses** (`search_status`, with `stop_reason`):

    | Status | Meaning (stop reasons) |
    | --- | --- |
    | `feasible` | The gap between a feasible and an infeasible alpha closed to `alpha_tolerance` (`tolerance`) |
    | `limit` | A feasible alpha was found but the search hit `alpha_max` (`alpha_bound`) or its iteration limit (`bracket_limit`, `bisect_limit`) |
    | `none_feasible` | No tested alpha was feasible: `alpha_min` remained infeasible (`alpha_bound`), an iteration limit was reached (`bracket_limit`, `bisect_limit`), or no feasible nonzero probe was found before the unit-resolution threshold or `alpha_max` (`unit_resolution`). |
    | `range` | A probe's scaled volumes left the native range (`offer_range`) |
    | `stagnation` | The next bracketing value equals the current alpha, or a bisection midpoint rounds to a bracket endpoint (`representable_limit`). |
    | `trivial` | The set offers nothing (all volumes zero or discarded); one probe at `alpha_max` succeeded (`nothing_offered`) |

- **Proofs.** Only a proved downward-closed class (any alpha below a feasible one is feasible) receives an upper certificate: the feasible and the infeasible probe that bracket the answer. Fixed programs (equal or weighted splitting on static routes, supplied programs and WCMP controller tables, which are built once and do not change with alpha) and one centralized-TE demand without a tunnel count (weighted sources included), or one optimized shortest-paths demand with a static route choice (`FEWER_HOPS` or `HIGHER_CAPACITY`), alone in its set, are proved; live controllers beside other demands, tunnel layouts and TE ingress pools are not. A proof is about feasibility, not delivery: delivery can fall as alpha grows. The bounded search on an unproved set is a heuristic.
- A later step can place the set at the largest tested feasible alpha (`alpha_from_step`); a simultaneous step that takes its alpha from an MSD step cannot have pool demands.

**Example.** One link of 10 and a demand of 4 (automatic `q` = 2^-7); then a demand of 3 at `q` = 1, starting at alpha 1/8:

```python
msd = """
units: {resolution: %s}
network:
  nodes: {A: {}, B: {}}
  links: [{source: A, target: B, capacity: 10}]
demands:
  d: [{source: ^A$, target: ^B$, volume: %s}]
workflow:
  - {type: MaximumSupportedDemand, name: msd, demand_set: d, alpha_start: %s}
"""
search = run(prepare(Scenario.from_yaml(msd % ("auto", 4, 1)))).steps[0].result
certificate = search.upper_certificate
assert search.alpha_feasible.value == 2.5
assert (search.search_status, search.stop_reason, search.proof) == ("feasible", "tolerance", "fixed_program")
assert (certificate.lower.value, certificate.upper.value) == (2.5, 321 / 128)

coarse = run(prepare(Scenario.from_yaml(msd % (1, 3, 0.125)))).steps[0].result
assert [(p.alpha.value, p.outcome, p.totals.reference_request_units) for p in coarse.history[:2]] == [(1/8, "below_resolution", 0), (1/4, "feasible", 1)]
```

The search finds 5/2 (a volume of 10 on the link of 10) and proves the answer lies below 321/128, the smallest infeasible alpha it tested. In the second search, 3 × 1/8 = 0.375 rounds to 0 units, so the first probe is `below_resolution`; 3 × 1/4 = 0.75 rounds to 1 unit and fits.

In the reference: [MaximumSupportedDemand](reference/workflow.md#maximumsupporteddemand); `MSDAnalysisJSON` in [Results](reference/results.md#msdanalysisjson).

## Results and their units

A result holds numbers of different kinds, and the field names say which. Bandwidth computed by the engine is in units of `q`; amounts you declared stay physical; path and tunnel costs stay unscaled, while `total_cost` is cost times bandwidth units: multiply it by `q` for cost times physical bandwidth. In exported JSON a field that was not asked for is absent, while a field that was asked for but has no value is `null`.

**The rule.**

- **Five kinds of numbers.** Bandwidth units (every `*_units` field and the native amounts; units × `q` is physical), physical amounts (inputs, offers and designs, `NetworkStats` capacities and `split_bound.capacity`, as declared), ratios (no unit), routing costs (never multiplied by `q`; `total_cost` is cost × bandwidth units, so `total_cost` × `q` is cost × physical bandwidth) and hardware money and power. Counts are plain integers. Native integer-valued configuration fields already contain units; YAML bandwidth minima are physical and are converted at preparation.
- Each row's native result says what this call did (`call_` fields) and the demand's state after it (totals), and the two never mix. The engine's exact rule: [The result](https://github.com/networmix/NetGraph-Core/blob/v0.12.0/docs/semantics.md#the-result).
- **Export.** `write_json` writes each record's declared fields, and the results schema is generated from the same declarations. Native integer quantities stay integer, optional outputs stay absent when unrequested, and unlimited and null values remain distinct. JSON rows default to compact exact summaries, and each optional output has its own selector; Python results always hold the detail fields, while the other outputs exist only when requested ([Output selection](reference/workflow.md#output-selection)).
- **Cost reports** are computed only when `cost_distribution` is requested and only for `converged` rows. Unrestricted optimized traffic engineering (`TE_MAXFLOW_UNLIM`) reports units at each marginal cost; shortest-path routing, tunnels and named routes report units at each path cost when attribution is available. Otherwise a converged row gives `controller_table`, `mixed_cost_dag` or `unsupported_model` under `unavailable_outputs`. Stale and repair rows carry neither a report nor an unavailable reason. A report's `cost_domain` is `analysis_graph` when costs include a TE ingress pool's attachment, and `physical_network` otherwise.

**Example.** A demand of 10 over A-B (cost 1) and B-C (cost 2), at `q` = 1/8:

```python
import json
from io import StringIO

from ngraph import write_json

prepared = prepare(Scenario.from_yaml("""
units: {resolution: 0.125}
network:
  nodes: {A: {}, B: {}, C: {}}
  links:
    - {source: A, target: B, capacity: 10, cost: 1}
    - {source: B, target: C, capacity: 10, cost: 2}
demands:
  te: [{source: ^A$, target: ^C$, volume: 10, preset: TE_MAXFLOW_UNLIM}]
  ecmp: [{source: ^A$, target: ^C$, volume: 10, preset: SHORTEST_PATHS_ECMP}]
workflow:
  - {type: TrafficMatrixPlacement, name: te, demand_set: te, outputs: {min_cut: true}}
  - {type: TrafficMatrixPlacement, name: ecmp, demand_set: ecmp, outputs: {min_cut: true}}
"""))
result = run(prepared)
te = converged(result, step=0).rows[0].result
assert te.delivered == 80 and te.delivered * prepared.topology.q == 10
assert te.total_cost == 240 and te.total_cost * prepared.topology.q == 30

out = StringIO()
write_json(result, out)
steps = json.loads(out.getvalue())["steps"]
te_row, ecmp_row = (step["result"]["cases"][0]["states"]["converged"]["rows"][0]["result"]
                    for step in steps)
assert te_row["min_cut"] == [{"link": "A|B|0", "direction": "forward"}]
assert ecmp_row["min_cut"] is None
assert "edge_flows" not in te_row
```

The 10 delivered are 80 units of 1/8. The route costs 3 per unit of bandwidth, so `total_cost` is 3 × 80 = 240, and 30 after × `q`. Both steps asked for the minimum cut: the optimized demand has one, A→B; ECMP has none, so its `min_cut` is `null`. Neither asked for `edge_flows`, so the key is absent.

In the reference: [Results](reference/results.md); [Output Format](reference/cli.md#output-format).

## Glossary

The documentation uses one term for each idea. The terms the sections define, each in the section named:

- bandwidth unit `q` (YAML `units.resolution`), unit, physical amount: [Units and the resolution q](#units-and-the-resolution-q)
- physical link, direction, enabled: [Links, directions and what is enabled](#links-directions-and-what-is-enabled)
- next hop, ECMP, admission, program: [Routing models and admission](#routing-models-and-admission)
- alpha (the demand multiplier), source roster, canonical order: [Demands: how traffic enters](#demands-how-traffic-enters)
- precision target, split count, achieved precision: [Precision and the choice of q](#precision-and-the-choice-of-q)
- tunnel, head, hold (a reservation), carried traffic, TE ingress pool, offer budget: [Tunnels and TE ingress pools](#tunnels-and-te-ingress-pools)
- routing domain, table: [Routing domains and the WCMP controller](#routing-domains-and-the-wcmp-controller)
- cap, dead cap: [Forwarding groups and their caps](#forwarding-groups-and-their-caps), [Failures: patterns, cases and states](#failures-patterns-cases-and-states)
- draw, failure pattern, failure case, failure state: [Failures: patterns, cases and states](#failures-patterns-cases-and-states)
- probe, certificate: [Maximum supported demand](#maximum-supported-demand)

Words the pages use in passing:

- **Native:** computed by, or handed directly to, the engine, NetGraph-Core: a native result, model or program. The native range is the engine's numeric limit: each amount in units, and the graph's capacity and cost sums, below 2^62 ([Precision and the choice of q](#precision-and-the-choice-of-q)).
- **Eligible:** usable in the case at hand: enabled and, in a failure case, not failed.
- **Directed link:** one direction of a physical link, `forward` (source to target) or `reverse`; Python `DirectedLink`.
- **Pool head, pool attachment:** a TE ingress pool's private head node, and its private link (cost 1) to one physical source.
- **Scenario seed:** the top-level `seed`, from which step and policy seeds are derived ([Seeds](reference/dsl.md#seeds)).
