# NetGraph Development Guide

## Essential Commands

```bash
make dev           # Create venv, install package with dev deps and hooks
make check         # Pre-commit with auto-fix, schema check, tests, then lint
make check-ci      # Non-mutating lint, schema check, and tests (CI)
make test          # Run tests with coverage
make docs          # Generate API documentation and diagram SVGs
make docs-serve    # Serve docs locally
```

`make docs` renders `docs/assets/diagrams/*.dot` with Graphviz; install it
with `brew install graphviz` (macOS) or `apt-get install graphviz` (Debian/Ubuntu).
Without it the diagram step is skipped and the committed SVGs stay as they are.

`bash dev/check_core_integration.sh /absolute/Core/worktree` normally builds a
hooks-off wheel from that source. To test an already frozen build, set
`NETGRAPH_CORE_WHEEL` to its absolute wheel path and
`NETGRAPH_CORE_WHEEL_SHA256` to its SHA256. Optional `NETGRAPH_CORE_COMMIT`,
`NETGRAPH_CORE_WRAPPER_SHA256` and `NETGRAPH_CORE_EXTENSION_SHA256` assert the
chosen source commit and installed bytes. Both imported modules must originate
inside the isolated integration venv; private hooks are refused. Evidence stays
under `build/core-integration/`.

## Publishing

**Manual**: `make clean && make build && make publish-test && make publish`

**Automated**: Create GitHub release → auto-publishes to PyPI

**Version**: Update `version = "x.y.z"` in `pyproject.toml` before publishing

## Key Development Files

```text
pyproject.toml              # Package config, dependencies, tool settings
Makefile                    # Development commands
.pre-commit-config.yaml     # Code quality hooks
dev/run-checks.sh           # Script behind make check
dev/scenario_perf.py        # Qualified scenario A/B/A and calibration driver
```

## Scenario performance comparisons

`make perf` shows the driver help. `make perf-tool-test` tests qualification,
timeout propagation, replay validation and measurement order with fake clocks;
it performs no performance measurement. Timing requires an explicit quiet
window and runs through the machine's heavy-run scheduler.

The driver consumes a JSON manifest with `schema_version: 1`, `artifacts`
(absolute file paths mapped to SHA256, including source, native extension,
dependency inventory, worker scripts and saved failure patterns), and `rows`.
Each row has a safe unique `name`, `boundary` (`product_cli` or `whole_process`),
an absolute `patterns` file, positive `timeout_seconds`, a description of the
actual `output_selection`, and `sides.old`/`sides.new`. A new question uses only
`sides.new` and an explicit `budget_seconds`.

Each side supplies an absolute executable in `argv`, absolute `cwd`, pinned
imported `origins`, `dependencies_sha256`, and its correctness-qualified
`output_sha256`. Set `stdout_json: true` to validate the full exported JSON in
the parent after process exit. `argv` includes the separate arguments `{report}` and
`{patterns}`. A task-specific worker runs one complete scenario through its
product CLI with the saved failure population and writes that report. Workers
for historical APIs belong to the experiment, outside the product package.

The worker report contains `exit_code: 0`, `iterations: 1`, positive finite
`product_cli_seconds`, and the exact `patterns_sha256`, `origins`,
`dependencies_sha256`, `output_selection`, `output_sha256`. With `stdout_json`,
the worker writes the actual product JSON to stdout and leaves `output_sha256`
null in its receipt; the parent computes and checks that digest after stopping
the process clock. This keeps result parsing, normalization and hashing out of
both measurement boundaries. The worker asserts the modules actually loaded
and the dependency digest. Its CLI boundary starts at entry to the product command and ends
after output encoding/writing; imports and interpreter startup remain in the
parent's separately recorded whole-process duration. A changed native question
gets its own qualified output digest; equality of old/new numerical results
is not assumed.

For a historical result, `output_digest_rules` may contain
`historical_step_times` (normalize only old step metadata durations) and
`historical_failure_sets` (sort only old excluded-node/link sets). These rules
preserve all numerical results and sequence order outside those sets; unknown
rules refuse. Retain raw stdout alongside the normalized digest.

```bash
python dev/scenario_perf.py validate manifest.json
# Only inside the explicitly granted window, through the heavy-run scheduler:
python dev/scenario_perf.py calibrate manifest.json --output calibration.noindex \
  --grant 'owner window reference' --deadline 2026-10-22T19:00:00+00:00
python dev/scenario_perf.py aba manifest.json --output comparison.noindex \
  --grant 'owner window reference' --deadline 2026-10-22T19:00:00+00:00
```

Calibration counts complete iterations needed for two seconds of work per
side/row. Comparisons default to three old/new/old repetitions. Every child
requires AC power and all three load averages below4 before and after, and its
entire timeout must fit the window. Logs preserve commands, PID, exit/timeout,
state and both durations; inputs are hash-checked after each completed row.
A ratio above1.03 requires a separate profile and disposition, not an automatic
pass. `--resume prior-output.noindex` reuses only completed rows with identical
frozen inputs and measurement mode; failed rows run afresh in a new directory.

## GitHub Workflows

```text
.github/workflows/
├── python-test.yml         # CI: tests, linting, type checking
├── docs.yml                # Build and deploy docs on push to main
└── publish.yml             # Publish to PyPI on release; Test PyPI on manual run
```
