"""Demands pinned to explicit routes (MPLS-style LSPs).

Covers the property that distinguishes a pinned route from ordinary routing:
a route broken by a failure carries nothing instead of rerouting.
"""

from __future__ import annotations

import netgraph_core
import pytest

from ngraph.analysis import analyze
from ngraph.analysis.demand import expand_demands
from ngraph.analysis.placement import place_demands
from ngraph.analysis.static_paths import build_static_path_bundles
from ngraph.model.demand.spec import StaticPath, TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.model.network import Link, Network, Node

SHORT = StaticPath(nodes=("A", "B", "C"))
LONG = StaticPath(nodes=("A", "D", "C"))


def _network() -> Network:
    """A->B->C carries 6 at cost 1/hop; A->D->C carries 4 at cost 9/hop."""
    net = Network()
    for name in ("A", "B", "D", "C"):
        net.add_node(Node(name))
    net.add_link(Link("A", "B", capacity=6.0, cost=1))
    net.add_link(Link("B", "C", capacity=6.0, cost=1))
    net.add_link(Link("A", "D", capacity=4.0, cost=9))
    net.add_link(Link("D", "C", capacity=4.0, cost=9))
    return net


def _place(
    paths,
    *,
    excluded_links=None,
    volume: float = 10.0,
    preset: FlowPolicyPreset = FlowPolicyPreset.SHORTEST_PATHS_WCMP,
    net: Network | None = None,
):
    net = net or _network()
    demand = TrafficDemand(
        source="^A$",
        target="^C$",
        volume=volume,
        mode="pairwise",
        flow_policy=preset,
        static_paths=tuple(paths),
        id="d",
    )
    expansion = expand_demands(net, [demand])
    ctx = analyze(net)
    flow_graph = netgraph_core.FlowGraph(ctx.multidigraph)
    return place_demands(
        expansion.demands,
        [d.volume for d in expansion.demands],
        flow_graph,
        ctx,
        ctx.build_node_mask(None),
        ctx.build_edge_mask(excluded_links),
        collect_entries=True,
        include_used_edges=True,
    )


class TestPlacement:
    def test_uses_every_pinned_route(self):
        result = _place([SHORT, LONG])
        assert result.summary.total_placed == pytest.approx(10.0)
        assert result.entries[0].used_edges == {
            "A|B|0:fwd",
            "B|C|0:fwd",
            "A|D|0:fwd",
            "D|C|0:fwd",
        }

    def test_pins_traffic_off_the_cheapest_route(self):
        """Ordinary routing would send everything down the cost-2 path."""
        result = _place([LONG])
        assert result.summary.total_placed == pytest.approx(4.0)
        assert result.entries[0].used_edges == {"A|D|0:fwd", "D|C|0:fwd"}

    def test_broken_route_carries_nothing_and_does_not_reroute(self):
        result = _place([SHORT], excluded_links={"B|C|0"})
        assert result.summary.total_placed == pytest.approx(0.0)

    def test_surviving_routes_still_carry_their_share(self):
        result = _place([SHORT, LONG], excluded_links={"B|C|0"})
        assert result.summary.total_placed == pytest.approx(4.0)

    def test_link_form_selects_a_specific_parallel_link(self):
        net = _network()
        net.add_link(Link("A", "B", capacity=1.0, cost=50))  # A|B|1
        cheap = _place([StaticPath(links=("A|B|0", "B|C|0"))], net=net)
        pricey = _place([StaticPath(links=("A|B|1", "B|C|0"))], net=_rebuild(net))
        assert cheap.summary.total_placed == pytest.approx(6.0)
        assert pricey.summary.total_placed == pytest.approx(1.0)

    def test_node_form_prefers_the_cheapest_parallel_link(self):
        net = _network()
        net.add_link(Link("A", "B", capacity=1.0, cost=50))
        result = _place([SHORT], net=net)
        assert result.summary.total_placed == pytest.approx(6.0)


def _rebuild(source: Network) -> Network:
    """Copy a network so each placement starts from clean capacity."""
    net = Network()
    for name in source.nodes:
        net.add_node(Node(name))
    for link in source.links.values():
        net.add_link(
            Link(link.source, link.target, capacity=link.capacity, cost=link.cost)
        )
    return net


class TestResolution:
    def _ctx(self):
        return analyze(_network())

    def test_rejects_non_adjacent_hop(self):
        with pytest.raises(ValueError, match="has no enabled link"):
            build_static_path_bundles(
                self._ctx(), [StaticPath(nodes=("A", "C"))], "A", "C"
            )

    def test_rejects_unknown_node(self):
        with pytest.raises(ValueError, match="unknown node"):
            build_static_path_bundles(
                self._ctx(), [StaticPath(nodes=("A", "B", "Z", "C"))], "A", "C"
            )

    def test_rejects_unknown_link(self):
        with pytest.raises(ValueError, match="unknown link"):
            build_static_path_bundles(
                self._ctx(), [StaticPath(links=("nope",))], "A", "C"
            )

    def test_rejects_link_not_leaving_the_reached_node(self):
        with pytest.raises(ValueError, match="does not leave node"):
            build_static_path_bundles(
                self._ctx(), [StaticPath(links=("B|C|0",))], "A", "C"
            )

    def test_rejects_route_with_wrong_endpoints(self):
        with pytest.raises(ValueError, match="must run from"):
            build_static_path_bundles(
                self._ctx(), [StaticPath(nodes=("A", "B"))], "A", "C"
            )

    def test_rejects_route_revisiting_a_node(self):
        net = _network()
        net.add_link(Link("B", "A", capacity=1.0, cost=1))
        ctx = analyze(net)
        with pytest.raises(ValueError, match="simple path"):
            build_static_path_bundles(
                ctx, [StaticPath(nodes=("A", "B", "A", "B", "C"))], "A", "C"
            )


class TestSpec:
    def test_requires_exactly_one_form(self):
        with pytest.raises(ValueError, match="exactly one"):
            StaticPath()
        with pytest.raises(ValueError, match="exactly one"):
            StaticPath(nodes=("A", "B"), links=("A|B|0",))

    def test_requires_two_nodes(self):
        with pytest.raises(ValueError, match="source and a target"):
            StaticPath(nodes=("A",))

    def test_round_trips_through_to_dict(self):
        demand = TrafficDemand(
            source="^A$",
            target="^C$",
            static_paths=(SHORT, StaticPath(links=("A|B|0",))),
        )
        assert demand.to_dict()["static_paths"] == [
            {"nodes": ["A", "B", "C"]},
            {"links": ["A|B|0"]},
        ]


class TestExpansionConstraints:
    def test_rejects_combine_mode(self):
        net = _network()
        demand = TrafficDemand(
            source="^A$",
            target="^C$",
            volume=1.0,
            mode="combine",
            static_paths=(SHORT,),
            id="d",
        )
        with pytest.raises(ValueError, match="use mode 'pairwise'"):
            expand_demands(net, [demand])

    def test_rejects_selectors_matching_several_pairs(self):
        net = _network()
        net.add_node(Node("A2"))
        net.add_link(Link("A2", "B", capacity=1.0, cost=1))
        demand = TrafficDemand(
            source="^A",
            target="^C$",
            volume=1.0,
            mode="pairwise",
            static_paths=(SHORT,),
            id="d",
        )
        with pytest.raises(ValueError, match="exactly one source and one target"):
            expand_demands(net, [demand])


class TestScenarioYaml:
    """The YAML surface: both spellings, and schema rejection of bad forms."""

    _NETWORK = """
network:
  nodes:
    A: {}
    B: {}
    D: {}
    C: {}
  links:
    - source: A
      target: B
      capacity: 6
      cost: 1
    - source: B
      target: C
      capacity: 6
      cost: 1
    - source: A
      target: D
      capacity: 4
      cost: 9
    - source: D
      target: C
      capacity: 4
      cost: 9
"""

    def _scenario(self, static_paths_block: str) -> str:
        return (
            self._NETWORK
            + """
demands:
  default:
    - source: "^A$"
      target: "^C$"
      volume: 10
      mode: pairwise
      flow_policy: SHORTEST_PATHS_WCMP
      static_paths:
"""
            + static_paths_block
        )

    def test_node_and_link_forms_both_load_and_place(self):
        from ngraph.scenario import Scenario

        scenario = Scenario.from_yaml(
            self._scenario(
                '        - ["A", "B", "C"]\n        - links: ["A|D|0", "D|C|0"]\n'
            )
        )
        demand = scenario.demand_set.get_set("default")[0]
        assert [p.nodes or p.links for p in demand.static_paths] == [
            ("A", "B", "C"),
            ("A|D|0", "D|C|0"),
        ]

    def test_mapping_form_with_nodes_key(self):
        from ngraph.scenario import Scenario

        scenario = Scenario.from_yaml(
            self._scenario('        - nodes: ["A", "B", "C"]\n')
        )
        assert scenario.demand_set.get_set("default")[0].static_paths[0].nodes == (
            "A",
            "B",
            "C",
        )

    def test_schema_rejects_empty_and_malformed_routes(self):
        import jsonschema

        from ngraph.scenario import Scenario

        with pytest.raises(jsonschema.ValidationError):
            Scenario.from_yaml(self._scenario("        []\n"))
        with pytest.raises(jsonschema.ValidationError):
            Scenario.from_yaml(
                self._scenario('        - {nodes: ["A", "B"], links: ["A|B|0"]}\n')
            )
        with pytest.raises(jsonschema.ValidationError):
            Scenario.from_yaml(self._scenario('        - ["A"]\n'))


class TestDisabledLinks:
    """A route must never be pinned to an administratively disabled link."""

    def _network_with_disabled_cheap_link(self) -> Network:
        net = Network()
        for name in ("A", "B", "C"):
            net.add_node(Node(name))
        net.add_link(Link("A", "B", capacity=6.0, cost=1))  # cheapest, disabled
        net.add_link(Link("A", "B", capacity=7.0, cost=2))  # enabled alternative
        net.add_link(Link("B", "C", capacity=100.0, cost=1))
        net.links["A|B|0"].disabled = True
        return net

    def test_node_hop_skips_disabled_link(self):
        result = _place(
            [StaticPath(nodes=("A", "B", "C"))],
            net=self._network_with_disabled_cheap_link(),
        )
        assert result.summary.total_placed == pytest.approx(7.0)
        assert "A|B|1:fwd" in result.entries[0].used_edges

    def test_naming_a_disabled_link_is_an_error(self):
        ctx = analyze(self._network_with_disabled_cheap_link())
        with pytest.raises(ValueError, match="disabled link"):
            build_static_path_bundles(
                ctx, [StaticPath(links=("A|B|0", "B|C|0"))], "A", "C"
            )

    def test_hop_with_only_disabled_links_is_an_error(self):
        net = self._network_with_disabled_cheap_link()
        net.links["A|B|1"].disabled = True
        with pytest.raises(ValueError, match="has no enabled link"):
            build_static_path_bundles(
                analyze(net), [StaticPath(nodes=("A", "B", "C"))], "A", "C"
            )


class TestInputForms:
    """Every route form the DSL accepts must work programmatically too."""

    def test_config_round_trip_accepts_list_and_mapping_forms(self):
        from ngraph.analysis.functions import _static_paths_from_config

        assert _static_paths_from_config([["A", "B", "C"]]) == (
            StaticPath(nodes=("A", "B", "C")),
        )
        assert _static_paths_from_config([{"links": ["A|B|0"]}]) == (
            StaticPath(links=("A|B|0",)),
        )
        assert _static_paths_from_config([StaticPath(nodes=("A", "B"))]) == (
            StaticPath(nodes=("A", "B")),
        )

    @pytest.mark.parametrize(
        "bad",
        [[{"path": ["A", "B"]}], ["not-a-route"], [{"nodes": ["A"], "links": ["x"]}]],
    )
    def test_config_round_trip_rejects_other_shapes(self, bad):
        from ngraph.analysis.functions import _static_paths_from_config

        with pytest.raises(ValueError, match="Invalid static path"):
            _static_paths_from_config(bad)

    def test_traffic_demand_rejects_non_staticpath_entries(self):
        with pytest.raises(ValueError, match="must be StaticPath objects"):
            TrafficDemand(
                source="^A$", target="^B$", static_paths=[{"nodes": ["A", "B"]}]
            )

    def test_yaml_rejects_non_string_hops(self):
        from ngraph.model.demand.builder import _build_static_paths

        with pytest.raises(ValueError, match="must all be strings"):
            _build_static_paths([["A", ["B", "B"], "C"]], "default")


class TestPinnedDemandIsNeverSilentlyDropped:
    def test_selector_matching_nothing_raises(self):
        net = _network()
        demand = TrafficDemand(
            source="^A$",
            target="^NOPE$",
            volume=5.0,
            mode="pairwise",
            static_paths=(SHORT,),
            id="d",
        )
        with pytest.raises(ValueError, match="match no active source or target"):
            expand_demands(net, [demand])


class TestBundleCaching:
    """Bundles are resolved once per context but must still track the masks."""

    def test_repeated_placements_track_changing_failures(self):
        outcomes = []
        for excluded in (None, {"B|C|0"}, None, {"A|D|0"}, {"B|C|0", "A|D|0"}, None):
            outcomes.append(
                round(
                    _place([SHORT, LONG], excluded_links=excluded).summary.total_placed,
                    3,
                )
            )
        assert outcomes == [10.0, 4.0, 10.0, 6.0, 0.0, 10.0]
