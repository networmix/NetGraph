"""Python and YAML refuse the same values, field by field, where each value is given.

The YAML schema and the constructors state one rule; each case runs bad values through
both, and good values through both with the same stored result. A schema refusal names
the field's path and value; a constructor's names the field and value.
"""

import copy
import json
import math
from importlib import resources

import jsonschema
import pytest
import yaml

from ngraph import (
    Component,
    DemandSpec,
    DirectedLink,
    FailureMode,
    FailureRule,
    Link,
    Node,
    RiskGroup,
    RouteSpec,
    Scenario,
    Selector,
    UnitsSettings,
)
from ngraph.workflow.base import step_type

NAN, INF = float("nan"), float("inf")

BASE = {
    "seed": 1,
    "network": {
        "nodes": {"A": {"attrs": {"role": "edge"}}, "T": {}},
        "links": [{"source": "A", "target": "T", "capacity": 5, "cost": 1}],
    },
    "risk_groups": [{"name": "rg"}],
    "components": {"chassis": {"capex": 10}},
    "failures": {"fp": {"modes": [{"weight": 1, "rules": [{"scope": "link"}]}]}},
    "demands": {
        "d": [
            {
                "source": {"path": "^A$", "group_by": "role"},
                "target": "^T$",
                "volume": 4,
            }
        ]
    },
    "routes": {"r": {"head": "A", "nodes": ["A", "T"]}},
    "units": {"resolution": 1},
    "workflow": [
        {"type": "BuildGraph", "name": "bg"},
        {"type": "NetworkStats", "name": "ns"},
        {"type": "CostPower", "name": "cp"},
        {"type": "MaxFlow", "name": "mf", "source": "^A$", "target": "^T$"},
        {"type": "MaximumSupportedDemand", "name": "msd", "demand_set": "d"},
        {"type": "TrafficMatrixPlacement", "name": "tmp", "demand_set": "d"},
    ],
}
STEP = {step["type"]: i for i, step in enumerate(BASE["workflow"])}


def step(kind, **fields):
    extra = {
        "MaxFlow": {"source": Selector("^A$"), "target": Selector("^T$")},
        "MaximumSupportedDemand": {"demand_set": "d"},
        "TrafficMatrixPlacement": {"demand_set": "d"},
    }.get(kind, {})
    return step_type(kind)(name="s", **extra, **fields)


def workflow(kind, field):
    return lambda s: getattr(s.workflow[STEP[kind]], field)


# (case, YAML path, Python build of a value, the stored value from Python, from YAML,
#  bad values, good values)
CASES = [
    (
        "link cost",
        ["network", "links", 0, "cost"],
        lambda v: Link("A", "T", cost=v),
        lambda o: o.cost,
        lambda s: s.network.links["A|T|0"].cost,
        [0, -1, 1.5, True, "1", None, 1 << 62],
        [1, 2.0, (1 << 62) - 1],
    ),
    (
        "link capacity",
        ["network", "links", 0, "capacity"],
        lambda v: Link("A", "T", v),
        lambda o: o.capacity,
        lambda s: s.network.links["A|T|0"].capacity,
        [-1, NAN, INF, True, "1"],
        [0, 2.5],
    ),
    (
        "link disabled",
        ["network", "links", 0, "disabled"],
        lambda v: Link("A", "T", disabled=v),
        lambda o: o.disabled,
        lambda s: s.network.links["A|T|0"].disabled,
        ["false", 1, None, 1.0],
        [True],
    ),
    (
        "node disabled",
        ["network", "nodes", "A", "disabled"],
        lambda v: Node("A", disabled=v),
        lambda o: o.disabled,
        lambda s: s.network.nodes["A"].disabled,
        ["false", 1, None],
        [True],
    ),
    (
        "risk group disabled",
        ["risk_groups", 0, "disabled"],
        lambda v: RiskGroup("rg", disabled=v),
        lambda o: o.disabled,
        lambda s: s.network.risk_groups["rg"].disabled,
        ["false", 1, None],
        [True],
    ),
    (
        "risk group name",
        ["risk_groups", 0, "name"],
        lambda v: RiskGroup(v),
        lambda o: o.name,
        lambda s: next(iter(s.network.risk_groups)),
        ["", 1, True, b"name"],
        [" g"],
    ),
    *(
        (
            f"component {name}",
            ["components", "chassis", name],
            lambda v, name=name: Component("chassis", **{name: v}),
            lambda o, name=name: getattr(o, name),
            lambda s, name=name: getattr(
                s.components_library.components["chassis"], name
            ),
            [-1, NAN, INF, True, "1"],
            [0, 2.5],
        )
        for name in ("capex", "power_watts", "power_watts_max", "capacity")
    ),
    (
        "component ports",
        ["components", "chassis", "ports"],
        lambda v: Component("chassis", ports=v),
        lambda o: o.ports,
        lambda s: s.components_library.components["chassis"].ports,
        [-1, 1.5, True, "1"],
        [0, 4, 4.0],
    ),
    (
        "component count",
        ["components", "chassis", "count"],
        lambda v: Component("chassis", count=v),
        lambda o: o.count,
        lambda s: s.components_library.components["chassis"].count,
        [0, -1, 1.5, True, "1"],
        [1, 2.0],
    ),
    (
        "failure mode weight",
        ["failures", "fp", "modes", 0, "weight"],
        lambda v: FailureMode(v),
        lambda o: o.weight,
        lambda s: s.failure_policies["fp"].modes[0].weight,
        [-1, NAN, INF, True, "1"],
        [0.5, 2],
    ),
    (
        "failure rule count",
        ["failures", "fp", "modes", 0, "rules", 0, "count"],
        lambda v: FailureRule("link", count=v),
        lambda o: o.count,
        lambda s: s.failure_policies["fp"].modes[0].rules[0].count,
        [0, -1, 1.5, True, "1"],
        [1, 3.0],
    ),
    (
        "failure rule probability",
        ["failures", "fp", "modes", 0, "rules", 0, "probability"],
        lambda v: FailureRule("link", probability=v),
        lambda o: o.probability,
        lambda s: s.failure_policies["fp"].modes[0].rules[0].probability,
        [-0.5, 1.5, NAN, True, "1"],
        [0, 0.5, 1],
    ),
    (
        "failure rule weight_by",
        ["failures", "fp", "modes", 0, "rules", 0, "weight_by"],
        lambda v: FailureRule("link", weight_by=v),
        lambda o: o.weight_by,
        lambda s: s.failure_policies["fp"].modes[0].rules[0].weight_by,
        ["", 1, True, b"name"],
        ["w"],
    ),
    (
        "failure rule path",
        ["failures", "fp", "modes", 0, "rules", 0, "path"],
        lambda v: FailureRule("link", path=v),
        lambda o: o.path,
        lambda s: s.failure_policies["fp"].modes[0].rules[0].path,
        ["([", 1, b"pattern"],
        ["^A", ""],
    ),
    (
        "demand volume",
        ["demands", "d", 0, "volume"],
        lambda v: DemandSpec(Selector("^A$"), Selector("^T$"), v),
        lambda o: o.volume,
        lambda s: s.demand_sets["d"].demands[0].volume,
        [-1, NAN, INF, True, "1"],
        [0, 2.5],
    ),
    (
        "demand priority",
        ["demands", "d", 0, "priority"],
        lambda v: DemandSpec(Selector("^A$"), Selector("^T$"), 1, priority=v),
        lambda o: o.priority,
        lambda s: s.demand_sets["d"].demands[0].priority,
        [1.5, True, "1"],
        [-1, 2, 2.0],
    ),
    (
        "selector group_by",
        ["demands", "d", 0, "source", "group_by"],
        lambda v: Selector("^A$", group_by=v),
        lambda o: o.group_by,
        lambda s: s.demand_sets["d"].demands[0].source.group_by,
        ["", 1, b"role"],
        ["role"],
    ),
    (
        "selector path",
        ["demands", "d", 0, "source", "path"],
        lambda v: Selector(v, group_by="role"),
        lambda o: o.path,
        lambda s: s.demand_sets["d"].demands[0].source.path,
        ["([", 1, b"pattern"],
        ["^A$", ""],
    ),
    (
        "units precision",
        ["units", "precision"],
        lambda v: UnitsSettings(precision=v),
        lambda o: o.precision,
        lambda s: s.units.precision,
        [0, -1, NAN, True, "1", 0.50001, 1],
        [0.01, 0.5],
    ),
    (
        "units resolution",
        ["units", "resolution"],
        lambda v: UnitsSettings(v),
        lambda o: o.resolution,
        lambda s: s.units.resolution,
        [0, -1, INF, True, "AUTO", 3],
        [1, 0.5, "auto"],
    ),
    (
        "route weight",
        ["routes", "r", "weight"],
        lambda v: RouteSpec("A", nodes=("A", "T"), weight=v),
        lambda o: o.weight,
        lambda s: s.routes["r"].weight,
        [-1, 1.5, True, 1 << 62],
        [0, 3, 3.0],
    ),
    (
        "route nodes",
        ["routes", "r", "nodes"],
        lambda v: RouteSpec(
            "A",
            nodes=v,
            edges=(DirectedLink("A|T|0", "forward"),) if v is None else None,
        ),
        lambda o: o.nodes,
        lambda s: s.routes["r"].nodes,
        [["A"], ["A", ""], ["A", 1]],
        [["A", "T"]],
    ),
    (
        "BuildGraph add_reverse",
        ["workflow", STEP["BuildGraph"], "add_reverse"],
        lambda v: step("BuildGraph", add_reverse=v),
        lambda o: o.add_reverse,
        workflow("BuildGraph", "add_reverse"),
        ["false", 1, None],
        [False],
    ),
    (
        "NetworkStats include_disabled",
        ["workflow", STEP["NetworkStats"], "include_disabled"],
        lambda v: step("NetworkStats", include_disabled=v),
        lambda o: o.include_disabled,
        workflow("NetworkStats", "include_disabled"),
        ["false", 1],
        [True],
    ),
    (
        "CostPower aggregation_level",
        ["workflow", STEP["CostPower"], "aggregation_level"],
        lambda v: step("CostPower", aggregation_level=v),
        lambda o: o.aggregation_level,
        workflow("CostPower", "aggregation_level"),
        [-1, 1.5, True, "1"],
        [0, 3, 3.0],
    ),
    (
        "MaxFlow iterations",
        ["workflow", STEP["MaxFlow"], "iterations"],
        lambda v: step("MaxFlow", iterations=v),
        lambda o: o.iterations,
        workflow("MaxFlow", "iterations"),
        [-1, 1.5, True, "1"],
        [0, 2, 2.0],
    ),
    (
        "MaxFlow offer",
        ["workflow", STEP["MaxFlow"], "offer"],
        lambda v: step("MaxFlow", offer=v),
        lambda o: o.offer,
        workflow("MaxFlow", "offer"),
        [-1, NAN, INF, True, "1"],
        [0, 2.5],
    ),
    (
        "MaxFlow failure_trace",
        ["workflow", STEP["MaxFlow"], "failure_trace"],
        lambda v: step("MaxFlow", failure_trace=v),
        lambda o: o.failure_trace,
        workflow("MaxFlow", "failure_trace"),
        ["false", 1],
        [True],
    ),
    (
        "MaxFlow workers",
        ["workflow", STEP["MaxFlow"], "workers"],
        lambda v: step("MaxFlow", workers=v),
        lambda o: o.workers,
        workflow("MaxFlow", "workers"),
        [0, -1, 1.5, True, "x"],
        [1, "auto", 2.0],
    ),
    (
        "MSD growth_factor",
        ["workflow", STEP["MaximumSupportedDemand"], "growth_factor"],
        lambda v: step("MaximumSupportedDemand", growth_factor=v),
        lambda o: o.growth_factor,
        workflow("MaximumSupportedDemand", "growth_factor"),
        [0, -1, NAN, True, "2", 1],
        [2, 1.5],
    ),
    (
        "MSD max_bisect_iters",
        ["workflow", STEP["MaximumSupportedDemand"], "max_bisect_iters"],
        lambda v: step("MaximumSupportedDemand", max_bisect_iters=v),
        lambda o: o.max_bisect_iters,
        workflow("MaximumSupportedDemand", "max_bisect_iters"),
        [0, 1.5, True],
        [1, 4.0],
    ),
    (
        "placement alpha",
        ["workflow", STEP["TrafficMatrixPlacement"], "alpha"],
        lambda v: step("TrafficMatrixPlacement", alpha=v),
        lambda o: o.alpha,
        workflow("TrafficMatrixPlacement", "alpha"),
        [0, -1, NAN, INF, True, "1"],
        [0.5, 2],
    ),
    (
        "scenario seed",
        ["seed"],
        lambda v: Scenario(Scenario.from_yaml("{}").network, seed=v),
        lambda o: o.seed,
        lambda s: s.seed,
        [1.5, True, "1"],
        [-1, 7, 7.0],
    ),
]


_NULLABLE = {
    "failure rule weight_by",
    "failure rule path",
    "selector group_by",
    "selector path",
    "route nodes",
    "MaxFlow offer",
    "placement alpha",
    "scenario seed",
}
for _case, _, _, _, _, _bad, _good in CASES:
    if None not in _bad and None not in _good:
        (_good if _case in _NULLABLE else _bad).append(None)


def data_with(path, value):
    data = copy.deepcopy(BASE)
    node = data
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    if path == ["routes", "r", "nodes"] and value is None:
        node["edges"] = [{"link": "A|T|0", "direction": "forward"}]
    return data


def load(path, value):
    return Scenario.from_yaml(yaml.safe_dump(data_with(path, value), sort_keys=False))


def same(a, b):
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    return a == b and type(a) is type(b)


@pytest.mark.parametrize(
    ("case", "path", "build", "from_python", "from_yaml", "bad", "good"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_python_and_yaml_refuse_and_store_the_same_values(
    case, path, build, from_python, from_yaml, bad, good
):
    validator = jsonschema.validators.validator_for(SCHEMA)(SCHEMA)
    label = PYTHON_LABELS.get(case, case.replace(" ", ".", 1))
    for value in bad:
        with pytest.raises((ValueError, TypeError)) as python_error:
            build(value)
        # A looser schema must fail this test even when the constructor still refuses.
        data = data_with(path, value)
        schema_errors = list(validator.iter_errors(data))
        if constructor_only(case, value):
            assert not schema_errors, (case, value, schema_errors)
        else:
            assert schema_errors, (case, value, "schema accepted a bad value")
        with pytest.raises(ValueError) as yaml_error:
            load(path, value)
        plain = value["group_by"] if isinstance(value, dict) else value
        if case == "route nodes":
            plain = tuple(value) if len(value) < 2 else value[1]
        python_message = str(python_error.value)
        assert python_message.startswith(label + ": "), (case, value, python_message)
        assert repr(plain) in python_message, (case, value, python_message)
        field_path = list(path)
        if case == "selector group_by" and field_path[-1] != "group_by":
            field_path += ["group_by"]
        if case == "route nodes" and len(value) >= 2:
            field_path += [1]
        raw = value["group_by"] if isinstance(value, dict) else value
        if case == "route nodes" and len(value) >= 2:
            raw = value[1]
        cause = yaml_error.value.__cause__
        if isinstance(cause, jsonschema.ValidationError):
            assert (
                str(yaml_error.value)
                == f"{location(field_path)} = {raw!r}: {cause.message}"
            )
        else:
            if case == "selector path" and field_path[-1] != "path":
                field_path += ["path"]
            expected = location(field_path)
            if field_path[0] == "workflow":
                expected += f" = {raw!r}"
            expected += python_message[len(label) :]
            assert str(yaml_error.value) == expected, (
                case,
                value,
                str(yaml_error.value),
                expected,
            )
    for value in good:
        stored = from_python(build(value))
        assert same(from_yaml(load(path, value)), stored), (case, value)
        assert stored == (value["group_by"] if isinstance(value, dict) else value) or (
            isinstance(stored, tuple) and list(stored) == value
        )


SCHEMA = json.loads(
    resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
)


# JSON Schema describes JSON numbers, not finiteness; it cannot compile Python regexes
# or express power-of-two membership. Fraction strings need arithmetic parsing too
# (tested with routing shares separately). All other local bad values fail schema alone.
def constructor_only(case, value):
    return (
        (
            isinstance(value, float)
            and not math.isfinite(value)
            and case != "units resolution"
        )
        or (case in ("failure rule path", "selector path") and value == "([")
        or (case == "units resolution" and value == 3)
    )


PYTHON_LABELS = {
    "link cost": "link A->T.cost",
    "link capacity": "link A->T.capacity",
    "link disabled": "link A->T.disabled",
    "node disabled": "node A.disabled",
    "risk group disabled": "risk group rg.disabled",
    "risk group name": "risk group.name",
    **{
        f"component {field}": f"component chassis.{field}"
        for field in (
            "capex",
            "power_watts",
            "power_watts_max",
            "capacity",
            "ports",
            "count",
        )
    },
    **{
        f"failure rule {field}": f"failure rule {field}"
        for field in ("count", "probability", "weight_by", "path")
    },
    "failure mode weight": "failure mode weight",
    "MaxFlow workers": "workers",
    "MSD growth_factor": "MaximumSupportedDemand.growth_factor",
    "MSD max_bisect_iters": "MaximumSupportedDemand.max_bisect_iters",
    "placement alpha": "TrafficMatrixPlacement.alpha",
    "scenario seed": "Scenario.seed",
}


def location(path):
    result = ""
    for index, part in enumerate(path):
        result += (
            f"[{part}]" if isinstance(part, int) else ("." if result else "") + part
        )
        if path[: index + 1] == ["network", "links", 0]:
            result += " (A->T)"
        if path[:index] == ["workflow"]:
            result += f" (name {BASE['workflow'][part]['name']!r})"
    return result


def test_every_parity_row_declares_null_as_accepted_or_refused():
    for case, _, _, _, _, bad, good in CASES:
        assert any(value is None for value in (*bad, *good)), case
