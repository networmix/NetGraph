"""Code serialization for notebook generation."""

from typing import TYPE_CHECKING, Any, Dict

import nbformat

from ngraph.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class NotebookCodeSerializer:
    """Converts Python classes into notebook cells."""

    @staticmethod
    def create_setup_cell() -> nbformat.NotebookNode:
        """Create setup cell."""
        setup_code = """# Setup analysis environment
from ngraph.workflow.notebook_analysis import (
    CapacityMatrixAnalyzer,
    FlowAnalyzer,
    SummaryAnalyzer,
    PackageManager,
    DataLoader
)

# Setup packages and environment
package_manager = PackageManager()
setup_result = package_manager.setup_environment()

if setup_result['status'] != 'success':
    print("⚠️ Setup warning:", setup_result['message'])
else:
    print("✅ Environment setup complete")"""

        return nbformat.v4.new_code_cell(setup_code)

    @staticmethod
    def create_data_loading_cell(json_path: str) -> nbformat.NotebookNode:
        """Create data loading cell."""
        loading_code = f"""# Load analysis results
loader = DataLoader()
load_result = loader.load_results('{json_path}')

if load_result['success']:
    results = load_result['results']
    print(f"✅ Loaded {{len(results)}} analysis steps from {json_path}")
else:
    print("❌ Load failed:", load_result['message'])
    results = {{}}"""

        return nbformat.v4.new_code_cell(loading_code)

    @staticmethod
    def create_capacity_analysis_cell() -> nbformat.NotebookNode:
        """Create capacity analysis cell."""
        analysis_code = """# Capacity Matrix Analysis
if results:
    capacity_analyzer = CapacityMatrixAnalyzer()
    capacity_analyzer.analyze_and_display_all_steps(results)
else:
    print("❌ No results data available")"""

        return nbformat.v4.new_code_cell(analysis_code)

    @staticmethod
    def create_flow_analysis_cell() -> nbformat.NotebookNode:
        """Create flow analysis cell."""
        flow_code = """# Flow Analysis
if results:
    flow_analyzer = FlowAnalyzer()
    flow_analyzer.analyze_and_display_all(results)
else:
    print("❌ No results data available")"""

        return nbformat.v4.new_code_cell(flow_code)

    @staticmethod
    def create_summary_cell() -> nbformat.NotebookNode:
        """Create analysis summary cell."""
        summary_code = """# Analysis Summary
if results:
    summary_analyzer = SummaryAnalyzer()
    summary_analyzer.analyze_and_display_summary(results)
else:
    print("❌ No results data loaded")"""

        return nbformat.v4.new_code_cell(summary_code)


class ExecutableNotebookExport:
    """Notebook export using executable Python classes."""

    def __init__(
        self, notebook_path: str = "results.ipynb", json_path: str = "results.json"
    ):
        self.notebook_path = notebook_path
        self.json_path = json_path
        self.serializer = NotebookCodeSerializer()

    def create_notebook(self, results_dict: Dict[str, Any]) -> nbformat.NotebookNode:
        """Create notebook using executable classes."""
        nb = nbformat.v4.new_notebook()

        # Header
        header = nbformat.v4.new_markdown_cell("# NetGraph Results Analysis")
        nb.cells.append(header)

        # Setup environment
        setup_cell = self.serializer.create_setup_cell()
        nb.cells.append(setup_cell)

        # Load data
        data_cell = self.serializer.create_data_loading_cell(self.json_path)
        nb.cells.append(data_cell)

        # Add analysis sections based on available data
        if self._has_capacity_data(results_dict):
            capacity_header = nbformat.v4.new_markdown_cell(
                "## Capacity Matrix Analysis"
            )
            nb.cells.append(capacity_header)
            nb.cells.append(self.serializer.create_capacity_analysis_cell())

        if self._has_flow_data(results_dict):
            flow_header = nbformat.v4.new_markdown_cell("## Flow Analysis")
            nb.cells.append(flow_header)
            nb.cells.append(self.serializer.create_flow_analysis_cell())

        # Summary
        summary_header = nbformat.v4.new_markdown_cell("## Summary")
        nb.cells.append(summary_header)
        nb.cells.append(self.serializer.create_summary_cell())

        return nb

    def _has_capacity_data(self, results_dict: Dict[str, Any]) -> bool:
        """Check if results contain capacity envelope data."""
        return any(
            isinstance(data, dict) and "capacity_envelopes" in data
            for data in results_dict.values()
        )

    def _has_flow_data(self, results_dict: Dict[str, Any]) -> bool:
        """Check if results contain flow analysis data."""
        return any(
            isinstance(data, dict)
            and any(k.startswith("max_flow:") for k in data.keys())
            for data in results_dict.values()
        )
