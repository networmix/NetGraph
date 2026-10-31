# NetGraph 0.24.1 against 0.26.0: speed and memory

This directory records a measured comparison of NetGraph 0.24.1 on NetGraph-Core 0.11.0 (before the 0.25 rebuild) with NetGraph 0.26.0 on Core 0.12.0, made in October 2026. It is internal documentation for maintainers, excluded from the site. It says how the two releases were made to compute the same thing, what was measured, where 0.26.0 spends its time and memory on the large data-centre workload, which changes could remove it, and how to rerun the DC-BB timings and diagnostic controls. No change to 0.26 is part of it.

The 0.26.0 changelog's "15 to 30 times faster" compares 0.26.0 with 0.25.0. Against 0.24.1, 0.26.0 is slower on the large workload below.

**Terms.** A placement step places demand groups once per failure case. For each group and case, 0.26 builds a native *forwarding program*: the routes and split plans its traffic follows. A `combine` group pools several sources; 0.25 and later give each source an equal share and its own route, held as a *source DAG* (a predecessor graph from that source to the destinations), plus a *pooled plan* for the group. *Source-edge attribution* splits the group's admitted traffic back into per-source edge flows. 0.24.1 instead placed each group through one aggregate *fanout* DAG from a virtual source. The whole-unit quantum `q` is explained in [static-q](../static-q/README.md), and source rosters and equal shares in [How NetGraph computes](../../concepts.md).

## Summary

- **DC-BB, a 3833-node, 45 856-link data-centre and backbone scenario:** 0.26.0 takes 6.6 times as long as 0.24.1 to prepare, run and export with 8 workers, and 12.1 times as long on a 192-pod variant with one worker. Its peak memory rises from about 0.5 GiB to about 22 GiB, and the machine swaps heavily.
- **Project timing controls:** only the Clos 16×4 and single-router scenarios of a 2025 study were timed, at seed 11, with 999 failure draws plus a baseline. In whole-process time against 0.24.1, 0.26.0 is about 30 % faster with 7 workers and 10 to 30 % slower with one, using each release's traffic-engineering routing. With shared ECMP routing it is 1.56 to 1.67 times slower on Clos and 1.28 times slower on the single router with one worker; the single-router result with 7 workers is inconclusive. Against the pure-Python 0.9.1 the study ran on, 0.26.0 is 4.5 to 28.6 times faster across these rows.
- **Memory and cleanup:** 0.26.0 keeps the complete forwarding program of every completed failure case until the run's result is released, with one source DAG per `combine` source and case.
- **Compute:** a rough proxy, discarding those programs early, attributes only about 8 % (D1) and 3.5 % (D2) of 0.26.0's time to paging and retention; the exact page-stall time is unmeasured. Of the rest, two parts dominate: building a separate route and plan for every source, and attributing pooled traffic back to per-source edge records.
- **The ranked candidates:** keep compact results instead of programs; stop building disposable per-source plans; skip source-edge attribution when nothing asks for it. Their savings overlap.
- **The 0.24.1 reference:** NetGraph 0.24.1 on corrected Core 0.11.0 is the reference for the qualified ECMP workloads below. D1 and D2 keep their rounding-attributable qualification against 0.26.0 and run within 3 % of released 0.24.1's time and memory on the recorded machine. A change to 0.26 is timed against it.

## The workloads

**DC-BB** is NetLab's generated data-centre and backbone scenario (`netlab.autoresearch.scenario_generator`, seed 42; NetLab 0.5.0 and 0.6.0 generate the same network). Its workflow is one maximum-supported-demand (MSD) step and 18 `TrafficMatrixPlacement` steps of 200 failure draws each, with `SHORTEST_PATHS_ECMP` routing and no flow details, edge arrays or cost distributions in the results.

| Row | Geometry | Workers | Inputs here (0.24.1 / 0.26.0 keywords) |
| --- | --- | --- | --- |
| D1 | default, 96 pods: 3833 nodes, 45 856 links | 8 | `inputs/dcbb96-0.24.1.yml.gz`, `inputs/dcbb96-0.26.0.yml.gz` |
| D2 | 192 pods (`abc1_pods_per_building=192`): 4697 nodes, 74 272 links | 1 | `inputs/dcbb192-0.24.1.yml.gz`, `inputs/dcbb192-0.26.0.yml.gz` |

Six steps (`tm_bb_avail_2pct`, `tm_bb_avail_5pct`, `tm_bb_avail_10pct`, `tm_dcbb_avail`, `tm_xsite_avail`, `tm_combined`) draw random availability failures, and the two releases draw them differently from the same seed. In every input here those six steps instead choose among 200 named risk groups per step (`replay_<step>/<draw>`), one per failure set that 0.24.1 drew for that step. Both releases therefore fail the same links with the same multiplicities. This is a resampled empirical failure law, not the stock one. Each pair of files differs only in each release's YAML keywords, and the 0.26.0 files declare `units: {resolution: 2^-18}` (`3.814697265625e-06`), a quantum that holds every DC-BB input exactly. The inputs request their row's workers.

**The project scenarios** are 20 saved networks from a 2025 study: Clos 16×4, a custom Dragonfly, Dragonfly A3H2G7 and a single router, each on seeds 11, 21, 33, 51 and 77. They use 999 common failure draws plus a baseline on 0.9.1, 0.24.1 and 0.26.0, with q = 2^-32 on 0.26.0. Before comparison, A3H2G7 link capacities were rounded to that grid on all three stacks, by at most 1.2e-10 per link. Traffic-engineering routing differs by release: `TE_WCMP_UNLIM` on 0.9.1 and 0.24.1, `TE_MAXFLOW_UNLIM` on 0.26.0, where WCMP no longer exists. The shared `SHORTEST_PATHS_ECMP` control covers only Clos and single-router seed 11 at 1 and 7 workers. The study's networks are not public, so the project rows are historical results here; they cannot be rerun from this directory.

## How the computations were made the same

Before any timing, each pair was checked by tools that were themselves tested against deliberately wrong results.

- **DC-BB:** loaded networks, ordered demands and endpoints, every failure draw and multiplicity, and MSD probe histories match. Results are compared by failure pattern. Exact equality alone earns certification. Otherwise a predeclared diagnostic labels the row *rounding-attributable* when the largest group-delivery difference at q = 2^-18 is below one unit of bandwidth and the difference at q = 2^-26 is at most one sixteenth as large. This diagnostic is not an exact-equality certificate or a general error theorem.
- **Project:** the common rounded inputs, demands, masks, MSD alpha and baseline results were checked. Six of the 20 traffic-engineering scenarios have a 0.9.1 baseline delivery differing by one binary64 step; those are rounding diagnostics, not exact passes. For the seed-11 ECMP controls, every per-demand delivery and reported cost bin was checked. Certification requires exact equality. The alternative diagnostic requires a difference below one unit at q = 2^-24 and at least sixteenfold shrink at q = 2^-32; 0.9.1 against 0.24.1 uses a relative limit of 1e-12. Traffic-engineering comparisons remain comparisons of different routing rules.

| Row | Largest group-delivery difference (quanta stated per row) | Label |
| --- | --- | --- |
| D1 | q = 2^-18 → 2^-26: 0.0686 → 0.000268 (on a delivery of 384 000), 256.03 times smaller | rounding-attributable |
| D2 | q = 2^-18 → 2^-26: 0.1367 → 0.000534, 256.0003 times smaller | rounding-attributable |
| Project, ECMP, single router, seed 11, 1 and 7 workers | none | certified equal |
| Project, ECMP, Clos, seed 11, 1 and 7 workers | 2.4e-9 at q = 2^-32, scaling with q | rounding-attributable |

The shrink of 256 is the ratio of the two quanta, as rounding predicts. The traffic-engineering rows differ by design: on Clos seed 11, 0.24.1 and 0.26.0 disagree in 12 of 999 failure cases, by 900 to 1500 out of about 430 000, because the two routings split flow differently over equal-cost paths.

The cross-release comparison tools are not in this directory: a change to 0.26 is judged against released 0.26.0 instead ("Judging a fix" below), and 0.26.0 itself is qualified against 0.24.1 above.

## Measurements

The machine was a Mac16,6 (Apple M4 Max, 36 GB) on macOS 27.0.1, on AC power, with CPython 3.13.13. Both releases were the PyPI wheels, with numpy 2.5.4, PyYAML 6.0.3, NetworkX 3.7 and jsonschema 4.26.0. Each workload used one outer job. The DC-BB campaign began with 6481 MB of swap in use and the project campaign with 8115 MB; these were not measurements on an empty machine. Swap-out and swap-in are system-wide counters and include background activity. Saved process inspections showed no overlapping heavy job. The timing ratios describe this recorded machine and memory state.

Each speed ratio comes from fresh-process A/B/A triples (3 for DC-BB rows, 5 for project rows): the new time over the mean of the two reference runs, with a bootstrap 95 % interval over whole triples. A row is called faster or slower only when its interval lies wholly beyond a 3 % margin and its reference runs drift by at most 3 %. Representative workload A/A runs drifted at most 1.0 %. The short null-clock and null-sampler controls were inconclusive, with drift up to 12.4 %; the workload controls, rather than those short controls, supported the unchanged 3 % workload drift limit.

**DC-BB** (0.24.1 against 0.26.0; "prepare + run + export" excludes YAML loading and cleanup):

| Row | Boundary | 0.24.1 | 0.26.0 | Ratio [95 %] | Peak memory |
| --- | --- | --- | --- | --- | --- |
| D1 | prepare + run + export | 5.49 s | 36.23 s | 6.59 [6.58, 6.65] | 0.49 → 22.71 GiB |
| D1 | whole process | 31.5 s | 83.1 s | descriptive | |
| D2 | prepare + run + export | 37.66 s | 454.04 s | 12.09 [12.03, 12.21] | 0.42 → 21.95 GiB |
| D2 | whole process | 75.9 s | 554.7 s | descriptive | |

During 0.26.0's D1 runs, system-wide counters recorded 18 to 21 GB swapped out and 5 to 6.5 GB swapped in per run; during D2, 68 GB out and 28 to 30 GB in. The same counters stayed under 1.1 GB either way during 0.24.1's runs. YAML loading of the 6 MB D1 input takes 25.4 s on 0.24.1 and 31.6 s on 0.26.0; the stock input without the replay risk groups loads in 6.5 and 8.2 s.

**The project timing controls** (seed 11, whole process):

| Row | 0.24.1 → 0.26.0 | 0.9.1 → 0.26.0 |
| --- | --- | --- |
| Clos, TE, 7 workers | 3.40 → 2.35 s, 0.70, faster | 26.03 → 2.35 s, 0.090 |
| Clos, TE, 1 worker | 5.95 → 7.67 s, 1.29, slower | 129.1 → 7.71 s, 0.060 |
| Clos, ECMP, 7 workers | 1.16 → 1.81 s, 1.56, slower | 13.53 → 1.82 s, 0.134 |
| Clos, ECMP, 1 worker | 1.18 → 1.96 s, 1.67, slower | 56.0 → 1.96 s, 0.035 |
| Single router, TE, 7 workers | 1.44 → 1.03 s, 0.71, faster | 5.12 → 1.04 s, 0.203 |
| Single router, TE, 1 worker | 0.90 → 0.99 s, 1.10, slower | 7.24 → 0.99 s, 0.136 |
| Single router, ECMP, 7 workers | 0.73 → 1.09 s, inconclusive (reference drift 5.3 %) | 4.88 → 1.09 s, 0.223 |
| Single router, ECMP, 1 worker | 0.57 → 0.72 s, 1.28, slower | 4.37 → 0.72 s, 0.166 |

Import plus a one-node run takes 0.376 s on 0.9.1, 0.147 s on 0.24.1 and 0.112 s on 0.26.0. In the Clos TE run phase, going from 1 to 7 workers speeds 0.26.0 up 4.5 times and 0.24.1 1.9 times.

## Where 0.26.0 spends its memory

0.26.0 keeps, for every completed failure case, the `PlacementResult` of each demand group, and each result owns its forwarding program. In these DC-BB cases, the forward `combine` group's program holds P source DAGs, one per source, and the reverse group's program holds one. The case therefore retains P + 1 source DAGs across its two results and two programs. Each DAG stores five arrays costing `12e + 8v + 4` bytes for e edges and v nodes, before object overhead and allocator rounding. On D1 and D2 a source DAG averages about 17 650 edges and 2956 nodes, about 235 KB of payload.

| Quantity | D1 | D2 |
| --- | --- | --- |
| Evaluated placement cases (after failure-pattern deduplication) | 2460 | 2460 |
| Source DAGs | 238 620 (2460 × 97) | 474 780 (2460 × 193) |
| DAG payload; with allocator rounding | 52.3 GiB; 60.24 GiB | 104.1 GiB; 119.90 GiB |
| Pooled plans, in addition | 2.90 GiB | 4.47 GiB |
| Peak resident memory | 22.7 GiB | 22.0 GiB |

These are allocations accumulated over the run. The resident peak is what remains under memory compression and swapping. The size model matches the released heap within 1.1 % at 12, 48, 96 and 192 pods, and grows almost linearly with P and with the number of evaluated cases. Workers are threads of one process, so case storage is shared: eight workers keep the same case storage as one.

Discarding each completed result's program as soon as its case is placed (the `--discard` counterfactual below) leaves both full default exports identical in every field. The peak falls to 2.54 GiB (D1) and 1.64 GiB (D2), and the cleanup after the run falls from 14 s (D1) and 51 to 54 s (D2) to about 0.1 s: that cleanup is the release of the retained programs.

0.24.1 keeps two aggregate fanout DAGs per active case and worker, about 383 KB each plus 30 KB of distances, and they die during the run.

## Where 0.26.0 spends its time

| Measurement | D1 | D2 |
| --- | --- | --- |
| Prepare + run + export, in the timing campaign | 36.23 s | 454.04 s |
| The same with programs discarded | 33.29 s | 438.21 s |
| Difference: a proxy for paging and retention | 2.95 s, 8.1 % | 15.82 s, 3.5 % |

The proxy is rough: freeing early also changes allocator and cache behaviour, and the machine's load differed. The exact page-stall time is unmeasured. The rest is computation:

- **Per-source route and plan preparation,** the 0.25 `combine` rule that gives each source its own equal share and route: repeating identical requests on the retained programs, which skips that preparation, removes about half of the native action cost on reduced runs at 96 and 192 pods.
- **Source-edge attribution:** after exact admission, Core forwards the admitted amount again with per-source attribution and builds every source's edge-flow record. The D1 and D2 baselines create 1 702 656 and 3 405 312 attribution entries. Over every case this costs 89.1 and 172.9 kernel work-seconds, 37 % and 40 % of clean CPU work, against 0.14 and 0.22 s for the same aggregate forwarding without attribution. These are kernel work-seconds summed over threads, not wall time.
- **Exact admission,** the whole-unit fit: 2.27 and 3.58 s, under 1 %, with at most 30 and 32 search probes.
- **Python:** on a reduced run (96 pods, 5 draws, 1 worker) 89 % of the time is native work under `_apply_matrix`; the largest Python self time is `flatten_link_attrs` (6 %).
- **Repeats:** only 43 of the 2460 placements repeat an identical mask and request, so caching exact repeats cannot help.

Per evaluated case, 0.26.0 makes one `apply_actions` call with two Replace actions; 0.24.1 makes two fanout placements.

## The code involved

The numbers are the first line of each named function or the cited range, at the tags `v0.26.0` and `v0.24.1` of this repository and `v0.12.0` and `v0.11.0` of NetGraph-Core. Read the other side with `git show v0.24.1:<path>` here, and `git show v0.12.0:<path>` in a NetGraph-Core clone.

| Mechanism | Where |
| --- | --- |
| One ledger and two policies per case | `ngraph/analysis/placement.py`: `policy_roster` (157), `_apply_matrix` (206), `_place_state` (254) |
| Results kept for every case and step | `ngraph/analysis/placement.py` `place` (435; the case loop near 491 to 515); `ngraph/scenario.py` `run` (312) |
| A route per source, then a union program | Core `src/flow_policy.cpp` `prepare_shortest_path_program` (680 to 775), which calls `creation_products` (269) for each reachable source; `src/route_kernels.cpp` `prepare_shortest_paths` (666 to 881) builds each source's full plan and DAG, and for several sources keeps little more than its support edges |
| The source DAG | Core `include/netgraph/core/route_structures.hpp` (30); creation in `src/route_kernels.cpp` (854 to 877) |
| The pooled plan | Core `src/forwarding_program.cpp` (206 to 236); `include/netgraph/core/detail/route_kernels.hpp` (111 to 154) |
| The program outlives its policy | Core `include/netgraph/core/flow_policy.hpp` `PlacementResult` (279 to 311) holds a shared `program`, assigned in `src/flow_policy.cpp` (1015, 1698); `bindings/python/apply_actions.cpp` (165 to 179) moves the native results into Python holders |
| Source-edge attribution | Core `src/flow_policy.cpp` (903 to 945); per-root arrivals and highest-averages allocation in `src/route_kernels.cpp` (1104, 1157) |
| Exact admission | Core `src/route_kernels.cpp`: `allocate` (896), `largest_fit` (993), `lossless_step` (1069) |
| 0.24.1's fanout | `ngraph/analysis/placement.py` at `v0.24.1`: `_place_cached_fanout` (630), its per-mask cache local to `place_demands` (178); Core 0.11.0 `src/flow_graph.cpp` (63 to 108) commits aggregate edge deltas |

## What a change could remove

The opportunities overlap, so their savings do not add up, and their measures differ: memory and nominal seconds for the first, a ceiling from reduced runs for the second, a kernel cost screen for the third. The order is the diagnosis's priority; the first waits on its contract (the first open question), and the other two do not depend on it.

1. **Keep compact results instead of complete programs.** This removes the retained programs whose discard drops the peak from 22.7 to 2.54 GiB on D1 (22.0 to 1.64 GiB on D2), a nominal 3 and 16 s, and almost all of the cleanup. Discarding keeps the default JSON export identical, but consumers that read native programs, replay a stale or repaired state, or ask for detailed routes or record identities need a contract first; that contract is the first open question.
2. **Stop building disposable single-source plans and copying shared route continuations.** A ceiling of about half of the native action cost on the reduced runs; its full-run share is extrapolated, not measured, so re-measure D1 before trusting it.
3. **Forward in aggregate without source-edge records when nothing asks for them.** 37 to 40 % of clean CPU work, estimated from additional kernel calls as a cost screen. The end-to-end elapsed gain is unmeasured. Aggregate edge results agree with and without attribution on every case.

None of them may change the source roster, the equal per-source shares, the routes, or any field of the default JSON export except the four recorded build/runtime identity fields named under "Judging a fix". Native-program consumers still need the contract review stated above.

## Reproducing

Run every command from the repository root, and all the blocks in this section in one shell session: later blocks reuse `$D` and `$EXT`. The environments and outputs land there. `measure.py` refuses a results path that already exists, so give each run a fresh name. It prints each phase, the "prepare + run + export" sum, the peak resident memory and the export's SHA-256. The stored inputs request their row's workers (8 for D1, 1 for D2); `--workers N` and `--draws N` override every placement step's workers and failure draws.

Make one environment per release from PyPI:

```sh
python3.13 -m venv v0241
v0241/bin/pip install ngraph==0.24.1 netgraph-core==0.11.0 numpy==2.5.4 pyyaml==6.0.3 networkx==3.7 jsonschema==4.26.0
python3.13 -m venv v0260
v0260/bin/pip install ngraph==0.26.0 netgraph-core==0.12.0 numpy==2.5.4 pyyaml==6.0.3 networkx==3.7 jsonschema==4.26.0
```

Run D1 on each (D2 likewise with the `dcbb192` inputs; 0.26.0's D1 swaps heavily on a 36 GB machine, and D2 takes about 9 minutes):

```sh
D=docs/design/perf-0.24-vs-0.26
v0241/bin/python -I $D/measure.py $D/inputs/dcbb96-0.24.1.yml.gz d1-0241.json
v0260/bin/python -I $D/measure.py $D/inputs/dcbb96-0.26.0.yml.gz d1-0260.json
```

`measure.py` does not report whole-process time or swapping: wrap a run in `/usr/bin/time -l` (macOS) or `/usr/bin/time -v` (Linux), and read `vm_stat` (or `/proc/vmstat`) before and after it. One run of each is a profile, not the A/B/A protocol above. On the machine above, a recheck of these commands gave 5.4 s for prepare + run + export on 0.24.1 (whole process 29.8 s, peak 0.51 GiB); 0.26.0 was rechecked only with `--discard` (below).

**The diagnostics** need the `ngprobe` module, built against Core's v0.12.0 headers and the pybind11 release Core pins (3.1.0), with a C++20 compiler:

```sh
git clone --branch v0.12.0 https://github.com/networmix/NetGraph-Core ngcore-0.12.0
v0260/bin/pip install pybind11==3.1.0
EXT=$(v0260/bin/python -m pybind11 --extension-suffix)
c++ -std=c++20 -O2 -shared -undefined dynamic_lookup -fvisibility=hidden \
  $(v0260/bin/python -m pybind11 --includes) -I ngcore-0.12.0/include \
  $D/ngprobe.cpp -o "ngprobe$EXT"
```

On Linux, replace `-undefined dynamic_lookup` with `-fPIC`. Delete the `ngcore-0.12.0` clone afterwards. Then:

```sh
v0260/bin/python -I $D/measure.py $D/inputs/dcbb96-0.26.0.yml.gz d1-discard.json --probe "./ngprobe$EXT" --discard
v0260/bin/python -I $D/measure.py $D/inputs/dcbb96-0.26.0.yml.gz d1r-probe.json --draws 5 --workers 1 --probe "./ngprobe$EXT" --census --kernels --discard
v0260/bin/python -I $D/measure.py $D/inputs/dcbb96-0.26.0.yml.gz d1r-reuse.json --draws 5 --workers 1 --reuse
```

The first is the no-retention counterfactual: on the machine above it gave 33.2 s for prepare + run + export and a 2.59 GiB peak, with the export hash below. The second and third are reduced runs (5 draws, 1 worker; 102 evaluated cases, 204 results):

- `--census` sizes what the results own: 9894 source DAGs, 2.33 GB of DAG payload and 2.68 GB with allocator rounding (`census` uses the allocator's usable sizes).
- `--kernels` reruns admission on each positive-delivery result's retained program, checks the admitted amount and each reachable source's delivery against that result, and checks that aggregate and attributed forwarding agree with the rerun's edge allocation. It does not compare those vectors with the original result's `edge_flows` output. It uses the graph's capacities, not a captured residual ledger, and is intended for these stored DC-BB diagnostics. Attributed forwarding of the multi-source group took 3.49 s, against 0.006 s without attribution and 0.08 s of exact admission.
- `--reuse` repeats each native action list on its retained programs and fails unless every request, delivery and per-source delivery repeats. The repeat took 5.08 s against 9.55 s for the first call. That difference is the preparation ceiling of the second candidate.

The same reduced commands on D2 gave 19 686 DAGs, 7.30 s against 0.010 s, and 10.45 against 19.59 s.

## Judging a fix

A change to 0.26 that is meant to keep results must reproduce released 0.26.0's computed export fields on the same inputs and settings. The raw hashes below identify the unmodified released exports on the recorded machine (stored inputs, no worker or draw overrides), byte-identical across every run there; they include build and runtime identity and are not candidate pass/fail hashes.

| Input | SHA-256 of released 0.26.0's export |
| --- | --- |
| `dcbb96-0.26.0.yml.gz` (8 workers) | `a10d7aa8421dd826c6007c61f27645438a87b27a052f1bc0d7297086b5c6e558` |
| `dcbb192-0.26.0.yml.gz` (1 worker) | `355f585a2ee5fddcf48635de75e5fe6a988b2eadef79a552e548cf467a098467` |

Install the fix before judging it: `v0260` holds the released wheel, so rerunning it judges the release again. Make a third environment `vfix` with the same pins, then replace the package under test: for a NetGraph change, `vfix/bin/pip install --no-deps -e .` from this checkout; for a Core change, build that checkout's wheel by its own instructions and `vfix/bin/pip install --no-deps --force-reinstall <wheel>`.

Run released 0.26.0 once on the target platform and pass that export to `--expect` (for example `vfix/bin/python -I $D/measure.py $D/inputs/dcbb96-0.26.0.yml.gz d1-fix.json --expect d1-0260.json`, and likewise for D2). The comparison records both exports' `netgraph_version`, `core_version`, `core_extension_sha256` and `python_version`, excludes exactly those four identity fields, and requires every other field to match. In particular, schema version, seed, the units report and every step and failure case remain exact. Then compare the same phase boundary on a recorded machine state, with the protocol above for a speed claim. A change that alters computed results needs its own qualification.

## The 0.24.1 reference

NetGraph 0.24.1, unchanged, on NetGraph-Core branch `ref/0.11.0-zerocap` (commit `d9b5595`, version `0.11.0+zerocap`, not released) is the performance reference for the qualified ECMP workloads below, subject to each row's rounding qualification. Released 0.24.1 cannot serve alone, because Core 0.11.0 departs from the ECMP rule in three ways; the branch adds two commits on the tag `v0.11.0` that correct them:

- **A zero-capacity route edge stays in the equal split.** It takes its equal share and carries nothing: lossless placement then admits nothing, and lossy placement drops that share on that edge. 0.11.0 left such edges out of the split, so it reported delivery that never arrived when an ECMP branch reached a node whose onward edges all had capacity 0, and with one zero edge among several it moved that edge's share to the others.
- **A lossy `FlowPolicy` call sends its whole volume afresh.** 0.11.0 capped the offer by the source's capacity and subtracted earlier deliveries. In 0.24.1 this reaches lossy demands pinned to static paths: a demand of 20 over two pinned paths of capacity 1 and 10 delivered 6.5; the reference delivers 11 and drops 9, as the same demand without static paths already did and as Core 0.12.0 does.
- **Equally near destinations all stay in the route.** NetGraph joins a destination set to a pseudo sink by cost-0 links. 0.11.0's multipath search kept only the destination with the widest path, which narrowed lossy `combine`, max-flow and sensitivity towards a set; the branch keeps every tied parent of a node with no usable onward edge, so the set is reached as anycast ECMP.

On a small network of three pods, each with an uplink of capacity 10 to each of two planes `pl1` and `pl2`, each plane linked to the destination `xyz1` with capacity 24, all costs 1, and one `combine` demand of 90 from the pods:

| Case | 0.24.1 lossless | Reference lossless | Reference lossy (offer) |
| --- | --- | --- | --- |
| Healthy | 48 | 48 | 48 (49) |
| `pl2` → `xyz1` at 0 | 48 | 0 | 24 (48) |
| pod 3's uplinks at 0 | 60 | 0 | 40 (60) |
| only pod 1 sends; `pl2` → `xyz1` at 0 | 20 | 0 | 10 (20) |
| pod 1 → `pl2` at 0 | 30 | 0 | 25 (30) |

In the failure cases the lossy drops fall on the zero edges. 0.26.0 delivers the same lossy amounts; its lossless deliveries in the four failure cases are 3q, 2q, q and 3q, whole-unit effects that vanish as q shrinks. With two equally near destinations behind links of 10 and 8 and a `combine` offer of 40, the reference delivers 16 lossless and 18 lossy, as 0.26.0 does (lossless to within one quantum); 0.24.1 delivered 10 lossy, all over the link of 10.

**What it was checked against.** On D1 and D2 the reference's computed records (the MSD result and probe history, and every step's results by failure pattern and multiplicity) equal unmodified 0.24.1's in every step. Both rows therefore keep their "rounding-attributable" qualification against 0.26.0 above. Core's C++ and Python suites and NetGraph 0.24.1's suite pass on the reference build, and Core's CI passes on every platform it tests (Linux, macOS and Windows; Python 3.11 to 3.14).

**Speed and memory.** The reference was timed on the machine above, with the same pins and Python 3.13.13, against two builds of unmodified Core 0.11.0: a local build of `v0.11.0` and the PyPI wheel. The reference and the local `v0.11.0` build came from clean exports of their commits with one toolchain (Apple clang 21.0.0, scikit-build-core 1.1.1, CMake 4.4.4, ninja 1.13.2, pybind11 3.1.0, `MACOSX_DEPLOYMENT_TARGET=15.0`). The protocol is the A/B/A one above with the comparator as A and the reference as B: each ratio is the reference's time over the mean of the comparator's two runs, so a ratio below 1 means the reference is faster, and "within margin" means the interval lies wholly within 3 % of 1. The machine was on AC power with sampled one-minute load averages of 1.9 to 3.6, 3.27 GB of swap in use throughout and a Spotlight indexer busy, with no other heavy job; comparator runs drifted at most 1.1 % (prepare + run + export) and 1.7 % (whole process).

| Row | Comparator | Triples | Prepare + run + export: ratio [95 %] | Whole process: ratio [95 %] | Peak memory, comparator → reference |
| --- | --- | --- | --- | --- | --- |
| D1 | local `v0.11.0` build | 7 | 0.988 [0.986, 0.991], within margin | 0.995 [0.994, 0.999], within margin | 0.484 → 0.482 GiB |
| D1 | PyPI 0.11.0 wheel | 3 | 1.006 [1.003, 1.011], within margin | 1.001 [0.988, 1.009], within margin | 0.476 → 0.471 GiB |
| D2 | local `v0.11.0` build | 7 | 0.951 [0.951, 0.953], faster | 0.978 [0.974, 0.981], within margin | 0.417 → 0.416 GiB |
| D2 | PyPI 0.11.0 wheel | 3 | 1.007 [1.004, 1.027], within margin | 1.002 [1.000, 1.016], within margin | 0.419 → 0.424 GiB |

Peak memory is the mean over each side's runs; every reference mean is within 3 % of its comparator's. Against the released wheel, the reference is within the 3 % margin on both rows. The D2 "faster" against the local build is a build effect, not the corrections: the local build of the same `v0.11.0` source ran D2 about 5 % slower than the PyPI wheel. Builds of different source therefore cannot be told apart below about 5 % on D2. In absolute terms the reference took 5.51 to 5.63 s on D1 (whole process 31.2 to 31.4 s, peak 0.476 to 0.489 GiB) and 38.19 to 38.64 s on D2 (76.3 to 77.0 s, 0.413 to 0.419 GiB); the 0.24.1 rows in "Measurements" were taken in another machine state.

**Building and using it.** These macOS commands use the recorded Xcode toolchain and deployment target. Start from a fresh clone so no previous CMake cache is reused. Other platforms need their own recorded toolchain and a fresh local comparison. In the shell session of "Reproducing", make an environment with that section's pins, build the branch's Core wheel and install it over the released one:

```sh
git clone --branch ref/0.11.0-zerocap https://github.com/networmix/NetGraph-Core ngcore-ref
git -C ngcore-ref switch --detach d9b5595a16006e3d2be9c1efde42cbca9ab28c05
python3.13 -m venv vref
vref/bin/pip install ngraph==0.24.1 netgraph-core==0.11.0 numpy==2.5.4 pyyaml==6.0.3 networkx==3.7 jsonschema==4.26.0
vref/bin/pip install scikit-build-core==1.1.1 pybind11==3.1.0 cmake==4.4.4 ninja==1.13.2
CC="$(xcrun --find clang)" CXX="$(xcrun --find clang++)" MACOSX_DEPLOYMENT_TARGET=15.0 vref/bin/pip wheel --no-deps --no-build-isolation -w ngcore-ref/dist ./ngcore-ref
vref/bin/pip install --no-deps --force-reinstall ngcore-ref/dist/netgraph_core-0.11.0+zerocap-*.whl
vref/bin/python -I $D/measure.py $D/inputs/dcbb96-0.24.1.yml.gz d1-ref.json
```

`measure.py` prints `netgraph_core` as `0.11.0+zerocap` when the reference is installed; run D2 likewise with the `dcbb192` input. To time a change to 0.26, install it as in "Judging a fix" and run it against the reference build in A/B/A triples on the same machine, under the protocol above, with the reference built on that machine. The ratios against PyPI 0.24.1 in "Measurements" stay as historical records; a change's ratio is measured afresh against the reference.

**Scope and limitations.**

- The reference covers ECMP shortest-path placement, lossless and lossy (`SHORTEST_PATHS_ECMP`, `SHORTEST_PATHS_ECMP_LOSSY`), and the default export. Traffic engineering and WCMP are outside it: their rules changed in 0.25.
- A reference row holds for its qualified workload: its input, source roster, ordered demands, failure replay and quantum, with that row's qualification against 0.26.0. No general equality with 0.26.0 is claimed. A changed workload is requalified as in "How the computations were made the same" before its ratio is used.
- A user link of cost 0 into a node that has onward links keeps 0.11.0's rule: settle order decides which equal-cost alternatives are kept, so ECMP can narrow there. Core 0.12.0 rejects zero costs, so 0.26.0 has no answer to match.
- Lossy `FlowPolicy` placement reports aggregate delivery only, without per-link drops.
- In Core's `FlowPolicy`, an explicit `target_per_flow` with `shortest_path=true` reaches the first record only, so `rebalance_demand` can shed volume; and lossy reoptimisation (`reoptimize_flows_on_each_placement`) can leave the ledger below the returned delivery. NetGraph 0.24.1 never calls `rebalance_demand`, and none of its lossy presets reoptimises.
- Capacities below 2^-12 are below the engine's resolution: such an edge can block lossless admission as a capacity of 0 does.

## Open questions

- Whether compact retention can serve every consumer of native programs (replay, repair, detailed routes), and at what contract.
- How much of the per-source preparation can be shared without changing the source roster, the equal shares or the routes.
- The elapsed gain of aggregate forwarding with 8 workers, and the exact page-stall time; neither was measured.
- The single-router ECMP row with 7 workers stayed inconclusive.
