# Roadmap

This page is for maintainers. It is the product's rolling roadmap and the only place that records planned and
deferred work and its state. The user documentation describes what the product does today; nothing on this page is
available until its row says so.

## Status values

**Contract**

- `pending`: the item needs a reviewed design before work starts; the link names the current source.
- `ready`: the linked design holds a reviewed contract for the item.
- `not needed`: the Work cell states the change completely.
- `—`: delivered before this roadmap; the code and user documentation define the behaviour.

**Implementation**

- `planned`: none of the item is in the product.
- `partly implemented`: part of it is; the evidence names which part.
- `implemented`: the item is in the product.

## Maintaining the roadmap

- One row per planned item. IDs never change and are never reused; a split gets new IDs and the old one leaves the
  table. A need in another repository is written `<repository>:<ID>`.
- A row changes in the commit that changes its item: its scope, its needs, its contract or its implementation. Its
  evidence names in-repository witnesses (tests, documents, reports); a row never names the commit that changes it.
- An implemented row may leave the table once a release has shipped it and no row needs it; the repository's changelog
  or its dated history reports keep it.
- Status words live only on this page. Designs state requirements; the changelog or the dated history reports say what
  shipped.
  When this page and a design disagree on order or needs, this page wins; on behaviour, the design wins.
- The page records product facts, not how the work is run: an effort's plans, reviews and CI results stay in its own
  records.
- An item moves from Deferred to Planned on the maintainer's decision, and gets its ID then.

## Planned

Nothing is scheduled yet.

| ID | Work | Needs | Contract | Implementation | Evidence |
|---|---|---|---|---|---|

## Deferred

Not scheduled. One entry per item: what it is, and why it is not scheduled or what would make it worth doing.

- **Small-scenario loading**: profile loading on small Clos and single-router inputs and compare with the earlier
  release before optimizing; an earlier comparison found roughly 1.2 ms of extra work, but the current loader has
  changed and small inputs need a fresh user-visible cost witness.
- **Large-scenario loading**: profile and reduce loading and model building on large inputs. On the 96-pod DC-BB
  scenario of `docs/design/perf-0.24-vs-0.26/` (3,833 nodes) it takes 6.94 s of the 10.40 s default run at 8 workers
  and 7.05 s of 18.37 s at one worker (one exploratory run each, NetGraph 0.27.0 on CPython 3.14 with NetGraph-Core
  0.13.0, a 28-CPU Mac), spent in regular expressions, node selection and YAML parsing. It is the largest measured part
  of a user's run on that workload and no NetGraph-Core change can remove it; unlike the fixed cost of
  "Small-scenario loading", it grows with the scenario. A profile of the loader and a qualified command-line comparison
  decide it.
- **Offline NetGraph setup**: let `.superset/workspace.sh setup` prepare constrained dependency wheels so a worktree
  prepared once online can run its checks offline, including its required Core package; pursue this when preparing
  workers without network rather than relying on an incidental pip cache.
- **Historical 0.26 reference comparison**: directly compare unchanged NetGraph 0.26.0 with the corrected 0.24.1
  reference on both recorded data-center/backbone workloads if a decision needs that historical baseline; the later
  implementation has its own direct reference comparison, and its measurements do not replace the original release's
  historical ratios.
- **DSL skill reference drift**: synchronize the DSL skill's units explanation and tunnel-count example with the
  maintained reference pages as part of release preparation; use a manual release sync unless recurring drift
  demonstrates that an additional check is worthwhile.
- **Documented-client gate guidance**: name `tests/integration/test_documented_clients.py` in maintainer instructions
  for changes to public records and documentation, so executable Python and YAML examples are checked with those
  changes; the test already exists and the remaining work is a small instruction change.
- **Publishing trigger instructions**: document that package publication follows a published GitHub release and
  distinguish its manual Test PyPI path, matching `.github/workflows/publish.yml`; add this when maintaining release
  instructions so a maintainer does not mistake a pushed tag for publication.
- **In-domain group failure states**: support converged and repaired forwarding for `group` scope at a programmed router
  inside the IGP domain without spilling a dead group's cap, dropping unrelated transit traffic or creating a cycle; the
  current explicit refusal stays until a representation can satisfy all three constraints.
- **Automatic placement worker count**: compare representative placement and capacity workloads at several worker counts
  before changing `workers: auto`, which currently uses every CPU; earlier measurements favored fewer workers for one
  backbone workload, but the placement implementation has since changed. On NetGraph 0.27.0 one exploratory run per
  count gave: the 96-pod DC-BB placement 18.37 s at 1 worker and 10.40 s at 8; `scenarios/backbone_clos.yml` 0.42 /
  0.34 / 0.34 s at 1 / 8 / 28, the last being `auto` on a 28-CPU Mac. Qualified comparisons at several counts are
  still needed before choosing a default.
- **Runtime errors identify their step**: attach the workflow step's name to exceptions raised while it runs, preserving
  the original exception type and cause; construction errors already carry locations, and this becomes worthwhile when
  several runtime steps of the same type cannot otherwise be distinguished.
- **Schema presence with impossible values**: make the results-schema presence checker refuse unsupported
  impossible-valued properties or account for their feasibility before deciding a field can be absent; the current
  schema does not need this form, so implement the smallest separating check when such a definition is introduced.
- **Private loader provenance**: remove loader-only `yaml_label`, `declaration_ordinal`, `expand_leaf_index`,
  `derived_seed`, `_membership_raw` and `CapacityQuery.declaration` from public constructor signatures while preserving
  identity through `dataclasses.replace` and binding to prepared capacity-query pools; this spans model and workflow
  construction and should wait for a concrete API simplification need.
- **Small-scenario execution overhead**: profile fixed topology compilation, construction and export costs on
  representative small combine workloads before optimizing them; retained profiles identify these boundaries, but
  historical study slowdowns and old setup timings have not been re-established on the current release.
- **Inspect effective MaxFlow model**: make `ngraph inspect --detail` show the effective `TE_MAXFLOW_UNLIM` model when a
  MaxFlow step omits both `preset` and `model`; it currently shows the raw `None` fields, and this fits a small CLI
  usability change.
- **Inspect parallel link IDs**: include each link's ID in the detailed inspection table so parallel links with
  identical endpoints and attributes can be distinguished; defer until the next CLI usability pass.
- **Bundled NSFNET output size**: assess the output a newcomer gets from `scenarios/nsfnet.yaml` and the cost of
  validating its pairwise failure results, then choose fewer requested results or representative schema validation while
  retaining coverage of every case shape; the scenario's geography has changed, so measure its current output before
  choosing a reduction.
- **Optional WCMP weight recipes**: offer clearly named configured or advertised link-bandwidth and
  disjoint-chain-bottleneck recipes alongside controller-derived weights if a scenario needs them, without treating
  independent next-hop maximum flows as jointly deliverable capacity; the existing controller and explicit-weight inputs
  cover current uses, so no additional recipe is scheduled.
- **Explain flattened whole-unit groups**: document that flattening nested forwarding-group shares is an approximation
  to nested whole-unit splitting, with an offer of 2 giving flat `[2,0,0]` instead of nested `[1,1,0]`; the
  implementation and regression already distinguish the answers, so the remaining change is an explanation beside the
  group rules, not a native group splitter.
- **Default failure states**: decide whether placement without explicit failure states should report converged and stale
  results together instead of the current converged-only default; both phases already exist, but changing the default
  adds computation and result rows, so reconcile the intended default before changing behavior.
- **Export cost of max-flow analyses**: reduce the per-pair object building when exporting capacity analyses. On
  `scenarios/nsfnet.yaml` the export takes 1.01 s of the 1.87 s run at one worker (54 %), more than the analyses' own
  run phase (0.69 s); NetGraph builds 393,244 integers, 87,696 floats and 175,392 lists, 51 MB in all, and reads Core
  getters for 0.227 s over 1,227,789 getter events at one worker (excluding enum reads) or 0.289 s over 1,315,488
  events including 87,699 enum reads in a run at eight workers: two exploratory bases, not one cost. Distinct from
  "Bundled NSFNET output size", which is about what is requested; this is what each exported pair costs. A NetGraph
  profile decides it; a columnar result form from NetGraph-Core would need that project's contract decision first.
- **Python work under the interpreter lock**: measure whether the interpreter lock is the critical path of failure
  analysis at eight workers, and compare a free-threaded CPython 3.14t build. On the 96-pod DC-BB scenario the case
  threads' CPU outside NetGraph-Core calls, a proxy for lock-held Python work, is 1.68 s by one timer correction and
  1.83-1.92 s by another, against a 2.72 s analysis; inside its calls NetGraph-Core holds the lock for 0.19 s of CPU and
  releases it for 10.47 s, and latency added to its calls on the case threads reaches the analysis wall in full. Lock
  waiting itself was not measured. Lock waits instrumented at their boundaries and a free-threaded build compared on
  that scenario at 8 workers decide it.
- **Adapter for NetGraph-Core's baseline route-program reuse**: if NetGraph-Core adopts its opt-in reuse of a workflow
  step's baseline route programs, `ngraph/analysis/placement.py` must use it. The adapter it was measured with (+155/−5
  lines, branch `prototype/baseline-reuse-adapter`) passes `preparation=`, captures the baseline policies before they
  are removed, derives each case's hints, threads the shared preparation through the state and case functions, and
  solves each step's baseline before its failure cases unless an earlier capture is reused, a scheduling change under
  which `test_converged_only_builds_no_baseline_and_schedules_cases_alone` fails by design. It keeps per-run captures
  for the life of the process in a module-level dictionary, is switched by `NETGRAPH_REUSE_LIFETIME`, and applies only
  to ordered, converged lists of lossless equal-split shortest-path demands. A landing chooses the user-facing switch,
  the capture's owner and lifetime, accepts or redesigns the scheduling change, and checks retained memory across
  scenarios for persistent processes such as NetLab's worker pool. With that adapter the 96-pod DC-BB run was 18 %
  faster at one worker (per-step capture) and 4.6 % at eight (per-run capture).
