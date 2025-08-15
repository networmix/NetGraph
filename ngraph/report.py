"""Standalone report generation for NetGraph analysis results.

Generates Jupyter notebooks and optional HTML reports from ``results.json``.
This module is separate from workflow execution to allow independent analysis
in notebooks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import nbformat

from ngraph.logging import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """Generate notebooks and HTML reports from a results document.

    The notebook includes environment setup, results loading, overview, and
    per-step analysis sections chosen via the analysis registry.
    """

    def __init__(self, results_path: Path = Path("results.json")):
        self.results_path = results_path
        self._results: dict[str, Any] = {}
        self._workflow_metadata: dict[str, Any] = {}

    def load_results(self) -> None:
        """Load and validate the JSON results file into memory."""
        if not self.results_path.exists():
            raise FileNotFoundError(f"Results file not found: {self.results_path}")
        try:
            with open(self.results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in results file: {e}") from e
        if not data:
            raise ValueError("Results file is empty")

        self._results = data
        self._workflow_metadata = data.get("workflow", {})
        steps = data.get("steps", {})
        if not isinstance(steps, dict) or not steps:
            raise ValueError(
                "No analysis results found in file (missing or empty 'steps')"
            )
        logger.info(
            f"Loaded results with {len(self._workflow_metadata)} workflow steps"
        )

    def generate_notebook(self, output_path: Path = Path("analysis.ipynb")) -> Path:
        """Create a Jupyter notebook with analysis scaffold.

        Args:
            output_path: Target path for the notebook.

        Returns:
            The path to the written notebook file.
        """
        if not self._results:
            raise ValueError("No results loaded. Call load_results() first.")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        nb = self._create_analysis_notebook()
        with open(output_path, "w", encoding="utf-8") as f:
            nbformat.write(nb, f)
        logger.info(f"Notebook saved to: {output_path}")
        return output_path

    def generate_html_report(
        self,
        notebook_path: Path = Path("analysis.ipynb"),
        html_path: Path = Path("analysis_report.html"),
        include_code: bool = False,
    ) -> Path:
        """Render the notebook to HTML using nbconvert.

        Args:
            notebook_path: Input notebook to execute and convert.
            html_path: Output HTML file path.
            include_code: If False, hide input cells.

        Returns:
            The path to the written HTML file.
        """
        if not notebook_path.exists():
            self.generate_notebook(notebook_path)
        html_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "jupyter",
            "nbconvert",
            "--execute",
            "--to",
            "html",
            str(notebook_path),
            "--output",
            str(html_path),
        ]
        if not include_code:
            cmd.append("--no-input")

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"HTML report saved to: {html_path}")
            return html_path
        except subprocess.CalledProcessError as e:
            logger.error(f"nbconvert failed: {e.stderr}")
            raise RuntimeError(f"Failed to generate HTML report: {e.stderr}") from e

    # -------------------- notebook construction --------------------

    def _create_analysis_notebook(self) -> nbformat.NotebookNode:
        nb = nbformat.v4.new_notebook()

        # Title
        nb.cells.append(nbformat.v4.new_markdown_cell("# NetGraph Results Analysis"))

        # Setup
        nb.cells.append(self._create_setup_cell())

        # CSS for consistent inline image sizing in HTML export (retina-safe)
        nb.cells.append(self._create_css_cell())

        # Data loading
        nb.cells.append(self._create_data_loading_cell())

        # Overview
        nb.cells.append(self._create_analysis_overview_cell())

        # Per-step sections
        self._add_analysis_sections(nb)
        return nb

    def _create_setup_cell(self) -> nbformat.NotebookNode:
        code = """# Setup analysis environment
from ngraph.workflow.analysis import (
    PackageManager, DataLoader, get_default_registry,
    SummaryAnalyzer, CapacityMatrixAnalyzer, PlacementMatrixAnalyzer,
    BACAnalyzer, LatencyAnalyzer, MSDAnalyzer
)

# Prefer high-resolution inline images in executed notebooks (HTML export)
try:
    from matplotlib_inline.backend_inline import set_matplotlib_formats
    set_matplotlib_formats("retina")
except Exception:
    pass

pm = PackageManager()
_setup = pm.setup_environment()
if _setup.get('status') != 'success':
    print("⚠️ Setup warning:", _setup.get('message'))
else:
    print("✅ Environment setup complete")

# Hard guarantee final DPI/size even if other extensions alter rcParams later
import matplotlib.pyplot as plt
plt.rcParams["figure.dpi"] = 300
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["figure.figsize"] = (8.0, 5.0)
plt.rcParams["savefig.bbox"] = "tight"

registry = get_default_registry()
print(f"Analysis registry loaded with {len(registry.get_all_step_types())} step types")"""
        return nbformat.v4.new_code_cell(code)

    def _create_css_cell(self) -> nbformat.NotebookNode:
        css = """
<style>
:root {
  /* Approximate A4 content width at typical CSS pixel density */
  --figure-max-width: 820px; /* ~8.5 in at ~96 css px/in */
}
/* Constrain inline images responsively for nbconvert HTML and JupyterLab */
div.output_subarea img,
.output_png img,
.jp-OutputArea-output img {
  display: block;
  margin: 0.25rem auto;
  width: 100% !important;
  max-width: min(100%, var(--figure-max-width)) !important;
  height: auto !important;
}
/* Ensure SVGs follow the same sizing */
div.output_subarea svg,
.jp-OutputArea-output svg {
  display: block;
  margin: 0.25rem auto;
  width: 100% !important;
  max-width: min(100%, var(--figure-max-width)) !important;
  height: auto !important;
}
</style>
"""
        return nbformat.v4.new_markdown_cell(css)

    def _create_data_loading_cell(self) -> nbformat.NotebookNode:
        code = f"""# Load analysis results
loader = DataLoader()
load = loader.load_results('{self.results_path.name}')
if load['success']:
    results = load['results']
    workflow_metadata = results.get('workflow', {{}})
    steps = results.get('steps', {{}})
    print(f"✅ Loaded {{len(steps)}} analysis steps from {self.results_path.name}")
    print(f"Workflow contains {{len(workflow_metadata)}} steps")
else:
    print("❌ Load failed:", load['message'])
    results = {{}}
    workflow_metadata = {{}}
    steps = {{}}"""
        return nbformat.v4.new_code_cell(code)

    def _create_analysis_overview_cell(self) -> nbformat.NotebookNode:
        code = """# Analysis Overview
print("Analysis Plan")
print("=" * 60)

if 'workflow' in results and workflow_metadata:
    step_order = sorted(workflow_metadata.keys(), key=lambda s: workflow_metadata[s]["execution_order"])
    for i, step_name in enumerate(step_order, 1):
        meta = workflow_metadata[step_name]
        step_type = meta["step_type"]
        print(f"{i:2d}. {step_name} ({step_type})")
        for cfg in registry.get_analyses(step_type):
            print(f"    -> {cfg.analyzer_class.__name__}.{cfg.method_name}")
        if step_name not in steps:
            print("    ⚠️ No data found for this step")
        print()
    print(f"Total: {len(step_order)} workflow steps")
else:
    print("❌ No workflow metadata found")"""
        return nbformat.v4.new_code_cell(code)

    def _add_analysis_sections(self, nb: nbformat.NotebookNode) -> None:
        if not self._workflow_metadata:
            return
        from ngraph.workflow.analysis import get_default_registry

        registry = get_default_registry()

        step_order = sorted(
            self._workflow_metadata.keys(),
            key=lambda s: self._workflow_metadata[s]["execution_order"],
        )

        for step_name in step_order:
            meta = self._workflow_metadata[step_name]
            step_type = meta["step_type"]

            nb.cells.append(
                nbformat.v4.new_markdown_cell(f"## {step_name} ({step_type})")
            )

            analyses = registry.get_analyses(step_type)
            if not analyses:
                nb.cells.append(
                    nbformat.v4.new_code_cell(
                        f'print("INFO: No analysis modules configured for step type: {step_type}")'
                    )
                )
                continue

            for cfg in analyses:
                if len(analyses) > 1:
                    nb.cells.append(
                        nbformat.v4.new_markdown_cell(f"### {cfg.section_title}")
                    )
                kwargs_src = cfg.kwargs or {}
                kwargs_list = [f"step_name='{step_name}'"] + [
                    f"{k}={repr(v)}" for k, v in kwargs_src.items()
                ]
                call = f"""analyzer = {cfg.analyzer_class.__name__}()
try:
    analyzer.{cfg.method_name}(results, {", ".join(kwargs_list)})
except Exception as e:
    print(f"❌ Analysis failed: {{e}}")"""
                nb.cells.append(nbformat.v4.new_code_cell(call))
