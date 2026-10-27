"""Refusal context does not change accepted steps or extension exceptions."""

import pickle
from dataclasses import dataclass, fields
from enum import Enum, StrEnum

import pytest
import yaml

from ngraph import (
    CapacityQuery,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    StepOutput,
    UnitsSettings,
    WorkflowStep,
    prepare,
)
from ngraph.analysis.preparation import StepNeeds
from ngraph.utils.values import _shown
from ngraph.workflow import BuildGraph
from ngraph.workflow.base import _check_name_length
from ngraph.workflow.diagnostics import workflow_location
from ngraph.workflow.parse import build_workflow_steps

NET = {
    "nodes": {"A": {}, "B": {}},
    "links": [{"source": "A", "target": "B", "capacity": 8, "cost": 3}],
}
REASON = "no legal resolution represents the complete prepared input/augmented graph"


@pytest.mark.parametrize("kind", ["strenum", "mixin"])
def test_enum_workflow_names_keep_values_and_refusal_locations(kind):
    def member(value):
        return (
            StrEnum("Name", {"VALUE": value}).VALUE
            if kind == "strenum"
            else Enum("Name", {"VALUE": value}, type=str).VALUE
        )

    name = member("step")
    assert workflow_location(2, name) == "workflow[2] (name 'step')"
    assert workflow_location(2, member("")) == "workflow[2]"
    assert workflow_location(2, None) == "workflow[2]"
    assert _check_name_length(member("n" * 100)) == "n" * 100
    with pytest.raises(ValueError) as error:
        _check_name_length(member("n" * 101))
    assert str(error.value).startswith(
        "workflow step name: expected a name of at most 100 characters, got 101"
    )
    step = build_workflow_steps(
        [{"type": "BuildGraph", "name": name}], lambda name: None
    )[0]
    assert step.name == "step" and type(step.name) is str
    with pytest.raises(ValueError) as error:
        build_workflow_steps(
            [{"type": "BuildGraph", "name": name, "bad": True}], lambda name: None
        )
    assert str(error.value) == (
        "workflow[0] (name 'step') = {'type': 'BuildGraph', 'name': <Name.VALUE: 'step'>, 'bad...: "
        "Unrecognized key(s) in workflow step 'step': bad. "
        "Allowed keys are: ['add_reverse', 'name', 'seed']"
    )


def loaded(entry, resolution=1):
    data = {
        "network": NET,
        "units": {"resolution": resolution},
        "demands": {
            "load": [
                {
                    "source": "^A$",
                    "target": "^B$",
                    "volume": 1,
                    "model": {
                        "routing": {
                            "type": "centralized_te",
                            "source_allocation": "equal",
                            "tunnel_count": {"per_head": 1},
                        },
                        "admission": "lossy",
                    },
                }
            ]
        },
        "workflow": [{"type": "BuildGraph", "name": "g"}, entry],
    }
    return Scenario.from_yaml(yaml.safe_dump(data, sort_keys=False))


@pytest.mark.parametrize("resolution", [1, "auto"])
@pytest.mark.parametrize(
    "kind, field",
    [
        ("MaxFlow", "offer"),
        ("MaxFlow", "design_demand"),
        ("TunnelCountAnalysis", "offer"),
        ("TunnelCountAnalysis", "design_demand"),
    ],
)
def test_step_amount_resolution_refusal(kind, field, resolution):
    entry = {"type": kind, "name": "bad", "offer": 1, "design_demand": 1}
    entry.update(
        {"source": "^A$", "target": "^B$"}
        if kind == "MaxFlow"
        else {"demand_set": "load", "counts": [1]}
    )
    if kind == "MaxFlow":
        entry["model"] = {
            "routing": {
                "type": "centralized_te",
                "source_allocation": "equal",
                "tunnel_count": {"per_head": 1},
            },
            "admission": "lossy",
        }
    refused = 1e20 if resolution == 1 else 1e40
    entry[field] = refused
    with pytest.raises(ValueError) as error:
        prepare(loaded(entry, resolution))
    assert type(error.value) is ValueError
    assert (
        str(error.value) == f"workflow[1] (name 'bad').{field} = {refused!r}: {REASON}"
    )
    assert type(error.value.__cause__) is ValueError
    entry[field] = 1
    prepare(loaded(entry, resolution))
    if resolution == "auto":
        entry[field] = 1e20
        prepare(loaded(entry, resolution))


@dataclass
class ExtensionQuestion(WorkflowStep):
    refusal: Exception | None = None
    amount: float = 1

    def needs(self):
        return StepNeeds(
            numerical=True,
            capacity=self.query,
            inputs={"amount": ("demand", self.amount)},
        )

    def query(self, prepared):
        if self.refusal is not None:
            raise self.refusal
        return CapacityQuery(Selector("^A$"), Selector("^B$"))

    def run(self, context):
        return StepOutput({}, None)


def custom(step):
    net = Network(nodes={"A": Node("A"), "B": Node("B")})
    net.add_link(Link("A", "B", 8, 3))
    return Scenario(net, (BuildGraph(name="g"), step), units=UnitsSettings(1))


@pytest.mark.parametrize(
    "amount, reason",
    [(1e20, REASON), (-1, "expected a finite nonnegative amount, got -1")],
)
def test_extension_amount_uses_its_declared_field(amount, reason):
    with pytest.raises(ValueError) as error:
        prepare(custom(ExtensionQuestion(name="bad", amount=amount)))
    assert str(error.value) == f"workflow[1] (name 'bad').amount = {amount!r}: {reason}"
    prepare(custom(ExtensionQuestion(name="bad")))


@pytest.mark.parametrize("base", [ValueError, TypeError])
def test_builtin_exception_is_relabelled_and_chained(base):
    original = base("reserved")
    with pytest.raises(base) as error:
        prepare(custom(ExtensionQuestion(name="bad", refusal=original)))
    assert type(error.value) is base
    assert str(error.value) == "workflow[1] (name 'bad'): reserved"
    assert error.value.__cause__ is original
    prepare(custom(ExtensionQuestion(name="bad")))


@pytest.mark.parametrize("base", [ValueError, TypeError, RuntimeError])
def test_extension_exception_is_the_original_object(base):
    class Refusal(base):
        def __init__(self, field, value):
            self.field, self.value = field, value
            super().__init__(f"{field} = {value}: reserved")

    original = Refusal("count", 3)
    with pytest.raises(Refusal) as error:
        prepare(custom(ExtensionQuestion(name="bad", refusal=original)))
    assert error.value is original
    assert error.value.field == "count" and error.value.value == 3
    assert str(error.value) == "count = 3: reserved"
    assert error.value.__cause__ is None
    prepare(custom(ExtensionQuestion(name="bad")))


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "BuildGraph", "name": "b"},
        {"type": "CostPower", "name": "b"},
        {"type": "NetworkStats", "name": "b"},
        {"type": "MaxFlow", "name": "b", "source": "^A$", "target": "^B$"},
        {"type": "MaximumSupportedDemand", "name": "b", "demand_set": "load"},
        {"type": "TrafficMatrixPlacement", "name": "b", "demand_set": "load"},
        {
            "type": "TunnelCountAnalysis",
            "name": "b",
            "demand_set": "load",
            "counts": [1],
            "offer": 1,
            "design_demand": 1,
        },
    ],
)
def test_loading_does_not_store_diagnostic_state(entry):
    step = loaded(entry).workflow[1]
    assert set(vars(step)) == {f.name for f in fields(step)} | {"_constructed"}
    if entry["type"] in {"MaxFlow", "TrafficMatrixPlacement", "TunnelCountAnalysis"}:
        with pytest.raises(
            TypeError, match="cannot pickle '_netgraph_core.OutputOptions' object"
        ):
            pickle.dumps(step, protocol=4)
    else:
        assert pickle.loads(pickle.dumps(step, protocol=4)) == step


def test_loaded_build_step_keeps_its_serialized_state():
    step = loaded({"type": "BuildGraph", "name": "b"}).workflow[1]
    expected = BuildGraph(name="b", yaml_label="workflow step b")
    assert vars(step) == vars(expected)
    assert pickle.dumps(step, protocol=4) == pickle.dumps(expected, protocol=4)
    assert len(pickle.dumps(step, protocol=4)) == 162
    assert step == expected
    with pytest.raises(TypeError):
        hash(step)


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "NoSuchStep", "name": "x" * 100000},
        {"type": "BuildGraph", "name": "bad", "add_reverse": "x" * 100000},
    ],
)
def test_refusals_remain_bounded(entry):
    with pytest.raises(ValueError) as error:
        loaded(entry)
    message = str(error.value)
    assert len(message) < 500
    shown = "'" + "x" * 56 + "..."
    if entry["type"] == "NoSuchStep":
        assert (
            message == f"workflow[1] (name {shown}).name = {shown}: {shown} is too long"
        )
    else:
        reason = "'" + "x" * 216 + "..."
        assert message == f"workflow[1] (name 'bad').add_reverse = {shown}: {reason}"
    prepare(loaded({"type": "BuildGraph", "name": "good", "add_reverse": False}))


@pytest.mark.parametrize("base", [ValueError, TypeError])
def test_needs_refusal_keeps_its_builtin_type(base):
    @dataclass
    class Question(ExtensionQuestion):
        def needs(self):
            if self.refusal is not None:
                raise self.refusal
            return super().needs()

    original = base("reserved")
    with pytest.raises(base) as error:
        prepare(custom(Question(name="bad", refusal=original)))
    assert type(error.value) is base
    assert str(error.value) == "workflow[1] (name 'bad'): reserved"
    assert error.value.__cause__ is original
    prepare(custom(Question(name="bad")))


def test_parser_locates_an_extension_construction_exception(monkeypatch):
    class Refusal(ValueError):
        def __init__(self, field, value):
            super().__init__(f"{field} = {value}: reserved")

    original = Refusal("count", 3)

    def refuse(*args):
        raise original

    with monkeypatch.context() as patch:
        patch.setattr(BuildGraph, "yaml_arguments", refuse)
        with pytest.raises(ValueError) as error:
            build_workflow_steps(
                [{"type": "BuildGraph", "name": "bad"}], lambda name: None
            )
        assert type(error.value) is ValueError
        assert error.value.__cause__ is original
        assert (
            str(error.value)
            == "workflow[0] (name 'bad') = {'type': 'BuildGraph', 'name': 'bad'}: count = 3: reserved"
        )
    build_workflow_steps([{"type": "BuildGraph", "name": "bad"}], lambda name: None)


@pytest.mark.parametrize(
    "given, shown",
    [
        (b"abc", "b'abc'"),
        (1.25, "1.25"),
        (True, "True"),
        (None, "None"),
        ((1,), "(1,)"),
        ({"x": [3]}, "{'x': [3]}"),
    ],
    ids=["bytes", "float", "flag", "null", "tuple", "mapping"],
)
def test_primitive_refusal_values(given, shown):
    assert _shown(given) == shown


def test_long_list_representation_is_bounded():
    assert _shown(["x"] * 100000) == repr(["x"] * 100000)[:57] + "..."
