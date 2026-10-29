"""Hand-derived report and domain values, with shared field-checking helpers."""

import json
import math
import sys
from fractions import Fraction
from hashlib import sha256
from importlib.metadata import version
from io import StringIO
from pathlib import Path

import _netgraph_core

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
from ngraph.results import InputConstraint, PreparationScope, SplitCountConstraint
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
    # v_min=c_min=4, L=4 and Gamma=3. Manual q1 has input bound2 met,
    # split bound1/3 unmet, achieved3/4. Directed capacity/cost sums are8/6.
    expected_units = {
        "q": 1.0,
        "exponent": 0,
        "mode": "manual",
        "precision": 0.25,
        "target_met": False,
        "input_convention": "promoted_binary64_half_up",
        "display_convention": "units_authoritative_binary64_display",
        "scope": {
            "workflow_steps": [],
            "workflow_demand_sets": [],
            "library_demand_sets": ["load"],
        },
        "limited_by": "declared",
        "achieved_precision": {"numerator": 3, "denominator": 4},
        "input_bound": {
            "kind": "input",
            "label": "link.S|T|0.capacity",
            "q_upper_bound": {"numerator": 2, "denominator": 1},
            "met": True,
        },
        "split_bound": {
            "kind": "split_count",
            "capacity_label": "link.S|T|0.capacity",
            "capacity": 4.0,
            "nodes": 2,
            "directed_links": 2,
            "group": None,
            "demands": 0,
            "tunnels": 0,
            "count": {"numerator": 3, "denominator": 1},
            "q_upper_bound": {"numerator": 1, "denominator": 3},
            "met": False,
        },
        "range_limit": None,
        "augmented_capacity_sum_units": 8,
        "augmented_cost_sum": 6,
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
    expected_python["weight_approximations"] = ()
    expected_python["achieved_precision"] = Fraction(3, 4)
    expected_python["input_bound"] = InputConstraint(
        "link.S|T|0.capacity", Fraction(2), True
    )
    expected_python["split_bound"] = SplitCountConstraint(
        "link.S|T|0.capacity", 4.0, 2, 2, None, 0, 0, Fraction(3), Fraction(1, 3), False
    )
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


def test_units_python_and_wire_domain_metadata_have_complete_hand_expectations():
    value, expected, expected_python = fixture()
    exact(vars(value.units_report), expected_python)
    exact(project(value), expected)
