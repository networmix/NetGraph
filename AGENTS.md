# Development

- Setup: `bash .superset/workspace.sh setup`. Each worktree gets its own venv;
  setup does not replace the Git hooks shared by worktrees.
- Superset **Run**: `bash .superset/workspace.sh check` runs lint, types, schemas,
  all tests, checks the generated API reference and builds documentation.
- After changing docstrings, run `make docs` and review the generated diff.
- For changes involving Core, run
  `bash dev/check_core_integration.sh /absolute/path/to/NetGraph-Core-worktree`.
  It tests the selected Core wheel in a separate venv; normal setup uses the
  published Core package. Results remain under `build/core-integration/`.

Confirm suspected defects with source and a reproducer. Check API wording
against implementation and bindings. Performance claims need correctness gates
and repeated A/B/A measurements on the same quiet machine. Local tests do not
replace CI; release notes should describe concise user-visible changes.
