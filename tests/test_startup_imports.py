"""Importing the package loads only what a run uses."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import ngraph


def check(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-B", "-c", code], text=True, capture_output=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "verified"


def test_public_names_load_their_modules_on_first_use_and_keep_identity():
    check(
        """
import sys
import ngraph
loaded = {m for m in sys.modules if m == "ngraph" or m.startswith("ngraph.")}
assert loaded == {"ngraph", "ngraph.logging"}, sorted(loaded)
for module in ("ngraph.analysis.paths", "ngraph.analysis.sensitivity",
               "ngraph.results", "ngraph.scenario", "ngraph.explorer"):
    assert module not in sys.modules, module
assert "PathQuery" in ngraph.__all__ and "PathQuery" in dir(ngraph)
from ngraph import PathQuery, paths, SensitivityQuery, edge_sensitivity, Node
from ngraph.analysis.paths import PathQuery as NativePathQuery, paths as native_paths
from ngraph.analysis.sensitivity import SensitivityQuery as NativeSensitivityQuery
from ngraph.analysis.sensitivity import edge_sensitivity as native_sensitivity
from ngraph.model.network import Node as ModelNode
assert PathQuery is NativePathQuery and paths is native_paths
assert SensitivityQuery is NativeSensitivityQuery and edge_sensitivity is native_sensitivity
assert ngraph.PathQuery is PathQuery and ngraph.paths is paths and Node is ModelNode
assert isinstance(ngraph.__version__, str)
try:
    ngraph.no_such_public_name
except AttributeError as exc:
    assert "no_such_public_name" in str(exc)
else:
    raise AssertionError("unknown public attribute accepted")
print("verified")
"""
    )


@pytest.mark.slow
def test_a_scenario_run_loads_no_unused_dependency_or_step():
    check(
        """
import sys
from ngraph.cli import main
from ngraph.scenario import Scenario
main(["--quiet", "run", "scenarios/readme_example.yml", "--no-results"])
for module in ("networkx", "ngraph.explorer",
               "ngraph.workflow.build_graph", "ngraph.workflow.cost_power"):
    assert module not in sys.modules, module
import ngraph.workflow as workflow
assert "ngraph.workflow.build_graph" not in sys.modules
from ngraph.workflow import BuildGraph
assert "networkx" not in sys.modules
assert BuildGraph.__module__ == "ngraph.workflow.build_graph"
assert workflow.BuildGraph is BuildGraph
Scenario.from_yaml(
    "network: {nodes: {A: {}}}\\nworkflow: [{type: NetworkStats, name: s}]\\n"
)
assert "ngraph.workflow.network_stats" in sys.modules
print("verified")
"""
    )


def test_the_yaml_parser_loads_only_the_step_types_it_meets():
    check(
        """
import sys
from ngraph.scenario import Scenario
Scenario.from_yaml(
    "network: {nodes: {A: {}}}\\nworkflow: [{type: NetworkStats, name: s}]\\n"
)
assert "ngraph.workflow.network_stats" in sys.modules
for name in ("max_flow_step", "maximum_supported_demand_step",
             "traffic_matrix_placement_step", "build_graph", "cost_power"):
    assert f"ngraph.workflow.{name}" not in sys.modules, name
print("verified")
"""
    )


def test_unrequested_program_and_cost_helpers_stay_unloaded_until_needed():
    check(
        """
import sys
from dataclasses import replace
from ngraph import (
    CapacityQuery, DemandSet, DemandSpec, Link, Network, Node, PlacementQuery,
    RouteSpec, Scenario, Selector, UnitsSettings, capacity, place, prepare,
)
assert "ngraph.analysis.programs" not in sys.modules
assert "ngraph.analysis.costs" not in sys.modules
n = Network(nodes={name: Node(name) for name in ("A", "B")})
n.add_link(Link("A", "B", 8))
s = Scenario(n, demand_sets={"d": DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^B$"), 2),))}, units=UnitsSettings(1))
p = prepare(s, demand_sets=("d",))
assert "ngraph.analysis.programs" not in sys.modules
query = CapacityQuery(Selector("^A$"), Selector("^B$"), workers=1)
assert capacity(p, query).cases[0].states["converged"].rows[0].result.delivered == 8
assert place(p, PlacementQuery(p.demand_sets["d"], workers=1)).cases[0].states["converged"].rows[0].result.delivered == 2
assert "ngraph.analysis.programs" not in sys.modules
assert "ngraph.analysis.costs" not in sys.modules
with_cost = capacity(p, CapacityQuery(Selector("^A$"), Selector("^B$"), workers=1, export_cost_distribution=True))
assert with_cost.cases[0].states["converged"].rows[0].cost_distribution is not None
assert "ngraph.analysis.costs" in sys.modules
routed = replace(s, routes={"fixed": RouteSpec("A", nodes=("A", "B"))})
compiled = prepare(routed, demand_sets=("d",))
assert "ngraph.analysis.programs" in sys.modules
assert "fixed" in compiled._named.routes
print("verified")
"""
    )


def test_the_three_public_name_declarations_agree():
    """TYPE_CHECKING imports, the lazy-load map and __all__ name the same symbols."""
    source = Path(ngraph.__file__).read_text()
    typed = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            for item in node.body:
                if isinstance(item, ast.ImportFrom):
                    typed |= {alias.asname or alias.name for alias in item.names}
    mapped = set(ngraph._EXPORTS)
    exported = set(ngraph.__all__) - {"__version__"}
    assert typed == mapped == exported
    assert len(exported) == 123


def test_command_line_help_loads_no_engine():
    """`ngraph --help` and argument errors need no Core, NumPy, YAML or analysis module."""
    check(
        """
import contextlib, io, sys
from ngraph.cli import main
with contextlib.redirect_stdout(io.StringIO()) as help_text:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
assert "usage: ngraph" in help_text.getvalue()
for module in ("netgraph_core", "_netgraph_core", "numpy", "yaml", "ngraph.scenario",
               "ngraph.hardware", "ngraph.workflow.base", "ngraph.explorer"):
    assert module not in sys.modules, module
loaded = sorted(m for m in sys.modules if m == "ngraph" or m.startswith("ngraph."))
assert loaded == ["ngraph", "ngraph.cli", "ngraph.logging", "ngraph.utils",
                  "ngraph.utils.output_paths"], loaded
print("verified")
"""
    )


@pytest.mark.slow
def test_a_cost_power_run_loads_the_inventory_not_the_explorer():
    """CostPower reads ngraph.hardware; the explorer stays unloaded."""
    check(
        """
import sys
from ngraph.scenario import Scenario, prepare, run
scenario = Scenario.from_yaml(
    "network: {nodes: {A: {attrs: {hardware: {component: C}}}}}\\n"
    "components: {C: {capex: 2}}\\n"
    "workflow: [{type: CostPower, name: c, aggregation_level: 0}]\\n"
)
assert run(prepare(scenario)).steps[0].result.levels[0][0].capex_total == 2.0
assert "ngraph.hardware" in sys.modules
assert "ngraph.explorer" not in sys.modules
print("verified")
"""
    )
