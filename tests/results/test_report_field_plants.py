"""Hand-derived report/domain values reject every emitted field near miss."""

import json
import math
import sys
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from importlib.metadata import version
from io import StringIO
from pathlib import Path

import _netgraph_core
import pytest

import ngraph.export as exporting
from ngraph import (
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    prepare,
    run,
    write_json,
)
from ngraph.results import PreparationScope, RunResult
from ngraph.workflow.build_graph import BuildGraph


def fixture():
    network = Network(nodes={name: Node(name) for name in ("S", "T")})
    network.add_link(Link("S", "T", 4, 3))
    demands = DemandSet(
        "load", (DemandSpec(Selector("^S$"), Selector("^T$"), 4, id="service"),)
    )
    prepared = prepare(
        Scenario(
            network,
            [BuildGraph(name="graph", seed=7)],
            demand_sets={"load": demands},
            seed=42,
            units=UnitsSettings(1, precision=0.25),
        ),
        demand_sets=("load",),
    )
    value = run(prepared)
    # One physical capacity and one physical parent input are both exactly4.
    # Their input bounds are2*1/4*4=2, so q1 is met and not binding (2q=2).
    # One source, one edge and no expansion fork produce no split constraints.
    # Both directions give capacity sum8 and cost sum6.
    expected_units = {
        "q": 1.0,
        "exponent": 0,
        "mode": "manual",
        "precision": 0.25,
        "target_met": True,
        "input_convention": "promoted_binary64_half_up",
        "display_convention": "units_authoritative_binary64_display",
        "scope": {
            "workflow_steps": [],
            "workflow_demand_sets": [],
            "library_demand_sets": ["load"],
        },
        "binding_constraints": [],
        "input_count": 2,
        "inexact_inputs": 0,
        "zeroed_inputs": 0,
        "inexact_examples": [],
        "zeroed_examples": [],
        "max_absolute_input_error": {"numerator": 0, "denominator": 1},
        "max_relative_input_error": {"numerator": 0, "denominator": 1},
        "augmented_capacity_sum_units": 8,
        "augmented_cost_sum": 6,
        "nominal_split_count": 0,
        "nominal_splits": [],
        "misses": [],
        "weight_approximations": [],
    }
    expected = {
        "metadata": {
            "schema_version": "1.0",
            "netgraph_version": version("ngraph"),
            "core_version": version("netgraph-core"),
            "core_extension_sha256": sha256(
                Path(_netgraph_core.__file__).read_bytes()
            ).hexdigest(),
            "python_version": sys.version.split()[0],
            "seed": 42,
        },
        "units_report": expected_units,
        "steps": [
            {
                "name": "graph",
                "step_type": "BuildGraph",
                "execution_order": 0,
                "scenario_seed": 42,
                "step_seed": 7,
                "seed_source": "explicit-step",
                "question": {
                    "kind": "build_graph",
                    "parameters": {"add_reverse": True},
                },
                "result": {
                    "kind": "build_graph",
                    "add_reverse": True,
                    "node_count": 2,
                    "edge_count": 2,
                    "graph": {
                        "directed": True,
                        "multigraph": True,
                        "graph": {},
                        "nodes": [
                            {"id": "S", "disabled": False},
                            {"id": "T", "disabled": False},
                        ],
                        "edges": [
                            {
                                "source": "S",
                                "target": "T",
                                "key": 0,
                                "id": "S|T|0",
                                "capacity": 4.0,
                                "cost": 3,
                                "disabled": False,
                            },
                            {
                                "source": "T",
                                "target": "S",
                                "key": 0,
                                "id": "S|T|0_reverse",
                                "capacity": 4.0,
                                "cost": 3,
                                "disabled": False,
                            },
                        ],
                    },
                },
            }
        ],
    }
    expected_python = dict(expected_units)
    # The two conventions are class constants of every report, not its fields.
    del expected_python["input_convention"], expected_python["display_convention"]
    expected_python["scope"] = PreparationScope((), (), ("load",))
    for name in (
        "binding_constraints",
        "inexact_examples",
        "zeroed_examples",
        "nominal_splits",
        "misses",
        "weight_approximations",
    ):
        expected_python[name] = ()
    for name in ("max_absolute_input_error", "max_relative_input_error"):
        expected_python[name] = Fraction(0)
    return value, expected, expected_python


def exact(actual, expected):
    assert type(actual) is type(expected), (type(actual), type(expected))
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for name in expected:
            exact(actual[name], expected[name])
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected, strict=True):
            exact(left, right)
    else:
        assert actual == expected, (actual, expected)


def project(value):
    output = StringIO()
    write_json(value, output)
    return json.loads(output.getvalue())


def field_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            path = (*prefix, key)
            yield path
            yield from field_paths(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from field_paths(child, (*prefix, index))


def near(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return math.nextafter(value, math.inf)
    if isinstance(value, str):
        return value + "!"
    if isinstance(value, list):
        rotated = value[1:] + value[:1]
        return rotated if rotated != value else [*value, None]
    if isinstance(value, dict):
        return {} if value else {"wrong": 0}
    return 0


def change(value, path, mode):
    parent = value
    for name in path[:-1]:
        parent = parent[name]
    name = path[-1]
    if mode == "missing":
        del parent[name]
    elif mode == "null":
        parent[name] = None
    else:
        parent[name] = near(parent[name])


def test_units_python_and_wire_domain_metadata_have_complete_hand_expectations():
    value, expected, expected_python = fixture()
    exact(vars(value.units_report), expected_python)
    exact(project(value), expected)


def test_report_projection_helper_field_plants_are_all_caught(monkeypatch):
    value, expected, _ = fixture()
    original = exporting._export_registered
    exact(project(value), expected)
    observed = tuple(field_paths(expected))
    caught = 0
    for path in observed:
        for mode in ("missing", "null", "wrong"):

            def planted(item, context, path=path, mode=mode):
                projected = original(item, context)
                if type(item) is RunResult:
                    projected = deepcopy(projected)
                    change(projected, path, mode)
                return projected

            with monkeypatch.context() as patch:
                patch.setattr(exporting, "_export_registered", planted)
                with pytest.raises(AssertionError):
                    exact(project(value), expected)
            caught += 1
    exact(project(value), expected)
    assert caught == 3 * len(observed)
    print(
        f"FIELD PLANTS: {len(observed)} emitted field paths; {caught} missing/null/near-value helper plants caught"
    )
