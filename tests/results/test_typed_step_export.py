"""Actual typed steps, exact-type custom exporters and one JSON projection."""

import json
from dataclasses import dataclass, replace
from io import StringIO
from types import MappingProxyType

import netgraph_core as ngc
import pytest

from ngraph.analysis.units import UnitsSettings
from ngraph.export import register_result_exporter, write_json
from ngraph.model.components import Component, ComponentsLibrary
from ngraph.model.network import Link, Network, Node
from ngraph.results import StepContext, StepOutput
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.base import WorkflowStep
from ngraph.workflow.build_graph import BuildGraph
from ngraph.workflow.cost_power import CostPower
from ngraph.workflow.max_flow_step import MaxFlow
from ngraph.workflow.network_stats import NetworkStats


def network():
    model = Network()
    model.add_node(
        Node("dc/a", attrs={"label": ["owned"], "hardware": {"component": "platform"}})
    )
    model.add_node(Node("dc/b", attrs={"hardware": {"component": "platform"}}))
    model.add_link(
        Link(
            "dc/a",
            "dc/b",
            10,
            3,
            attrs={
                "hardware": {
                    "source": {"component": "optic"},
                    "target": {"component": "optic"},
                }
            },
        )
    )
    return model


def test_domain_steps_typed_values_and_exact_json_preserve_their_behavior():
    model = network()
    library = ComponentsLibrary(
        {
            "platform": Component("platform", capex=100, power_watts=10),
            "optic": Component("optic", capex=1.5, power_watts=0.5),
        }
    )
    prepared = prepare(
        Scenario(
            model,
            [
                BuildGraph(name="graph"),
                NetworkStats(name="stats"),
                CostPower(name="cost", aggregation_level=2),
            ],
            components_library=library,
            seed=42,
        )
    )
    with pytest.raises(TypeError, match="read-only"):
        model.nodes["dc/a"].attrs["label"].append("changed")
    result = run(prepared)
    graph, stats, cost = [step.result for step in result.steps]
    assert graph.node_count == 2 and graph.link_count == 2 and graph.add_reverse
    assert graph.graph["directed"] and graph.graph["multigraph"]
    assert graph.graph["nodes"][0]["label"] == ["owned"]
    assert stats.node_count == 2 and stats.link_count == 1
    assert (
        stats.total_capacity
        == stats.mean_capacity
        == stats.median_capacity
        == stats.min_capacity
        == stats.max_capacity
        == 10
    )
    assert stats.mean_cost == stats.median_cost == stats.min_cost == stats.max_cost == 3
    assert (
        stats.mean_degree
        == stats.median_degree
        == stats.min_degree
        == stats.max_degree
        == 1
    )
    assert list(cost.levels) == [0, 1, 2]
    (root,) = cost.levels[0]
    assert (
        root.platform_capex,
        root.platform_power_watts,
        root.optics_capex,
        root.optics_power_watts,
        root.capex_total,
        root.power_total_watts,
    ) == (200, 20, 3, 1, 203, 21)
    output = StringIO()
    write_json(result, output)
    wire = json.loads(output.getvalue())
    assert set(wire) == {"metadata", "units_report", "steps"}
    assert wire["metadata"]["seed"] == 42
    assert [step["execution_order"] for step in wire["steps"]] == [0, 1, 2]
    assert wire["steps"][0]["question"] == {
        "kind": "build_graph",
        "parameters": {"add_reverse": True},
    }
    assert wire["steps"][1]["question"] == {
        "kind": "network_stats",
        "parameters": {
            "include_disabled": False,
            "excluded_nodes": [],
            "excluded_links": [],
        },
    }
    assert wire["steps"][2]["question"] == {
        "kind": "cost_power",
        "parameters": {"include_disabled": False, "aggregation_level": 2},
    }
    assert [row["level"] for row in wire["steps"][2]["result"]["levels"]] == [0, 1, 2]
    assert wire["steps"][2]["result"]["levels"][0]["rows"][0]["capex_total"] == 203
    assert "results" not in vars(prepared.scenario)


def test_registered_custom_result_is_published_as_itself_and_encoded_once():
    @dataclass(frozen=True)
    class Value:
        numbers: tuple[int, ...]

    calls = []

    def encode(value, context):
        calls.append(value)
        assert context.topology.graph.num_nodes() == 0
        return {"numbers": list(value.numbers)}

    register_result_exporter(Value, encode)
    original = Value((1, 2))

    class Step(WorkflowStep):
        def run(self, context: StepContext) -> StepOutput:
            assert isinstance(context.prior_results, MappingProxyType)
            return StepOutput({"operation": "numbers"}, original)

    result = run(prepare(Scenario(Network(), [Step()])))
    # Its own type decides its immutability; publication neither copies it
    # nor runs its encoder.
    assert result.steps[0].result is original
    assert calls == []
    with pytest.raises(ValueError, match="Value"):
        register_result_exporter(Value, encode)
    output = StringIO()
    write_json(result, output)
    assert len(calls) == 1
    assert json.loads(output.getvalue())["steps"][0]["result"] == {"numbers": [1, 2]}


def test_unknown_result_does_not_discover_to_dict_and_has_registered_control():
    class Value:
        def to_dict(self):
            pytest.fail("serializer discovered an arbitrary method")

    class Step(WorkflowStep):
        def run(self, context):
            return StepOutput({}, Value())

    prepared = prepare(Scenario(Network(), [Step()]))
    with pytest.raises(TypeError, match="unregistered result type Value"):
        run(prepared)
    register_result_exporter(Value, lambda value, context: {"registered": True})
    output = StringIO()
    write_json(run(prepared), output)
    assert json.loads(output.getvalue())["steps"][0]["result"] == {"registered": True}


@pytest.mark.parametrize(
    "question",
    [object(), ("custom",), MaxFlow(name="numeric"), "custom"],
    ids=["object", "tuple", "numeric-step", "text"],
)
def test_a_question_is_a_query_a_domain_step_or_json_parameters(question):
    class Step(WorkflowStep):
        def run(self, context):
            return StepOutput(question, {})

    with pytest.raises(TypeError, match="workflow question: unsupported type"):
        run(prepare(Scenario(Network(), [Step()])))
    assert (
        run(prepare(Scenario(Network(), [BuildGraph()]))).steps[0].result.kind
        == "build_graph"
    )


def test_encoder_error_writes_no_partial_json_and_retry_succeeds():
    class Value:
        pass

    fail = [True]

    def encode(value, context):
        if fail[0]:
            raise RuntimeError("publication failure")
        return {"complete": True}

    register_result_exporter(Value, encode)

    class Step(WorkflowStep):
        def run(self, context):
            return StepOutput({}, Value())

    result = run(prepare(Scenario(Network(), [Step()])))
    destination = StringIO("original")
    destination.seek(0, 2)
    with pytest.raises(RuntimeError, match="publication failure"):
        write_json(result, destination)
    assert destination.getvalue() == "original"
    fail[0] = False
    output = StringIO()
    write_json(result, output)
    assert json.loads(output.getvalue())["steps"][0]["result"] == {"complete": True}


def test_unknown_question_is_refused_without_reading_arbitrary_attributes():
    class Unknown:
        @property
        def parameters(self):
            pytest.fail("read unknown question attributes")

    result = run(prepare(Scenario(Network(), [BuildGraph()])))
    forged = replace(result, steps=(replace(result.steps[0], question=Unknown()),))
    destination = StringIO("original")
    destination.seek(0, 2)
    with pytest.raises(TypeError, match="unsupported step question Unknown"):
        write_json(forged, destination)
    assert destination.getvalue() == "original"
    output = StringIO()
    write_json(result, output)
    assert json.loads(output.getvalue())["steps"][0]["question"] == {
        "kind": "build_graph",
        "parameters": {"add_reverse": True},
    }


def test_build_graph_nested_output_does_not_borrow_prepared_network():
    network = Network()
    network.add_node(Node("a", attrs={"labels": ["owned"]}))
    network.add_node(Node("t"))
    network.add_link(Link("a", "t", 4, 3, attrs={"nested": {"tag": "original"}}))
    prepared = prepare(
        Scenario(network, workflow=[BuildGraph()], units=UnitsSettings(1))
    )
    first = run(prepared).steps[0].result
    for edit in (
        lambda: first.graph["nodes"][0]["labels"].append("changed output"),
        lambda: first.graph["edges"][0]["nested"].__setitem__("tag", "changed"),
        lambda: first.graph["nodes"].clear(),
    ):
        with pytest.raises(TypeError, match="read-only"):
            edit()
    assert prepared.scenario.network.nodes["a"].attrs["labels"] == ["owned"]
    assert prepared.scenario.network.links["a|t|0"].attrs["nested"] == {
        "tag": "original"
    }
    later = run(prepared).steps[0].result
    assert later.graph["nodes"][0]["labels"] == ["owned"]
    assert later.graph["edges"][0]["nested"]["tag"] == "original"


@dataclass
class Count(WorkflowStep):
    def run(self, context):
        nodes = len(context.prepared.scenario.network.nodes)
        return StepOutput({"limit": [1]}, {"nodes": [nodes]})


@dataclass
class Rewrite(WorkflowStep):
    def run(self, context):
        for edit in (
            lambda: context.prior_results["count"].result["nodes"].append(999),
            lambda: context.prior_results["count"].question["limit"].append(9),
            lambda: context.prior_results["graph"].result.graph["nodes"].clear(),
        ):
            with pytest.raises(TypeError, match="read-only"):
                edit()
        return StepOutput({}, {"done": True})


def exported(scenario):
    output = StringIO()
    write_json(run(prepare(scenario)), output)
    return {step["name"]: step for step in json.loads(output.getvalue())["steps"]}


def test_a_later_step_cannot_rewrite_an_earlier_published_result():
    network = Network(nodes={name: Node(name) for name in ("a", "b")})
    network.add_link(Link("a", "b", 1, 1))
    steps = (Count(name="count"), BuildGraph(name="graph"))
    alone = exported(Scenario(network, steps))
    after = exported(Scenario(network, (*steps, Rewrite(name="rewrite"))))
    assert after["count"] == alone["count"]
    assert after["count"]["result"] == {"nodes": [2]}
    assert after["graph"] == alone["graph"]
    assert len(after["graph"]["result"]["graph"]["nodes"]) == 2


def test_a_custom_question_is_checked_and_frozen_at_publication():
    params = {"limit": [1]}

    class Asks(WorkflowStep):
        def run(self, context):
            return StepOutput(params, {"ok": True})

    result = run(prepare(Scenario(Network(), [Asks(name="asks")])))
    params["limit"].append(99)
    output = StringIO()
    write_json(result, output)
    assert json.loads(output.getvalue())["steps"][0]["question"] == {
        "kind": "custom",
        "parameters": {"limit": [1]},
    }

    class Bad(WorkflowStep):
        def run(self, context):
            return StepOutput({"nodes": {"a", "b"}}, {"ok": True})

    with pytest.raises(ValueError, match="expected finite JSON data, got set"):
        run(prepare(Scenario(Network(), [Bad(name="bad")])))


def test_a_registered_result_holding_a_native_core_value_publishes():
    @dataclass(frozen=True)
    class NativeFlow:
        result: ngc.PlacementResult

    register_result_exporter(
        NativeFlow, lambda value, context: {"delivered": value.result.delivered}
    )

    class DirectCore(WorkflowStep):
        def run(self, context):
            topology = context.prepared.topology
            a, b = topology.node_id_by_name["a"], topology.node_id_by_name["b"]
            routing = ngc.CentralizedTE(
                source_allocation=ngc.SourceAllocation.OPTIMIZED
            )
            options = ngc.EvaluationOptions(
                ngc.FlowPolicyConfig(routing=routing), eligibility=topology.disabled
            )
            native = ngc.evaluate_demand(topology.graph, [a], [b], options)
            return StepOutput({}, NativeFlow(native))

    network = Network(nodes={name: Node(name) for name in ("a", "b")})
    network.add_link(Link("a", "b", 4, 1))
    prepared = prepare(
        Scenario(network, (DirectCore(name="direct"),), units=UnitsSettings(1))
    )
    result = run(prepared)
    assert type(result.steps[0].result.result) is ngc.PlacementResult
    output = StringIO()
    write_json(result, output)
    assert json.loads(output.getvalue())["steps"][0]["result"] == {"delivered": 4}


def test_a_read_only_record_collection_is_not_a_json_result_or_question():
    later = []

    class PublishesNodes(WorkflowStep):
        def run(self, context):
            return StepOutput({}, context.prepared.scenario.network.nodes)

    class AsksNodes(WorkflowStep):
        def run(self, context):
            return StepOutput(context.prepared.scenario.network.nodes, {})

    class Later(WorkflowStep):
        def run(self, context):
            later.append("ran")
            return StepOutput({}, {"complete": True})

    network = Network(nodes={"s": Node("s")})
    for first, message in (
        (PublishesNodes(name="nodes"), r"^unregistered result type _FrozenDict$"),
        (AsksNodes(name="nodes"), "expected finite JSON data, got .*Node$"),
    ):
        prepared = prepare(Scenario(network, (first, Later(name="later"))))
        with pytest.raises((TypeError, ValueError), match=message):
            run(prepared)
        assert later == []
    # Read-only JSON is still shared as it is, and a record's attrs refuse records.
    attrs = Node("a", attrs={"x": [1]}).attrs
    assert Node("b", attrs=attrs).attrs is attrs
    with pytest.raises(ValueError, match="expected finite JSON data"):
        Node("c", attrs=prepare(Scenario(network)).scenario.network.nodes)
