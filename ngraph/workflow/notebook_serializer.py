"""Code serialization for notebook generation."""

from typing import TYPE_CHECKING, List

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

    @staticmethod
    def create_flow_availability_cells() -> List[nbformat.NotebookNode]:
        """Create flow availability analysis cells (markdown header + code)."""
        # Markdown header cell
        header_cell = nbformat.v4.new_markdown_cell("## Flow Availability Analysis")

        # Code analysis cell
        flow_code = """# Flow Availability Distribution Analysis
if results:
    capacity_analyzer = CapacityMatrixAnalyzer()

    # Find steps with total flow samples (total_capacity_samples)
    flow_steps = []
    for step_name, step_data in results.items():
        if isinstance(step_data, dict) and 'total_capacity_samples' in step_data:
            samples = step_data['total_capacity_samples']
            if isinstance(samples, list) and len(samples) > 0:
                flow_steps.append(step_name)

    if flow_steps:
        for step_name in flow_steps:
            capacity_analyzer.analyze_and_display_flow_availability(results, step_name)
    else:
        print("ℹ️  No flow availability data found")
        print("   To generate this analysis, run CapacityEnvelopeAnalysis with baseline=True")
else:
    print("❌ No results data available")"""

        code_cell = nbformat.v4.new_code_cell(flow_code)

        return [header_cell, code_cell]
