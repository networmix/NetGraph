"""Constructor boundaries and read-only mapping results retain ordinary semantics."""

import ast
import inspect
import json
import math
import signal
from fractions import Fraction
from importlib import resources

import jsonschema
import numpy as np
import pytest
import yaml

from ngraph import (
    Component,
    ComponentsLibrary,
    CostPowerResult,
    DirectedLink,
    GroupChild,
    Network,
    Scenario,
    prepare,
    run,
)
from ngraph.dsl.expansion.schema import ExpansionSpec
from ngraph.model.risk import GenerateSpec, MembershipSpec
from ngraph.workflow import CostPower


@pytest.fixture(autouse=True)
def bounded_case():
    previous = signal.signal(
        signal.SIGALRM, lambda *args: pytest.fail("case exceeded 3 seconds")
    )
    signal.alarm(3)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


TEXT_FIELDS = [
    (lambda v: GenerateSpec(v, "role", "rg-${value}"), "generate.scope", "node"),
    (lambda v: GenerateSpec("node", v, "rg-${value}"), "generate.group_by", "role"),
    (lambda v: GenerateSpec("node", "role", v), "generate.name", "rg-${value}"),
    (lambda v: MembershipSpec(v), "membership.scope", "node"),
    (lambda v: ExpansionSpec({"x": [1]}, v), "expand.mode", "cartesian"),
    (lambda v: ExpansionSpec({v: [1]}), "expand.vars key", "x"),
]


@pytest.mark.parametrize("build,label,good", TEXT_FIELDS)
@pytest.mark.parametrize("bad", ["", b"text"])
def test_new_text_fields_refuse_empty_and_wrong_kind(build, label, good, bad):
    with pytest.raises(ValueError) as error:
        build(bad)
    detail = "a nonempty name" if bad == "" else "text"
    assert str(error.value) == f"{label}: expected {detail}, got {bad!r}"
    build(good)


@pytest.mark.parametrize("kind", [GenerateSpec, MembershipSpec])
def test_new_pattern_fields_allow_empty_matching_text(kind):
    obj = (
        kind("node", "role", "r-${value}", path="")
        if kind is GenerateSpec
        else kind("node", path="")
    )
    assert obj.path == ""
    with pytest.raises(ValueError) as error:
        if kind is GenerateSpec:
            kind("node", "role", "r-${value}", path=b"pattern")
        else:
            kind("node", path=b"pattern")
    label = "generate" if kind is GenerateSpec else "membership"
    assert str(error.value) == f"{label}.path: expected text, got b'pattern'"


def test_membership_match_requires_a_match_record():
    with pytest.raises(TypeError) as error:
        MembershipSpec("node", match=1)
    assert str(error.value) == "membership.match: expected MatchSpec or None, got 1"
    assert MembershipSpec("node", path="A").path == "A"


@pytest.mark.parametrize(
    "vars", [{"x": list(range(10001))}, {"x": list(range(101)), "y": list(range(101))}]
)
def test_expansion_size_is_bounded_at_spec_construction(vars):
    size = math.prod(map(len, vars.values()))
    with pytest.raises(ValueError) as error:
        ExpansionSpec(vars)
    assert (
        str(error.value)
        == f"expand.vars: Template expansion would create {size} items (limit: 10000). Consider using fewer variables or splitting into multiple entries."
    )
    assert len(ExpansionSpec({"x": list(range(10000))}).vars["x"]) == 10000


@pytest.mark.parametrize("key", [1, np.int64(1), np.uint64(1)])
def test_cost_power_levels_compare_and_index_as_a_mapping(key):
    result = (
        run(prepare(Scenario(Network(), workflow=[CostPower(aggregation_level=4)])))
        .steps[0]
        .result
    )
    # Use the public run's result, not a private mapping constructor.
    assert isinstance(result, CostPowerResult)
    expected = {i: () for i in range(5)}
    assert result.levels == expected and expected == result.levels
    assert result == CostPowerResult(False, 4, expected)
    assert result.levels[key] == ()
    with pytest.raises(TypeError):
        hash(result.levels)
    assert result.levels != {0: ()}
    assert result.levels != {i: ((None,) if i == 1 else ()) for i in range(5)}
    for invalid in (-1, "x", None, 1.5):
        with pytest.raises(KeyError):
            result.levels[invalid]
    with pytest.raises(KeyError):
        result.levels[5]


@pytest.mark.parametrize(
    "loader", ["constructor", "dict", "yaml", "nested", "scenario"]
)
def test_component_count_is_bounded_before_float_consumers(loader):
    def build(count):
        if loader == "constructor":
            return Component("c", count=count)
        data = {"c": {"count": count}}
        if loader == "nested":
            return (
                ComponentsLibrary.from_dict({"p": {"children": data}})
                .get("p")
                .children["c"]
            )
        if loader == "dict":
            return ComponentsLibrary.from_dict(data).get("c")
        source = yaml.safe_dump({"components": data})
        if loader == "yaml":
            return ComponentsLibrary.from_yaml(source).get("c")
        return Scenario.from_yaml(source).components_library.get("c")

    maximum = (1 << 1024) - (1 << 970) - 1
    for value in (maximum + 1, 10**400):
        with pytest.raises(ValueError) as error:
            build(value)
        label = (
            "component c"
            if loader == "constructor"
            else "components.p.children.c"
            if loader == "nested"
            else "components.c"
        )
        assert str(error.value).startswith(label + ".count")
        assert str(value)[:57] in str(error.value)
    assert build(maximum).count == maximum
    assert math.isfinite(float(build(maximum).count))


def test_fractional_share_error_describes_all_supported_kinds():
    edge = DirectedLink("A|B|0", "forward")
    with pytest.raises(ValueError) as error:
        GroupChild(2.5, edge)
    assert (
        str(error.value)
        == "group_child.share: expected an exact share (integer, fraction string or Fraction), got 2.5"
    )
    assert GroupChild("5/2", edge).share == Fraction(5, 2)


def test_capacity_helper_and_link_creation_have_no_redundant_checks():
    from ngraph.analysis.capacity import validate_capacity_inputs
    from ngraph.dsl.blueprints.expand import _create_link

    assert tuple(inspect.signature(validate_capacity_inputs).parameters) == (
        "source",
        "target",
        "config",
        "outputs",
    )
    calls = [
        n
        for n in ast.walk(ast.parse(inspect.getsource(_create_link)))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "integer"
    ]
    assert calls == []


def test_component_count_schema_has_the_same_float_conversion_boundary():
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    validator = jsonschema.validators.validator_for(schema)(schema)
    maximum = (1 << 1024) - (1 << 970) - 1
    validator.validate({"components": {"c": {"count": maximum}}})
    for bad in (maximum + 1, 10**400):
        assert list(validator.iter_errors({"components": {"c": {"count": bad}}}))
