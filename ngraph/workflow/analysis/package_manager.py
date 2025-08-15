"""Environment setup for notebook analysis components.

This module configures plotting and table-display libraries used by notebook
analysis. It does not install packages dynamically. All required dependencies
must be declared in ``pyproject.toml`` and available at runtime.
"""

from __future__ import annotations

from typing import Any

import itables.options as itables_opt
import matplotlib.pyplot as plt


class PackageManager:
    """Configure plotting and table-display packages for notebooks.

    The class validates that required packages are importable and applies common
    styling defaults for plots and data tables.
    """

    REQUIRED_PACKAGES = {
        "itables": "itables",
        "matplotlib": "matplotlib",
        "seaborn": "seaborn",
        "pandas": "pandas",
        "numpy": "numpy",
    }

    @classmethod
    def check_packages(cls) -> dict[str, Any]:
        """Return availability status of required packages.

        Returns:
            A dictionary with keys:
                - ``missing_packages``: list of missing import names.
                - ``message``: short status message.
        """
        import importlib

        missing: list[str] = []
        for pkg in cls.REQUIRED_PACKAGES:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)

        return {
            "missing_packages": missing,
            "message": (
                "All required packages are available"
                if not missing
                else f"Missing packages: {', '.join(missing)}"
            ),
        }

    @classmethod
    def setup_environment(cls) -> dict[str, Any]:
        """Configure plotting and table libraries if present.

        Returns:
            A dictionary with keys:
                - ``status``: ``"success"`` or ``"error"``.
                - ``message``: short message.
                - ``missing_packages``: list of missing import names.
        """
        check = cls.check_packages()
        if check["missing_packages"]:
            return {
                **check,
                "status": "error",
                "message": check["message"],
            }
        try:
            plt.style.use("seaborn-v0_8")
            import seaborn as sns

            # Consistent, high-quality defaults across all analyses
            sns.set_theme(
                style="whitegrid", context="notebook", palette="deep", font_scale=1.0
            )

            # Global matplotlib tuning for clearer figures
            plt.rcParams.update(
                {
                    # High-DPI inline and export
                    "figure.dpi": 300,
                    "savefig.dpi": 300,
                    # Default physical size for all figures (inches)
                    "figure.figsize": (8.0, 5.0),
                    # Use tight bounding box on export to avoid extra padding
                    "savefig.bbox": "tight",
                    # Layout and grid tuning
                    "figure.autolayout": False,
                    # Constrained layout and colorbar compatibility:
                    # Disable constrained layout globally to avoid colorbar engine issues;
                    # analyses should rely on tight layout or explicit fig sizes.
                    "figure.constrained_layout.use": False,
                    "axes.grid": True,
                    "grid.linestyle": ":",
                    "grid.linewidth": 0.5,
                    # Typography: make titles less dominant and readable
                    "axes.titlesize": "medium",
                    "axes.labelsize": "medium",
                    "xtick.labelsize": "small",
                    "ytick.labelsize": "small",
                }
            )

            itables_opt.lengthMenu = [10, 25, 50, 100, 500, -1]
            itables_opt.maxBytes = 10**7
            itables_opt.maxColumns = 200
            itables_opt.showIndex = True

            import warnings

            warnings.filterwarnings("ignore")

            return {
                **check,
                "status": "success",
                "message": "Environment setup complete",
            }
        except Exception as e:  # pragma: no cover - defensive guard in notebooks
            return {
                **check,
                "status": "error",
                "message": f"Environment setup failed: {e}",
            }
