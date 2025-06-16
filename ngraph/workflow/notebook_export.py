from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import nbformat

from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step
from ngraph.workflow.notebook_serializer import NotebookCodeSerializer

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class NotebookExport(WorkflowStep):
    """Export scenario results to a Jupyter notebook with external JSON data file.

    Creates a Jupyter notebook containing analysis code and visualizations,
    with results data stored in a separate JSON file. This separation improves
    performance and maintainability for large datasets.

    YAML Configuration:
        ```yaml
        workflow:
          - step_type: NotebookExport
            name: "export_analysis"              # Optional: Custom name for this step
            notebook_path: "analysis.ipynb"      # Optional: Notebook output path (default: "results.ipynb")
            json_path: "results.json"            # Optional: JSON data output path (default: "results.json")
            output_path: "analysis.ipynb"        # Optional: Backward compatibility alias for notebook_path
            include_visualizations: true         # Optional: Include plots (default: true)
            include_data_tables: true            # Optional: Include data tables (default: true)
            max_data_preview_rows: 100           # Optional: Max rows in data previews
            allow_empty_results: false           # Optional: Allow notebook creation with no results
        ```

    Attributes:
        notebook_path: Destination notebook file path (default: "results.ipynb").
        json_path: Destination JSON data file path (default: "results.json").
        output_path: Backward compatibility alias for notebook_path (default: "results.ipynb").
        include_visualizations: Whether to include visualization cells (default: True).
        include_data_tables: Whether to include data table displays (default: True).
        max_data_preview_rows: Maximum number of rows to show in data previews (default: 100).
        allow_empty_results: Whether to create a notebook when no results exist (default: False).
                           If False, raises ValueError when results are empty.
    """

    notebook_path: str = "results.ipynb"
    json_path: str = "results.json"
    output_path: str = "results.ipynb"  # Backward compatibility
    include_visualizations: bool = True
    include_data_tables: bool = True
    max_data_preview_rows: int = 100
    allow_empty_results: bool = False

    def __post_init__(self) -> None:
        """Ensure backward compatibility between output_path and notebook_path."""
        # If output_path was set but not notebook_path, use output_path
        if (
            self.output_path != "results.ipynb"
            and self.notebook_path == "results.ipynb"
        ):
            self.notebook_path = self.output_path
        # If notebook_path was set but not output_path, use notebook_path
        elif (
            self.notebook_path != "results.ipynb"
            and self.output_path == "results.ipynb"
        ):
            self.output_path = self.notebook_path

    def run(self, scenario: "Scenario") -> None:
        """Create notebook and JSON files with the current scenario results.

        Generates both a Jupyter notebook (analysis code) and a JSON file (data).
        """
        results_dict = scenario.results.to_dict()

        # Resolve output paths
        notebook_output_path = Path(self.notebook_path)
        json_output_path = Path(self.json_path)

        if not results_dict:
            if self.allow_empty_results:
                logger.warning(
                    "No analysis results found, but proceeding with empty notebook "
                    "because 'allow_empty_results=True'. This may indicate missing "
                    "analysis steps in the scenario workflow."
                )
                # Always export JSON file, even if empty, for consistency
                self._save_results_json({}, json_output_path)
                nb = self._create_empty_notebook()
            else:
                raise ValueError(
                    "No analysis results found. Cannot create notebook without data. "
                    "Either run analysis steps first, or set 'allow_empty_results: true' "
                    "to create an empty notebook."
                )
        else:
            logger.info(f"Creating notebook with {len(results_dict)} result sets")
            logger.info(
                f"Estimated data size: {self._estimate_data_size(results_dict)}"
            )

            # Save results to JSON file
            self._save_results_json(results_dict, json_output_path)

            # Create notebook that references the JSON file
            nb = self._create_data_notebook(
                results_dict, json_output_path, notebook_output_path
            )

        try:
            self._write_notebook(nb, scenario, notebook_output_path, json_output_path)
        except Exception as e:
            logger.error(f"Error writing files: {e}")
            # Create error notebook as fallback for write errors
            try:
                nb = self._create_error_notebook(str(e))
                self._write_notebook(
                    nb, scenario, notebook_output_path, json_output_path
                )
            except Exception as write_error:
                logger.error(f"Failed to write error notebook: {write_error}")
                raise

    def _write_notebook(
        self,
        nb: nbformat.NotebookNode,
        scenario: "Scenario",
        notebook_path: Path,
        json_path: Optional[Path] = None,
    ) -> None:
        """Write notebook to file and store paths in results."""
        # Ensure output directory exists
        notebook_path.parent.mkdir(parents=True, exist_ok=True)

        # Write notebook
        nbformat.write(nb, notebook_path)
        logger.info(f"📓 Notebook written to: {notebook_path}")

        if json_path:
            logger.info(f"📊 Results JSON written to: {json_path}")

        # Store paths in results
        scenario.results.put(self.name, "notebook_path", str(notebook_path))
        if json_path:
            scenario.results.put(self.name, "json_path", str(json_path))

    def _create_empty_notebook(self) -> nbformat.NotebookNode:
        """Create a minimal notebook for scenarios with no results."""
        nb = nbformat.v4.new_notebook()

        header = nbformat.v4.new_markdown_cell(
            "# NetGraph Results\n\nNo analysis results were found in this scenario."
        )

        nb.cells.append(header)
        return nb

    def _create_error_notebook(self, error_message: str) -> nbformat.NotebookNode:
        """Create a notebook documenting the error that occurred."""
        nb = nbformat.v4.new_notebook()

        header = nbformat.v4.new_markdown_cell(
            "# NetGraph Results\n\n"
            "## Error During Notebook Generation\n\n"
            f"An error occurred while generating this notebook:\n\n"
            f"```\n{error_message}\n```"
        )

        nb.cells.append(header)
        return nb

    def _create_data_notebook(
        self,
        results_dict: dict[str, dict[str, Any]],
        json_path: Path,
        notebook_path: Path,
    ) -> nbformat.NotebookNode:
        """Create notebook with content based on results structure."""
        serializer = NotebookCodeSerializer()
        nb = nbformat.v4.new_notebook()

        # Header
        header = nbformat.v4.new_markdown_cell("# NetGraph Results Analysis")
        nb.cells.append(header)

        # Setup environment
        setup_cell = serializer.create_setup_cell()
        nb.cells.append(setup_cell)

        # Load data
        data_cell = serializer.create_data_loading_cell(str(json_path))
        nb.cells.append(data_cell)

        # Add analysis sections based on available data
        if self._has_capacity_data(results_dict):
            capacity_header = nbformat.v4.new_markdown_cell(
                "## Capacity Matrix Analysis"
            )
            nb.cells.append(capacity_header)

            capacity_cell = serializer.create_capacity_analysis_cell()
            nb.cells.append(capacity_cell)

        if self._has_flow_data(results_dict):
            flow_header = nbformat.v4.new_markdown_cell("## Flow Analysis")
            nb.cells.append(flow_header)

            flow_cell = serializer.create_flow_analysis_cell()
            nb.cells.append(flow_cell)

        # Summary
        summary_header = nbformat.v4.new_markdown_cell("## Summary")
        nb.cells.append(summary_header)

        summary_cell = serializer.create_summary_cell()
        nb.cells.append(summary_cell)

        return nb

    def _save_results_json(
        self, results_dict: dict[str, dict[str, Any]], json_path: Path
    ) -> None:
        """Save results dictionary to JSON file."""
        # Ensure directory exists
        json_path.parent.mkdir(parents=True, exist_ok=True)

        json_str = json.dumps(results_dict, indent=2, default=str)
        json_path.write_text(json_str, encoding="utf-8")
        logger.info(f"Results JSON saved to: {json_path}")

    def _estimate_data_size(self, results_dict: dict[str, dict[str, Any]]) -> str:
        """Estimate the size of the results data for logging purposes."""
        json_str = json.dumps(results_dict, default=str)
        size_bytes = len(json_str.encode("utf-8"))

        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _create_robust_code_cell(
        self, code: str, context: str
    ) -> nbformat.NotebookNode:
        """Create a code cell with error handling wrapper."""
        wrapped_code = f"""try:
{code}
except Exception as e:
    print(f"Error in {context}: {{e}}")
    import traceback
    traceback.print_exc()"""
        return nbformat.v4.new_code_cell(wrapped_code)

    def _has_capacity_data(self, results_dict: dict[str, dict[str, Any]]) -> bool:
        """Check if results contain capacity matrix data."""
        for _step_name, step_data in results_dict.items():
            if isinstance(step_data, dict) and "capacity_envelopes" in step_data:
                return True
        return False

    def _has_flow_data(self, results_dict: dict[str, dict[str, Any]]) -> bool:
        """Check if results contain flow analysis data."""
        for _step_name, step_data in results_dict.items():
            if isinstance(step_data, dict):
                flow_keys = [k for k in step_data.keys() if k.startswith("max_flow:")]
                if flow_keys:
                    return True
        return False


register_workflow_step("NotebookExport")(NotebookExport)
