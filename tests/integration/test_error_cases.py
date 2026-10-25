"""YAML refusals and degenerate physical topologies through preparation/run."""

import pytest
from yaml.parser import ParserError

from ngraph.results import BuildGraphResult
from ngraph.scenario import Scenario, prepare, run

from .helpers import ScenarioDataBuilder


def _graph(scenario):
    (step,) = run(prepare(scenario)).steps
    assert isinstance(step.result, BuildGraphResult)
    assert step.result.node_count == len(step.result.graph["nodes"])
    assert step.result.edge_count == len(step.result.graph["edges"])
    return step.result.graph


def _builder(nodes=()):
    return (
        ScenarioDataBuilder()
        .with_simple_nodes(list(nodes))
        .with_workflow_step("BuildGraph", "build_graph")
    )


@pytest.mark.slow
class TestMalformedYAML:
    def test_invalid_yaml_syntax(self):
        with pytest.raises(ValueError, match="invalid YAML") as error:
            Scenario.from_yaml("network:\n  nodes:\n    NodeA: {\n")
        assert isinstance(error.value.__cause__, ParserError)
        assert (
            _graph(_builder(("NodeA",)).build_scenario())["nodes"][0]["id"] == "NodeA"
        )

    def test_missing_required_fields(self):
        scenario = ScenarioDataBuilder().build_scenario()
        assert not scenario.network.nodes and not scenario.workflow
        assert run(prepare(scenario)).steps == ()

    def test_invalid_node_definitions(self):
        with pytest.raises(ValueError, match="Additional properties are not allowed"):
            Scenario.from_yaml(
                "network:\n  nodes:\n    NodeA:\n      invalid_field: should_not_exist\n      disabled: not_a_boolean\n"
            )
        assert (
            _graph(_builder(("NodeA",)).build_scenario())["nodes"][0]["disabled"]
            is False
        )

    def test_nonexistent_link_endpoints(self):
        with pytest.raises(
            ValueError, match="target 'NonexistentNode' matches no node"
        ):
            Scenario.from_yaml("""
network:
  nodes: {NodeA: {}}
  links:
    - {source: NodeA, target: NonexistentNode, capacity: 10, cost: 1}
workflow:
  - {type: BuildGraph, name: build_graph}
""")


@pytest.mark.slow
class TestBlueprintErrors:
    def test_nonexistent_blueprint_reference(self):
        with pytest.raises((ValueError, KeyError)):
            Scenario.from_yaml("network:\n  nodes:\n    group: {blueprint: absent}\n")
        scenario = Scenario.from_yaml(
            "blueprints:\n  simple:\n    nodes: {member: {}}\nnetwork:\n  nodes:\n    group: {blueprint: simple}\n"
        )
        assert scenario.network.nodes

    def test_circular_blueprint_references(self):
        builder = _builder()
        builder.with_blueprint("a", {"nodes": {"next": {"blueprint": "b"}}})
        builder.with_blueprint("b", {"nodes": {"next": {"blueprint": "a"}}})
        builder.data["network"] = {"nodes": {"group": {"blueprint": "a"}}}
        with pytest.raises((ValueError, RecursionError)):
            builder.build_scenario()
        builder.data["blueprints"]["b"] = {"nodes": {"last": {}}}
        assert _graph(builder.build_scenario())["nodes"]

    def test_malformed_link_patterns(self):
        builder = _builder(("A", "B"))
        builder.data["network"]["links"] = [
            {"source": "A", "target": "B", "pattern": "invalid_pattern", "capacity": 10}
        ]
        with pytest.raises(ValueError):
            builder.build_scenario()
        builder.data["network"]["links"][0]["pattern"] = "mesh"
        assert len(_graph(builder.build_scenario())["edges"]) == 2


@pytest.mark.slow
class TestWorkflowErrors:
    def test_nonexistent_workflow_step_type(self):
        builder = _builder(("A",))
        builder.with_workflow_step("NonexistentStepType", "invalid_step")
        with pytest.raises((ValueError, KeyError)):
            builder.build_scenario()
        builder.data["workflow"].pop()
        assert len(_graph(builder.build_scenario())["nodes"]) == 1


@pytest.mark.slow
class TestEdgeCases:
    def test_empty_network(self):
        graph = _graph(_builder().build_scenario())
        assert graph["nodes"] == graph["edges"] == []

    def test_single_node_network(self):
        graph = _graph(_builder(("LonelyNode",)).build_scenario())
        assert [node["id"] for node in graph["nodes"]] == ["LonelyNode"]
        assert graph["edges"] == []

    def test_isolated_nodes(self):
        graph = _graph(_builder(("NodeA", "NodeB", "NodeC")).build_scenario())
        assert [node["id"] for node in graph["nodes"]] == ["NodeA", "NodeB", "NodeC"]
        assert graph["edges"] == []

    def test_self_loop_links(self):
        builder = _builder(("NodeA",))
        builder.with_simple_links([("NodeA", "NodeA", 10)])
        scenario = builder.build_scenario()
        assert _graph(scenario)["edges"] == [] and not scenario.network.links

    def test_duplicate_links(self):
        builder = _builder(("NodeA", "NodeB"))
        builder.with_simple_links([("NodeA", "NodeB", 10), ("NodeA", "NodeB", 20)])
        builder.data["network"]["links"][1]["cost"] = 2
        graph = _graph(builder.build_scenario())
        assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 4
        assert [
            (edge["capacity"], edge["cost"])
            for edge in graph["edges"]
            if edge["source"] == "NodeA"
        ] == [(10, 1), (20, 2)]

    def test_zero_capacity_links(self):
        builder = _builder(("NodeA", "NodeB")).with_simple_links(
            [("NodeA", "NodeB", 0)]
        )
        graph = _graph(builder.build_scenario())
        assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 2
        assert all(
            edge["capacity"] == 0 and edge["cost"] == 1 for edge in graph["edges"]
        )

    def test_very_large_network_parameters(self):
        builder = _builder(("NodeA", "NodeB")).with_simple_links(
            [("NodeA", "NodeB", 999999999999)]
        )
        builder.data["network"]["links"][0]["cost"] = 999999999999
        graph = _graph(builder.build_scenario())
        assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 2
        assert all(
            edge["capacity"] == edge["cost"] == 999999999999 for edge in graph["edges"]
        )

    def test_special_characters_in_node_names(self):
        names = ["node-with-dashes", "node_with_underscores", "Node-123_test"]
        graph = _graph(_builder(names).build_scenario())
        assert {node["id"] for node in graph["nodes"]} == set(names)
