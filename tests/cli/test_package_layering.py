"""Tests for package-level import layering.

The package root must not eagerly import the CLI module: the console entry
point (``ngraph.cli:main``) and ``python -m ngraph`` import it explicitly.
"""

from __future__ import annotations

import subprocess
import sys


def test_import_ngraph_does_not_import_cli() -> None:
    """Importing the package root must not pull ngraph.cli into sys.modules."""
    code = "import sys, ngraph; assert 'ngraph.cli' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_from_ngraph_import_cli_still_works() -> None:
    """``from ngraph import cli`` resolves via submodule import fallback."""
    code = "from ngraph import cli; assert callable(cli.main)"
    subprocess.run([sys.executable, "-c", code], check=True)
