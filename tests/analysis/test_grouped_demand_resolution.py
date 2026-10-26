"""Group expansion retains branch order, shares and explicit overlap refusals."""

import pytest

from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare


def _dc_network():
    network = Network(
        nodes={
            name: Node(name)
            for name in ("dc1/a", "dc1/b", "dc2/a", "dc2/b", "hub1", "hub2")
        }
    )
    for source in ("dc1/a", "dc1/b", "dc2/a", "dc2/b"):
        for target in ("hub1", "hub2"):
            network.add_link(Link(source, target, 10, 1))
    return network


def _prepared(
    network,
    source,
    target,
    *,
    mode="combine",
    group_mode="per_group",
    volume=8,
    policy=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
):
    demands = DemandSet(
        "load",
        (
            DemandSpec(
                Selector(source),
                Selector(target),
                volume,
                policy,
                id="d1",
                mode=mode,
                group_mode=group_mode,
            ),
        ),
    )
    return prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )


class TestPerGroupCombine:
    def test_one_demand_per_source_group(self):
        prepared = _prepared(_dc_network(), "^(dc[0-9]+)/", "^hub")
        value = prepared.demand_sets["load"]
        assert len(value.demands) == 2
        assert [(row.id, row.nominal_units) for row in value.demands] == [
            ("d1|0", 4),
            ("d1|1", 4),
        ]
        assert (
            value.accounting[0].declared_units
            == value.accounting[0].resolved_units
            == 8
        )

    def test_targets_combined_per_source_group(self):
        value = _prepared(_dc_network(), "^(dc[0-9]+)/", "^hub").demand_sets["load"]
        assert [
            (row.endpoints.sources, row.endpoints.destinations) for row in value.demands
        ] == [
            (("dc1/a", "dc1/b"), ("hub1", "hub2")),
            (("dc2/a", "dc2/b"), ("hub1", "hub2")),
        ]
        assert all(row.pool is None for row in value.demands)


class TestPerGroupPairwise:
    def test_pairwise_within_each_group(self):
        with pytest.raises(ValueError, match="overlap"):
            _prepared(_dc_network(), "^(dc[0-9]+)/", "^(dc[0-9]+)/", mode="pairwise")
        value = _prepared(
            _dc_network(), "^(dc[0-9]+)/a$", "^(dc[0-9]+)/b$", mode="pairwise"
        ).demand_sets["load"]
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.nominal_units)
            for row in value.demands
        ] == [(("dc1/a",), ("dc1/b",), 4), (("dc2/a",), ("dc2/b",), 4)]
        assert value.accounting[0].resolved_units == 8

    def test_no_shared_labels_preserves_discarded_share(self):
        value = _prepared(
            _dc_network(), "^(dc[0-9]+)/", "^(hub[0-9]+)$", mode="pairwise"
        ).demand_sets["load"]
        assert value.demands == ()
        (accounting,) = value.accounting
        assert accounting.declared_units == accounting.discarded_units == 8
        assert accounting.resolved_units == 0
        assert [(share.reason, share.units) for share in accounting.discards] == [
            ("empty_selection", 8)
        ]


def _two_group_network():
    network = Network(nodes={name: Node(name) for name in ("A/1", "A/2", "B/1", "B/2")})
    network.add_link(Link("A/1", "B/1", 1, 3))
    return network


class TestCombineOverlapRefusal:
    def test_per_group_combine_refuses_own_group_overlap(self):
        with pytest.raises(ValueError, match="overlap.*A/1"):
            _prepared(_two_group_network(), "^(A|B)/", "^(A|B)/", volume=100)
        prepared = _prepared(_two_group_network(), "^(A)/", "^B/", volume=100)
        (row,) = prepared.demand_sets["load"].demands
        assert row.endpoints.sources == ("A/1", "A/2")
        assert row.endpoints.destinations == ("B/1", "B/2")

    @pytest.mark.parametrize(
        "preset",
        [
            FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY,
            FlowPolicyPreset.SHORTEST_PATHS_WCMP,
            FlowPolicyPreset.TE_MAXFLOW_UNLIM,
        ],
    )
    def test_group_pairwise_placement_bounded_by_real_capacity(self, preset):
        prepared = _prepared(
            _two_group_network(),
            "^(A|B)/",
            "^(A|B)/",
            group_mode="group_pairwise",
            volume=100,
            policy=preset,
        )
        resolved = prepared.demand_sets["load"]
        assert [row.nominal_units for row in resolved.demands] == [50, 50]
        (accounting,) = resolved.accounting
        assert (
            accounting.declared_units == 100
            and accounting.resolved_units == 100
            and accounting.discarded_units == 0
        )
        assert accounting.discards == ()
        state = (
            place(prepared, PlacementQuery(resolved, workers=1))
            .cases[0]
            .states["converged"]
        )
        assert [row.result.delivered for row in state.rows] == [1, 1]
        assert (
            state.totals.reference_request_units == 100
            and state.totals.delivered_units == 2
        )

    def test_flatten_combine_full_overlap_raises(self):
        with pytest.raises(ValueError, match="overlap"):
            _prepared(
                _two_group_network(),
                "^(A|B)/",
                "^(A|B)/",
                group_mode="flatten",
                volume=100,
            )
        assert (
            len(
                _prepared(_two_group_network(), "^A/", "^B/", group_mode="flatten")
                .demand_sets["load"]
                .demands
            )
            == 1
        )

    def test_flatten_combine_partial_overlap_refuses(self):
        with pytest.raises(ValueError, match="overlap.*A/1"):
            _prepared(
                _two_group_network(), "^A/", "^(A/1|B)", group_mode="flatten", volume=10
            )
        value = _prepared(
            _two_group_network(), "^A/", "^B/", group_mode="flatten", volume=10
        ).demand_sets["load"]
        assert value.demands[0].nominal_units == 10


class TestPerGroupVolumeConservation:
    def test_combine_volume_conserved_with_three_groups(self):
        network = Network(
            nodes={name: Node(name) for name in ("g1/x", "g2/x", "g3/x", "sink")}
        )
        for name in ("g1/x", "g2/x", "g3/x"):
            network.add_link(Link(name, "sink", 10, 1))
        value = _prepared(network, "^(g[0-9]+)/", "^sink$", volume=9).demand_sets[
            "load"
        ]
        assert [row.nominal_units for row in value.demands] == [3, 3, 3]
        assert (
            value.accounting[0].declared_units
            == value.accounting[0].resolved_units
            == 9
        )
        assert value.accounting[0].discarded_units == 0
