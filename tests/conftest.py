"""Global pytest configuration.

Conditionally registers optional fixture plugin `tests.algorithms.sample_graphs`.
Avoid importing the plugin directly to let pytest apply assertion rewriting.
When running a subset of tests where that module is unavailable, pytest still
collects and runs tests in the targeted folder.
"""

from __future__ import annotations

from importlib.util import find_spec

# Register plugin if available without importing it here. Pytest will import it
# with assertion rewriting enabled, avoiding PytestAssertRewriteWarning.
pytest_plugins: list[str] = []
if find_spec("tests.algorithms.sample_graphs") is not None:
    pytest_plugins = ["tests.algorithms.sample_graphs"]
