"""Explicit routes resolve once on enabled nominal links and replay fixed paths."""

from copy import deepcopy

import netgraph_core as ngc
import pytest
import yaml

from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec, PinnedRoutes, RouteSpec
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import DirectedLink, Link, Network, Node
from ngraph.model.selectors import Condition, Selector
from ngraph.scenario import Scenario, prepare

SHORT = RouteSpec("A", nodes=("A", "B", "C"), weight=3)
LONG = RouteSpec("A", nodes=("A", "D", "C"), weight=2)


def _network():
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C", "D")})
    for source, target, units, cost in (
        ("A", "B", 6, 1),
        ("B", "C", 6, 1),
        ("A", "D", 4, 9),
        ("D", "C", 4, 9),
    ):
        network.add_link(Link(source, target, units, cost))
    return network


def _prepared(
    routes, *, network=None, mode="pairwise", source="^A$", target="^C$", volume=10
):
    declarations = {f"r{index}": route for index, route in enumerate(routes)}
    demands = DemandSet(
        "load",
        (
            DemandSpec(
                Selector(source),
                Selector(target),
                volume,
                PinnedRoutes(tuple(declarations)),
                id="d",
                mode=mode,
            ),
        ),
    )
    return prepare(
        Scenario(
            network or _network(),
            demand_sets={"load": demands},
            routes=declarations,
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    )


def _place(prepared, excluded=()):
    policy = (
        FailurePolicy(
            modes=[
                FailureMode(
                    1, [FailureRule("link", [Condition("id", "in", list(excluded))])]
                )
            ]
        )
        if excluded
        else None
    )
    result = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["load"],
            failures=None if policy is None else FailureRequest(policy, 1, 42),
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=True),
        ),
    )
    return result.cases[-1].states["converged"]


def _flows(prepared, state):
    (row,) = state.rows
    return {
        (ref.link, ref.direction): int(units)
        for ref, units in zip(
            prepared.topology.edge_refs, row.result.edge_flows, strict=True
        )
        if units
    }


class TestPlacement:
    def test_uses_every_pinned_route(self):
        prepared = _prepared((SHORT, LONG))
        state = _place(prepared)
        assert state.totals.delivered_units == 10
        assert _flows(prepared, state) == {
            ("A|B|0", "forward"): 6,
            ("B|C|0", "forward"): 6,
            ("A|D|0", "forward"): 4,
            ("D|C|0", "forward"): 4,
        }

    def test_pins_traffic_off_the_cheapest_route(self):
        prepared = _prepared((LONG,))
        state = _place(prepared)
        assert state.totals.delivered_units == 4
        assert _flows(prepared, state) == {
            ("A|D|0", "forward"): 4,
            ("D|C|0", "forward"): 4,
        }

    def test_broken_route_carries_nothing_and_does_not_reroute(self):
        prepared = _prepared((SHORT,))
        assert _place(prepared, ("B|C|0",)).totals.delivered_units == 0
        assert _place(prepared).totals.delivered_units == 6

    def test_surviving_routes_still_carry_their_share(self):
        prepared = _prepared((SHORT, LONG))
        assert _place(prepared, ("B|C|0",)).totals.delivered_units == 4

    def test_edge_form_selects_a_specific_parallel_link(self):
        network = _network()
        network.add_link(Link("A", "B", 1, 50))
        cheap = _prepared(
            (
                RouteSpec(
                    "A",
                    edges=(
                        DirectedLink("A|B|0", "forward"),
                        DirectedLink("B|C|0", "forward"),
                    ),
                ),
            ),
            network=network,
        )
        pricey = _prepared(
            (
                RouteSpec(
                    "A",
                    edges=(
                        DirectedLink("A|B|1", "forward"),
                        DirectedLink("B|C|0", "forward"),
                    ),
                ),
            ),
            network=network,
        )
        assert _place(cheap).totals.delivered_units == 6
        assert _place(pricey).totals.delivered_units == 1

    def test_node_form_prefers_the_cheapest_parallel_link(self):
        network = _network()
        network.add_link(Link("A", "B", 1, 50))
        prepared = _prepared((SHORT,), network=network)
        assert _flows(prepared, _place(prepared)) == {
            ("A|B|0", "forward"): 6,
            ("B|C|0", "forward"): 6,
        }


class TestResolution:
    def test_rejects_non_adjacent_hop(self):
        with pytest.raises(ValueError, match="no enabled physical hop A->C"):
            _prepared((RouteSpec("A", nodes=("A", "C")),))
        assert _place(_prepared((SHORT,))).totals.delivered_units == 6

    def test_rejects_unknown_node(self):
        with pytest.raises(ValueError, match="unknown node.*Z"):
            _prepared((RouteSpec("A", nodes=("A", "B", "Z", "C")),))
        assert _prepared((SHORT,)).topology.graph.num_nodes() == 4

    def test_rejects_unknown_link(self):
        with pytest.raises(ValueError, match="unknown directed physical link.*nope"):
            _prepared((RouteSpec("A", edges=(DirectedLink("nope", "forward"),)),))
        assert _prepared((SHORT,)).topology.graph.num_edges() == 8

    def test_rejects_edge_not_leaving_the_reached_node(self):
        with pytest.raises(ValueError, match="begin at its declared head"):
            _prepared((RouteSpec("A", edges=(DirectedLink("B|C|0", "forward"),)),))
        assert _prepared((SHORT,)).demand_sets["load"].demands[0].nominal_units == 10

    def test_rejects_route_with_wrong_endpoints(self):
        with pytest.raises(ValueError, match="destination|end"):
            _prepared((RouteSpec("A", nodes=("A", "B")),))
        assert _place(_prepared((SHORT,))).totals.delivered_units == 6

    @pytest.mark.parametrize(
        "nodes", [("A", "B", "A", "B", "C"), ("A", "B", "A", "D", "C")]
    )
    def test_rejects_route_revisiting_a_node(self, nodes):
        with pytest.raises(ValueError, match="duplicate member|node.*repeated"):
            _prepared((RouteSpec("A", nodes=nodes),))
        assert _prepared((SHORT,)).demand_sets["load"].demands


class TestSpec:
    def test_requires_exactly_one_form(self):
        with pytest.raises(ValueError, match="exactly one"):
            RouteSpec("A")
        with pytest.raises(ValueError, match="exactly one"):
            RouteSpec("A", nodes=("A", "B"), edges=(DirectedLink("A|B|0", "forward"),))
        assert RouteSpec("A", nodes=("A", "B")).nodes == ("A", "B")

    def test_requires_two_nodes(self):
        with pytest.raises(ValueError, match="at least two nodes"):
            _prepared((RouteSpec("A", nodes=("A",)),))
        assert _place(_prepared((SHORT,))).totals.delivered_units == 6


class TestEndpointConstraints:
    def test_singleton_combine_and_pairwise_are_supported(self):
        for mode in ("combine", "pairwise"):
            assert _place(_prepared((SHORT,), mode=mode)).totals.delivered_units == 6

    def test_rejects_route_for_another_resolved_pair(self):
        network = _network()
        network.add_node(Node("A2"))
        network.add_link(Link("A2", "B", 1, 1))
        with pytest.raises(ValueError, match="head|source"):
            _prepared((SHORT,), network=network, source="^A", mode="pairwise")
        assert (
            _place(
                _prepared((SHORT,), network=network, source="^A$")
            ).totals.delivered_units
            == 6
        )


def _yaml_data():
    return {
        "units": {"resolution": 1},
        "network": {
            "nodes": {name: {} for name in ("A", "B", "C", "D")},
            "links": [
                {
                    "source": link.source,
                    "target": link.target,
                    "capacity": link.capacity,
                    "cost": link.cost,
                }
                for link in _network().links.values()
            ],
        },
        "routes": {
            "short": {"head": "A", "nodes": ["A", "B", "C"], "weight": 3},
            "long": {
                "head": "A",
                "edges": [
                    {"link": "A|D|0", "direction": "forward"},
                    {"link": "D|C|0", "direction": "forward"},
                ],
                "weight": 2,
            },
        },
        "demands": {
            "load": [
                {
                    "source": "^A$",
                    "target": "^C$",
                    "volume": 10,
                    "model": {
                        "routing": {"type": "pinned", "routes": ["short", "long"]},
                        "admission": "lossless",
                    },
                }
            ]
        },
    }


class TestScenarioYaml:
    def test_node_and_edge_forms_both_load_and_place(self):
        prepared = prepare(
            Scenario.from_yaml(yaml.safe_dump(_yaml_data())), demand_sets=("load",)
        )
        assert _place(prepared).totals.delivered_units == 10
        assert prepared.scenario.routes["short"].nodes == ("A", "B", "C")
        assert prepared.scenario.routes["long"].edges == (
            DirectedLink("A|D|0", "forward"),
            DirectedLink("D|C|0", "forward"),
        )

    def test_mapping_form_with_nodes_key(self):
        data = _yaml_data()
        data["demands"]["load"][0]["model"]["routing"]["routes"] = ["short"]
        prepared = prepare(
            Scenario.from_yaml(yaml.safe_dump(data)), demand_sets=("load",)
        )
        assert _place(prepared).totals.delivered_units == 6

    @pytest.mark.parametrize(
        "route",
        [
            {"head": "A", "nodes": []},
            {"head": "A", "nodes": ["A"]},
            {"head": "A", "nodes": ["A", "B"], "edges": []},
        ],
    )
    def test_schema_rejects_empty_and_malformed_routes(self, route):
        data = _yaml_data()
        data["routes"]["short"] = route
        with pytest.raises(ValueError):
            prepare(Scenario.from_yaml(yaml.safe_dump(data)), demand_sets=("load",))
        assert (
            _place(
                prepare(
                    Scenario.from_yaml(yaml.safe_dump(_yaml_data())),
                    demand_sets=("load",),
                )
            ).totals.delivered_units
            == 10
        )


def _disabled_network():
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    network.add_link(Link("A", "B", 6, 1, disabled=True))
    network.add_link(Link("A", "B", 7, 2))
    network.add_link(Link("B", "C", 100, 1))
    return network


class TestDisabledLinks:
    def test_node_hop_skips_disabled_link(self):
        prepared = _prepared((SHORT,), network=_disabled_network())
        assert _flows(prepared, _place(prepared)) == {
            ("A|B|1", "forward"): 7,
            ("B|C|0", "forward"): 7,
        }

    def test_naming_a_disabled_link_is_an_error(self):
        with pytest.raises(ValueError, match="route.r0: disabled link A\\|B\\|0"):
            _prepared(
                (
                    RouteSpec(
                        "A",
                        edges=(
                            DirectedLink("A|B|0", "forward"),
                            DirectedLink("B|C|0", "forward"),
                        ),
                    ),
                ),
                network=_disabled_network(),
            )
        assert (
            _place(
                _prepared((SHORT,), network=_disabled_network())
            ).totals.delivered_units
            == 7
        )

    def test_hop_with_only_disabled_links_is_an_error(self):
        network = _disabled_network()
        network.disable_link("A|B|1")
        with pytest.raises(ValueError, match="no enabled physical hop A->B"):
            _prepared((SHORT,), network=network)
        network.enable_link("A|B|1")
        assert _place(_prepared((SHORT,), network=network)).totals.delivered_units == 7

    def test_sampled_failure_never_selects_nominal_alternative(self):
        network = _disabled_network()
        network.enable_link("A|B|0")
        prepared = _prepared((SHORT,), network=network)
        assert _place(prepared).totals.delivered_units == 6
        assert _place(prepared, ("A|B|0",)).totals.delivered_units == 0
        assert _place(prepared).totals.delivered_units == 6


class TestTypedHops:
    def test_yaml_rejects_non_string_hops(self):
        data = _yaml_data()
        data["routes"]["short"]["nodes"] = ["A", ["B", "B"], "C"]
        with pytest.raises(ValueError):
            Scenario.from_yaml(yaml.safe_dump(data))
        with pytest.raises(ValueError, match="route.nodes"):
            RouteSpec("A", nodes=("A", ["B"], "C"))
        assert _prepared((SHORT,)).demand_sets["load"].demands


class TestDiscardedRouteShare:
    def test_selector_matching_nothing_preserves_discarded_share(self):
        prepared = _prepared((SHORT,), target="^NOPE$", volume=5)
        value = prepared.demand_sets["load"]
        assert value.demands == ()
        assert (
            value.accounting[0].declared_units
            == value.accounting[0].discarded_units
            == 5
        )
        assert value.accounting[0].discards[0].reason == "empty_selection"


class TestRouteReuse:
    def test_repeated_placements_track_changing_failures(self):
        prepared = _prepared((deepcopy(SHORT), deepcopy(LONG)))
        outcomes = [
            _place(prepared, excluded).totals.delivered_units
            for excluded in ((), ("B|C|0",), (), ("A|D|0",), ("B|C|0", "A|D|0"), ())
        ]
        assert outcomes == [10, 4, 10, 6, 0, 10]
