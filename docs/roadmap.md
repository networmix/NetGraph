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
  backbone workload, but the placement implementation has since changed.
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
