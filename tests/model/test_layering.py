"""Tests for model/DSL package layering.

The runtime selector engine lives in ``ngraph.model.selectors`` so that the
model layer (failure policies in particular) evaluates selectors without
importing the DSL package. ``ngraph.dsl.selectors`` keeps YAML-facing parsing
and re-exports the moved names for backward compatibility.

The subprocess tests stub parent packages with path-only modules so that
importing a model module does not execute ``ngraph/__init__.py`` (which pulls
in the analysis layer, a legitimate DSL consumer).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import ngraph

_NGRAPH_DIR = Path(ngraph.__file__).resolve().parent


def _run_python(code: str) -> None:
    """Run a Python snippet in a fresh interpreter and require success."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_failure_policy_import_does_not_load_dsl() -> None:
    """Importing the failure policy module must not load any ngraph.dsl module."""
    code = textwrap.dedent(
        f"""
        import sys
        import types

        # Path-only stubs skip package __init__ side effects of parents.
        for name, path in [
            ("ngraph", {str(_NGRAPH_DIR)!r}),
            ("ngraph.model", {str(_NGRAPH_DIR / "model")!r}),
            ("ngraph.model.failure", {str(_NGRAPH_DIR / "model" / "failure")!r}),
        ]:
            mod = types.ModuleType(name)
            mod.__path__ = [path]
            sys.modules[name] = mod

        import ngraph.model.failure.policy  # noqa: F401

        dsl_modules = sorted(m for m in sys.modules if m.startswith("ngraph.dsl"))
        assert not dsl_modules, f"policy import pulled in DSL modules: {{dsl_modules}}"
        """
    )
    _run_python(code)


def test_model_packages_do_not_load_dsl_selectors() -> None:
    """Importing the model packages must not load ngraph.dsl.selectors modules.

    The only accepted residual model -> dsl dependency is the dependency-free
    string expansion helpers in ``ngraph.dsl.expansion``.
    """
    code = textwrap.dedent(
        f"""
        import sys
        import types

        stub = types.ModuleType("ngraph")
        stub.__path__ = [{str(_NGRAPH_DIR)!r}]
        sys.modules["ngraph"] = stub

        import ngraph.model  # noqa: F401
        import ngraph.model.failure  # noqa: F401
        import ngraph.model.failure.parser  # noqa: F401
        import ngraph.model.selectors  # noqa: F401

        unexpected = sorted(
            m
            for m in sys.modules
            if m.startswith("ngraph.dsl")
            and m != "ngraph.dsl"
            and not m.startswith("ngraph.dsl.expansion")
        )
        assert not unexpected, f"model packages imported DSL modules: {{unexpected}}"
        """
    )
    _run_python(code)


def test_dsl_selectors_reexports_model_selector_names() -> None:
    """ngraph.dsl.selectors re-exports the moved names for backward compatibility."""
    import ngraph.dsl.selectors as dsl_selectors
    import ngraph.model.selectors as model_selectors

    for name in model_selectors.__all__:
        assert getattr(dsl_selectors, name) is getattr(model_selectors, name), (
            f"ngraph.dsl.selectors.{name} is not the ngraph.model.selectors object"
        )

    # Parsing entry points remain in the DSL layer.
    assert callable(dsl_selectors.normalize_selector)
    assert callable(dsl_selectors.parse_match_spec)
