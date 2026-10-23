"""Typed expansion preserves integer totals and declares every discarded share."""

import pytest

from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Condition, MatchSpec, Selector
from ngraph.scenario import Scenario, prepare


@pytest.fixture
def simple_network():
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C", "D")})
    for source, target in (("A", "B"), ("B", "C"), ("C", "D")):
        network.add_link(Link(source, target, 100, 1))
    return network


def _resolved(network, *demands):
    return prepare(
        Scenario(
            network,
            demand_sets={"load": DemandSet("load", demands)},
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    ).demand_sets["load"]


class TestDemandIdentity:
    def test_explicit_id_preserved(self, simple_network):
        spec = DemandSpec(Selector("^A$"), Selector("^B$"), 100, id="my-stable-id")
        assert spec.id == "my-stable-id"
        resolved = _resolved(simple_network, spec)
        assert resolved.demands[0].base_id == "my-stable-id"
        assert resolved.demands[0].id == "my-stable-id|0"

    def test_absent_id_is_assigned_by_declaration_ordinal(self, simple_network):
        spec = DemandSpec(Selector("^A$"), Selector("^B$"), 100)
        assert spec.id is None
        first, second = (_resolved(simple_network, spec) for _ in range(2))
        assert first.demands[0].base_id == second.demands[0].base_id == "load|0"
        assert first.demands[0].id == second.demands[0].id == "load|0|0"


class TestResolvedPairwise:
    def test_pairwise_single_pair(self, simple_network):
        value = _resolved(
            simple_network,
            DemandSpec(Selector("^A$"), Selector("^D$"), 100, mode="pairwise"),
        )
        (row,) = value.demands
        assert row.endpoints.sources == ("A",) and row.endpoints.destinations == ("D",)
        assert row.nominal_units == 100 and row.pool is None

    def test_pairwise_multiple_sources(self, simple_network):
        value = _resolved(
            simple_network,
            DemandSpec(Selector("^[AB]$"), Selector("^[CD]$"), 100, mode="pairwise"),
        )
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.nominal_units)
            for row in value.demands
        ] == [
            (("A",), ("C",), 25),
            (("A",), ("D",), 25),
            (("B",), ("C",), 25),
            (("B",), ("D",), 25),
        ]

    def test_pairwise_self_shares_are_discarded(self, simple_network):
        # Singleton groups make the diagonal intentional; overlapping multi-node
        # groups are refused before expansion by the common endpoint rule.
        value = _resolved(
            simple_network,
            DemandSpec(
                Selector("^[AB]$", group_by="name"),
                Selector("^[AB]$", group_by="name"),
                100,
                mode="pairwise",
            ),
        )
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.nominal_units)
            for row in value.demands
        ] == [(("A",), ("B",), 25), (("B",), ("A",), 25)]
        (accounting,) = value.accounting
        assert accounting.declared_units == 100 and accounting.resolved_units == 50
        assert accounting.discarded_units == 50
        assert [(share.reason, share.units) for share in accounting.discards] == [
            ("self_pair", 25),
            ("self_pair", 25),
        ]
        with pytest.raises(ValueError, match="overlap"):
            _resolved(
                simple_network,
                DemandSpec(
                    Selector("^[AB]$"), Selector("^[AB]$"), 100, mode="pairwise"
                ),
            )


class TestResolvedEdgeCases:
    def test_empty_demand_set_is_explicit(self, simple_network):
        value = _resolved(simple_network)
        assert value.demands == value.accounting == value.expansion_template == ()

    def test_no_matching_nodes_preserves_discarded_total(self, simple_network):
        value = _resolved(
            simple_network, DemandSpec(Selector("^absent$"), Selector("^D$"), 100)
        )
        assert value.demands == ()
        (accounting,) = value.accounting
        assert accounting.declared_units == accounting.discarded_units == 100
        assert accounting.resolved_units == 0
        assert [(share.reason, share.units) for share in accounting.discards] == [
            ("empty_selection", 100)
        ]

    def test_multiple_demands_mixed_modes(self, simple_network):
        value = _resolved(
            simple_network,
            DemandSpec(Selector("^A$"), Selector("^B$"), 50, mode="pairwise"),
            DemandSpec(Selector("^[CD]$"), Selector("^[AB]$"), 100),
        )
        assert len(value.demands) == 2
        assert [row.nominal_units for row in value.demands] == [50, 100]
        assert value.demands[1].endpoints.sources == ("C", "D")
        assert value.demands[1].endpoints.destinations == ("A", "B")
        assert all(row.pool is None for row in value.demands)


@pytest.fixture
def network_with_attrs():
    network = Network()
    for dc in ("dc1", "dc2"):
        for role in ("leaf", "spine"):
            for index in (1, 2):
                network.add_node(
                    Node(f"{dc}_{role}_{index}", attrs={"dc": dc, "role": role})
                )
    return network


class TestTypedSelectors:
    def test_group_by_selector(self, network_with_attrs):
        # Same grouped populations overlap: the declaration refuses instead of
        # silently trimming them. Disjoint group members are the legal control.
        with pytest.raises(ValueError, match="overlap"):
            _resolved(
                network_with_attrs,
                DemandSpec(
                    Selector(group_by="dc"),
                    Selector(group_by="dc"),
                    100,
                    mode="pairwise",
                ),
            )
        value = _resolved(
            network_with_attrs,
            DemandSpec(
                Selector(".*leaf", group_by="dc"),
                Selector(".*spine", group_by="dc"),
                100,
                mode="pairwise",
            ),
        )
        assert len(value.demands) == 16
        assert sum(row.nominal_units for row in value.demands) == 100

    def test_match_selector_filters_nodes(self, network_with_attrs):
        value = _resolved(
            network_with_attrs,
            DemandSpec(
                Selector(match=MatchSpec([Condition("role", "==", "leaf")])),
                Selector(match=MatchSpec([Condition("role", "==", "spine")])),
                100,
                mode="pairwise",
            ),
        )
        assert len(value.demands) == 16
        assert all(
            "leaf" in row.endpoints.sources[0]
            and "spine" in row.endpoints.destinations[0]
            for row in value.demands
        )

    def test_combined_path_and_match(self, network_with_attrs):
        value = _resolved(
            network_with_attrs,
            DemandSpec(
                Selector("^dc1_", match=MatchSpec([Condition("role", "==", "leaf")])),
                Selector("^dc2_", match=MatchSpec([Condition("role", "==", "spine")])),
                100,
                mode="pairwise",
            ),
        )
        assert len(value.demands) == 4
        assert all(row.nominal_units == 25 for row in value.demands)
        assert all(
            row.endpoints.sources[0].startswith("dc1_leaf")
            and row.endpoints.destinations[0].startswith("dc2_spine")
            for row in value.demands
        )


class TestDemandFieldDefaults:
    def test_default_group_mode(self):
        spec = DemandSpec(Selector("^A$"), Selector("^B$"), 100)
        assert spec.group_mode == "flatten"
        assert spec.mode == "combine" and spec.priority == 0
        assert spec.volume == 100.0 and spec.id is None
