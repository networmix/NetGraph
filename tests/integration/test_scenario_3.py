"""Nested Clos expansion, physical rules and native shortest-path capacity."""

import netgraph_core as ngc
import pytest

from ngraph.results import BuildGraphResult, CapacityAnalysis
from ngraph.scenario import prepare, run
from tests.question import asked

from .expectations import SCENARIO_3_EXPECTATIONS
from .helpers import create_scenario_helper, load_scenario_from_file


@pytest.mark.slow
class TestScenario3:
    @pytest.fixture(scope="class")
    @classmethod
    def scenario_3(cls):
        return load_scenario_from_file("scenario_3.yaml")

    @pytest.fixture(scope="class")
    @classmethod
    def scenario_3_executed(cls, scenario_3):
        return run(prepare(scenario_3))

    @pytest.fixture(scope="class")
    @classmethod
    def helper(cls, scenario_3, scenario_3_executed):
        return create_scenario_helper(scenario_3, scenario_3_executed)

    def test_scenario_parsing_and_execution(self, scenario_3_executed):
        result = scenario_3_executed.steps[0].result
        assert isinstance(result, BuildGraphResult)
        assert result.node_count == 64 and result.link_count == 288

    def test_network_structure_validation(self, helper):
        helper.validate_network_structure(SCENARIO_3_EXPECTATIONS)

    def test_nested_blueprint_structure(self, helper):
        assert [
            sum(name.startswith(prefix) for name in helper.network.nodes)
            for prefix in ("my_clos1/", "my_clos2/")
        ] == [32, 32]

    def test_3tier_clos_blueprint_structure(self, helper):
        assert [
            sum(name.startswith(prefix) for name in helper.network.nodes)
            for prefix in ("my_clos1/b1/t1/", "my_clos1/b1/t2/", "my_clos1/spine/")
        ] == [4, 4, 16]

    def test_one_to_one_link_pattern(self, helper):
        links = helper.network.find_links(
            source_regex=r"my_clos1/b1/t2/.*", target_regex=r"my_clos1/spine/.*"
        )
        assert len(links) == 16
        assert len({link.source for link in links}) == 4
        assert all(
            sum(link.source == source for link in links) == 4
            for source in {link.source for link in links}
        )
        inter = helper.network.find_links(
            source_regex=r"my_clos1/spine/.*", target_regex=r"my_clos2/spine/.*"
        )
        assert (
            len(inter) == 16
            and len({link.source for link in inter})
            == len({link.target for link in inter})
            == 16
        )

    def test_mesh_pattern_in_nested_blueprints(self, helper):
        links = helper.network.find_links(
            source_regex=r"my_clos1/b1/t1/.*", target_regex=r"my_clos1/b1/t2/.*"
        )
        assert len(links) == len({(link.source, link.target) for link in links}) == 16

    def test_node_rules_application(self, helper):
        helper.validate_node_attributes(
            "my_clos1/b1/t1/t1-1",
            {"risk_groups": {"PowerZone_Clos1_B1_PZA"}, "hw_component": "LeafHW-A"},
        )
        helper.validate_node_attributes(
            "my_clos2/b2/t1/t1-1",
            {"risk_groups": {"PowerZone_Clos2_B2_PZA"}, "hw_component": "LeafHW-B"},
        )
        helper.validate_node_attributes(
            "my_clos1/spine/t3-1",
            {"risk_groups": {"Room_Clos1_Spine"}, "hw_component": "SpineHW"},
        )

    def test_link_rules_application(self, helper):
        links = helper.network.find_links(
            source_regex=r"my_clos1/spine/t3-1$", target_regex=r"my_clos2/spine/t3-1$"
        )
        assert len(links) == 1 and links[0].capacity == 200
        helper.validate_link_attributes(
            r"my_clos1/spine/t3-2$",
            r"my_clos2/spine/t3-2$",
            {"risk_groups": {"Conduit_InterClos_C1"}},
        )

    def test_link_capacity_configuration(self, helper):
        internal = helper.network.find_links(
            source_regex=r"my_clos1/b1/t1/.*", target_regex=r"my_clos1/b1/t2/.*"
        )
        assert len(internal) == 16 and all(link.capacity == 100 for link in internal)
        regular = helper.network.find_links(
            source_regex=r"my_clos1/spine/t3-2$", target_regex=r"my_clos2/spine/t3-2$"
        )
        assert len(regular) == 1 and regular[0].capacity == 400

    def test_no_traffic_demands(self, helper):
        helper.validate_traffic_demands(expected_count=0)
        assert not helper.scenario.demand_sets

    def test_no_failure_policy(self, helper):
        helper.validate_failure_policy(expected_rules=0)
        assert not helper.scenario.failure_policies

    def test_optimized_shortest_results(self, helper):
        values = {step.name: step.result for step in helper.result.steps}
        expected = ngc.to_units(3200, helper.result.topology.q)
        for name in ("capacity_analysis_forward", "capacity_analysis_reverse"):
            value = values[name]
            assert isinstance(value, CapacityAnalysis)
            assert asked(value)["model"]["routing"] == "shortest_paths"
            assert asked(value)["model"]["allocation"] == "optimized"
            assert len(value.cases) == 1 and set(value.cases[0].states) == {"converged"}
            assert (
                value.cases[0].states["converged"].rows[0].result.delivered == expected
            )

    def test_equal_shortest_results(self, helper):
        values = {step.name: step.result for step in helper.result.steps}
        expected = ngc.to_units(3200, helper.result.topology.q)
        for name in (
            "capacity_analysis_forward_balanced",
            "capacity_analysis_reverse_balanced",
        ):
            value = values[name]
            assert asked(value)["model"]["allocation"] == "equal"
            assert (
                value.cases[0].states["converged"].rows[0].result.delivered == expected
            )

    def test_capacity_totals_are_consistent(self, helper):
        # Eight t1 nodes each have four capacity-100 uplinks: their cut is3200.
        # Equal splitting through the regular fabric attains that bound; the
        # capacity-200 inter-fabric exception can still carry its two100 shares.
        topology = helper.result.topology
        source_cut = sum(
            link.capacity
            for link in helper.network.links.values()
            if link.source.startswith("my_clos1/") and "/t1/" in link.source
        )
        assert source_cut == 3200
        inter_cut = sum(
            link.capacity
            for link in helper.network.links.values()
            if link.source.startswith("my_clos1/")
            != link.target.startswith("my_clos1/")
        )
        assert inter_cut >= source_cut
        expected = ngc.to_units(source_cut, topology.q)
        for step in helper.result.steps[1:]:
            (row,) = step.result.cases[0].states["converged"].rows
            assert row.result.delivered == expected
            assert sum(source.delivered for source in row.result.by_source) == expected

    def test_topology_semantic_correctness(self, helper):
        helper.validate_topology_semantics()

    def test_inter_clos_connectivity(self, helper):
        links = helper.network.find_links(
            source_regex=r"my_clos1/.*", target_regex=r"my_clos2/.*"
        )
        assert len(links) == 16
        assert all(
            "/spine/" in link.source and "/spine/" in link.target for link in links
        )

    def test_regex_pattern_matching_in_rules(self, helper):
        nodes = [
            node
            for name, node in helper.network.nodes.items()
            if name.startswith("my_clos1/spine/t3-")
        ]
        assert len(nodes) == 16 and all(
            node.risk_groups == {"Room_Clos1_Spine"} for node in nodes
        )

    def test_workflow_step_execution_order(self, scenario_3_executed):
        assert [step.name for step in scenario_3_executed.steps] == [
            "build_graph",
            "capacity_analysis_forward",
            "capacity_analysis_reverse",
            "capacity_analysis_forward_balanced",
            "capacity_analysis_reverse_balanced",
        ]
        assert [step.execution_order for step in scenario_3_executed.steps] == list(
            range(5)
        )
        assert isinstance(scenario_3_executed.steps[0].result, BuildGraphResult)
        assert all(
            isinstance(step.result, CapacityAnalysis)
            for step in scenario_3_executed.steps[1:]
        )
