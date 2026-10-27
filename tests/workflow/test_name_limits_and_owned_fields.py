"""Step names are short identifiers; each refusing reader owns its field."""

import inspect
import json
from dataclasses import dataclass
from importlib import resources

import pytest
import yaml

from ngraph import CapacityQuery, Network, Scenario, Selector, StepOutput, prepare
from ngraph.analysis.preparation import StepNeeds
from ngraph.utils.values import text
from ngraph.workflow import BuildGraph, TunnelCountAnalysis, WorkflowStep
from ngraph.workflow.base import WORKFLOW_STEP_REGISTRY
from ngraph.workflow.diagnostics import error_context
from ngraph.workflow.parse import build_workflow_steps

NET = {
    "nodes": {"A": {}, "B": {}},
    "links": [{"source": "A", "target": "B", "capacity": 8}],
}


def shown_name(name):
    raw = repr(name)
    return raw if len(raw) <= 60 else raw[:57] + "..."


@dataclass
class Edited(WorkflowStep):
    def needs(self):
        return None

    def run(self, context):
        return StepOutput({}, None)


@pytest.mark.parametrize("boundary", ["python", "parser", "yaml", "prepare"])
@pytest.mark.parametrize("size", [100, 101, 100000])
def test_name_length_at_each_boundary(boundary, size):
    name = "x" * size
    entry = {"type": "BuildGraph", "name": name}

    def call():
        if boundary == "python":
            return BuildGraph(name=name)
        if boundary == "parser":
            return build_workflow_steps([entry], lambda name: None)
        if boundary == "yaml":
            return Scenario.from_yaml(
                yaml.safe_dump({"network": {}, "workflow": [entry]})
            )
        step = Edited(name="short")
        scenario = Scenario(Network(), [step])
        step.name = name
        return prepare(scenario)

    if size == 100:
        call()
        return
    reason = f"expected a name of at most 100 characters, got {size}"
    if boundary == "python":
        expected = "workflow step name: " + reason
    else:
        if boundary == "yaml":
            reason = shown_name(name) + " is too long"
        expected = (
            f"workflow[0] (name {shown_name(name)}).name = {shown_name(name)}: {reason}"
        )
    with pytest.raises(ValueError) as error:
        call()
    assert str(error.value) == expected
    assert len(str(error.value)) < 300
    if boundary == "yaml":
        assert error.value.__cause__.validator == "maxLength"


def test_name_limit_counts_plain_characters_and_precedes_other_fields():
    assert BuildGraph(name="🦋" * 100).name == "🦋" * 100
    with pytest.raises(ValueError) as error:
        BuildGraph(name="🦋" * 101, seed="bad")
    assert (
        str(error.value)
        == "workflow step name: expected a name of at most 100 characters, got 101"
    )
    entry = {"type": "BuildGraph", "name": "x" * 101, "bogus": True}
    with pytest.raises(ValueError) as error:
        build_workflow_steps([entry], lambda name: None)
    assert str(error.value) == (
        f"workflow[0] (name {shown_name(entry['name'])}).name = {shown_name(entry['name'])}: "
        "expected a name of at most 100 characters, got 101"
    )


def test_generated_name_and_edited_duplicate_check_the_same_limit(monkeypatch):
    kind = "x" * 99
    monkeypatch.setitem(WORKFLOW_STEP_REGISTRY, kind, Edited)

    def arguments(cls, values, name):
        if len(name) > 100:
            raise ValueError("name reached the field reader before validation")
        return values

    monkeypatch.setattr(Edited, "yaml_arguments", classmethod(arguments))
    short_kind = "y" * 98
    monkeypatch.setitem(WORKFLOW_STEP_REGISTRY, short_kind, Edited)
    assert (
        build_workflow_steps([{"type": short_kind}], lambda name: None)[0].name
        == short_kind + "_0"
    )
    with pytest.raises(ValueError) as error:
        build_workflow_steps([{"type": kind}], lambda name: None)
    name = kind + "_0"
    assert str(error.value) == (
        f"workflow[0] (name {shown_name(name)}).name = {shown_name(name)}: "
        "expected a name of at most 100 characters, got 101"
    )
    first, second = Edited(name="a"), Edited(name="b")
    scenario = Scenario(Network(), [first, second])
    first.name = second.name = "x" * 101
    with pytest.raises(ValueError) as error:
        prepare(scenario)
    assert str(error.value) == (
        f"workflow[0] (name {shown_name(name)}).name = {shown_name(name)}: "
        "expected a name of at most 100 characters, got 101"
    )


def test_each_workflow_schema_name_has_the_limit():
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    workflow = schema["properties"]["workflow"]["items"]
    names = [workflow["properties"]["name"]] + [
        case["then"]["properties"]["name"] for case in workflow["allOf"]
    ]
    assert len(names) == 8
    assert all(n == {"type": "string", "maxLength": 100} for n in names)


@pytest.mark.parametrize("phase", ["needs", "capacity", "count"])
@pytest.mark.parametrize(
    "label",
    [
        None,
        "custom.label",
        "workers",
        "Ext.ghost",
        "workflow.bad.ghost",
        "step bad.ghost",
    ],
)
def test_preparation_only_uses_the_refusing_readers_field(phase, label):
    @dataclass
    class Ext(WorkflowStep):
        value: object = 3

        def refuse(self, where):
            if phase != where:
                return
            if label is None:
                if self.value != "ok":
                    raise ValueError("plain reason")
            else:
                text(self.value, label)

        def needs(self):
            self.refuse("needs")
            return StepNeeds(
                numerical=True,
                capacity=self.capacity if phase == "capacity" else None,
                counts=self.count if phase == "count" else None,
            )

        def capacity(self, prepared):
            self.refuse("capacity")
            return CapacityQuery(Selector("^A$"), Selector("^B$"))

        def count(self, prepared):
            from ngraph.analysis.counts import TunnelCountQuery
            from ngraph.results import ResolvedDemandSet

            self.refuse("count")
            return TunnelCountQuery(ResolvedDemandSet("d", (), (), ()), (1,), 1, 1)

        def run(self, context):
            return StepOutput({}, None)

    network = Scenario.from_yaml(
        yaml.safe_dump({"network": NET, "workflow": []})
    ).network
    with pytest.raises(ValueError) as error:
        prepare(Scenario(network, [Ext(name="bad")]))
    own = label is not None and label not in {"custom.label", "workers"}
    reason = (
        "plain reason"
        if label is None
        else ("" if own else label + ": ") + "expected text, got 3"
    )
    assert (
        str(error.value)
        == "workflow[0] (name 'bad')" + (".ghost" if own else "") + ": " + reason
    )
    assert error.value.__cause__ is not None
    prepare(Scenario(network, [Ext(name="bad", value="ok")]))


@pytest.mark.parametrize(
    "field, bad, reason, suffix",
    [
        ("counts", (0,), "expected an integer in [1, 10000], got 0", ""),
        ("up_to", 0, "expected an integer in [1, 10000], got 0", " = 0"),
        ("export_details", "yes", "expected bool, got 'yes'", " = 'yes'"),
        ("workers", 0, "integer outside [1, inf), got 0", " = 0"),
        ("counts", (), "give at least one count or up_to, got ()", ""),
        ("counts", 3, "expected a sequence of integers, got 3", " = 3"),
        ("outputs", 3, "expected native OutputOptions, got 3", " = 3"),
        ("offer", -1, "expected a finite nonnegative amount, got -1", " = -1"),
    ],
)
def test_count_query_owns_the_field_it_refuses(field, bad, reason, suffix):
    step = TunnelCountAnalysis(
        name="bad", demand_set="d", counts=(1,), offer=1, design_demand=1
    )
    doc = {
        "network": NET,
        "demands": {
            "d": [
                {
                    "source": "^A$",
                    "target": "^B$",
                    "volume": 0,
                    "preset": "TE_ECMP_16_LSP",
                }
            ]
        },
        "workflow": [],
    }
    scenario = Scenario.from_yaml(yaml.safe_dump(doc))
    scenario = Scenario(scenario.network, [step], demand_sets=scenario.demand_sets)
    prepare(scenario)
    object.__setattr__(step, field, bad)
    with pytest.raises((ValueError, TypeError)) as error:
        prepare(scenario)
    assert (
        str(error.value)
        == f"workflow[0] (name 'bad').{field + '[0]' if field == 'counts' and bad == (0,) else field}{suffix}: {reason}"
    )


@pytest.mark.parametrize("resolution", [1, "auto"])
def test_distributed_minimum_names_the_declared_field(resolution):
    doc = {
        "network": NET,
        "units": {"resolution": resolution},
        "workflow": [
            {
                "type": "MaxFlow",
                "name": "bad",
                "source": "^A$",
                "target": "^B$",
                "offer": 1,
                "design_demand": 1,
                "model": {
                    "routing": {
                        "type": "distributed_te",
                        "tunnel_count": {"per_head": 1},
                        "min_unreserved_bandwidth": 1e40,
                    }
                },
            }
        ],
    }
    with pytest.raises(ValueError) as error:
        prepare(Scenario.from_yaml(yaml.safe_dump(doc)))
    assert str(error.value) == (
        "workflow[0] (name 'bad').model.routing.min_unreserved_bandwidth = 1e+40: "
        "no legal resolution represents the complete prepared input/augmented graph"
    )
    doc["workflow"][0]["model"]["routing"]["min_unreserved_bandwidth"] = 1
    prepared = prepare(Scenario.from_yaml(yaml.safe_dump(doc)))
    assert prepared._inputs["workflow.bad.min_unreserved"] == ("min_unreserved", 1.0)


def test_reason_resolver_has_no_call_site_field_or_dead_reason_fallback():
    assert tuple(inspect.signature(error_context).parameters) == (
        "exc",
        "labels",
        "fields",
    )


@pytest.mark.parametrize("filename", ["docs/reference/workflow.md", "CHANGELOG.md"])
def test_published_name_limit_matches_acceptance(filename):
    from tests.docs.pages import stated

    (shown,) = stated(filename, r"(\d+) characters")
    limit = int(shown)
    assert limit == 100
    BuildGraph(name="x" * limit)
    with pytest.raises(ValueError) as error:
        BuildGraph(name="x" * (limit + 1))
    assert (
        str(error.value)
        == f"workflow step name: expected a name of at most {limit} characters, got {limit + 1}"
    )


@pytest.mark.parametrize("exception_base", [ValueError, TypeError])
def test_count_preparation_does_not_replace_exception_subclasses(
    monkeypatch, exception_base
):
    class OwnError(exception_base):
        pass

    step = TunnelCountAnalysis(
        name="bad", demand_set="d", counts=(1,), offer=1, design_demand=1
    )
    error = OwnError("own reason")

    def refuse(self, demands):
        raise error

    monkeypatch.setattr(TunnelCountAnalysis, "query_for", refuse)
    with pytest.raises(OwnError) as caught:
        step.query(type("Prepared", (), {"demand_sets": {"d": None}})())
    assert caught.value is error
    assert caught.value.__cause__ is None
    assert str(caught.value) == "own reason"


@pytest.mark.parametrize(
    "kind",
    [
        "BuildGraph",
        "CostPower",
        "MaxFlow",
        "MaximumSupportedDemand",
        "NetworkStats",
        "TrafficMatrixPlacement",
        "TunnelCountAnalysis",
    ],
)
def test_every_builtin_checks_its_name_before_invalid_other_fields(kind):
    import ngraph.workflow as workflow

    cls = getattr(workflow, kind)
    with pytest.raises(ValueError) as caught:
        cls(name="x" * 101, seed="wrong")
    assert (
        str(caught.value)
        == "workflow step name: expected a name of at most 100 characters, got 101"
    )


def test_parser_refuses_a_long_blank_name_before_naming_the_step():
    entry = {"type": "BuildGraph", "name": " " * 101}
    with pytest.raises(ValueError) as caught:
        build_workflow_steps([entry], lambda name: None)
    raw = repr(entry["name"])[:57] + "..."
    assert (
        str(caught.value)
        == f"workflow[0] (name {raw}).name = {raw}: expected a name of at most 100 characters, got 101"
    )
    assert (
        build_workflow_steps(
            [{"type": "BuildGraph", "name": " " * 100}], lambda name: None
        )[0].name
        == "BuildGraph_0"
    )


def test_count_query_keeps_the_refusing_reader_as_its_cause(monkeypatch):
    from ngraph.utils.values import _located_error

    original = _located_error(
        TypeError("tunnel_counts.outputs: expected native OutputOptions, got 3"),
        "tunnel_counts.outputs",
        3,
    )
    step = TunnelCountAnalysis(
        name="bad", demand_set="d", counts=(1,), offer=1, design_demand=1
    )

    def refuse(self, demands):
        raise original

    monkeypatch.setattr(TunnelCountAnalysis, "query_for", refuse)
    with pytest.raises(TypeError) as caught:
        step.query(type("Prepared", (), {"demand_sets": {"d": None}})())
    assert caught.value is not original
    assert caught.value.__cause__ is original
    assert (
        str(caught.value)
        == "tunnel_counts.outputs: expected native OutputOptions, got 3"
    )
    assert caught.value._input_label == "TunnelCountAnalysis.outputs"
    assert caught.value._input_reason == "expected native OutputOptions, got 3"


def test_a_custom_input_called_min_unreserved_keeps_its_own_path():
    @dataclass
    class CustomMinimum(WorkflowStep):
        min_unreserved: float = 1e40

        def needs(self):
            return StepNeeds(
                numerical=True,
                inputs={"min_unreserved": ("min_unreserved", self.min_unreserved)},
            )

        def run(self, context):
            return StepOutput({}, None)

    with pytest.raises(ValueError) as error:
        prepare(Scenario(Network(), [CustomMinimum(name="custom")]))
    assert str(error.value) == (
        "workflow[0] (name 'custom').min_unreserved = 1e+40: "
        "no legal resolution represents the complete prepared input/augmented graph"
    )
    prepare(Scenario(Network(), [CustomMinimum(name="custom", min_unreserved=1)]))
