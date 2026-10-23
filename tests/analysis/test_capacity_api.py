"""Typed capacity questions, exact cuts and converged sensitivity."""

import netgraph_core as ngc
import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.units import UnitsSettings
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare
from tests.placement_fixture import network_of


def _prepare(network):
    return prepare(Scenario(network, units=UnitsSettings(1)))


def _simple_network():
    return network_of(
        [("S", "A", 1, 1), ("A", "T", 1, 1), ("S", "B", 1, 1), ("B", "T", 1, 1)]
    )


def _query(source="^S$", target="^T$", **kwargs):
    return CapacityQuery(Selector(source), Selector(target), workers=1, **kwargs)


def _row(prepared, query=None):
    return capacity(prepared, query or _query()).cases[0].states["converged"].rows[0]


def test_capacity_combine_basic():
    prepared = _prepare(
        network_of([("A", "B", 2, 1), ("B", "C", 1, 1), ("A", "C", 1, 1)])
    )
    row = _row(prepared, _query("^A$", "^C$", export_cost_distribution=True))
    assert row.endpoints.sources == ("A",) and row.endpoints.destinations == ("C",)
    assert row.result.delivered == 2
    assert [(bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins] == [
        (1, 1),
        (2, 1),
    ]


def test_capacity_pairwise_disjoint_groups():
    prepared = _prepare(
        network_of(
            [("S1", "X", 3, 1), ("S2", "X", 1, 1), ("X", "T1", 3, 1), ("X", "T2", 1, 1)]
        )
    )
    query = CapacityQuery(
        Selector(r"^(S\d)$"), Selector(r"^(T\d)$"), mode="pairwise", workers=2
    )
    rows = capacity(prepared, query).cases[0].states["converged"].rows
    assert [
        (row.endpoints.sources, row.endpoints.destinations, row.result.delivered)
        for row in rows
    ] == [
        (("S1",), ("T1",), 3),
        (("S1",), ("T2",), 1),
        (("S2",), ("T1",), 1),
        (("S2",), ("T2",), 1),
    ]


def test_singleton_self_pair_is_zero():
    row = _row(_prepare(_simple_network()), _query(target="^S$"))
    assert row.kind == "self" and row.node == "S" and row.capacity_units == 0


@pytest.mark.parametrize(
    "source,target,label", [("^Z$", "^T$", "source"), ("^S$", "^Z$", "target")]
)
def test_empty_selection_raises(source, target, label):
    prepared = _prepare(_simple_network())
    with pytest.raises(ValueError, match=f"capacity.{label}: empty selection"):
        capacity(prepared, _query(source, target))
    assert _row(prepared).result.delivered == 2


def test_shortest_support_and_unrestricted_use_all_equal_cost_paths():
    prepared = _prepare(_simple_network())
    shortest = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(allocation=ngc.RouteAllocation.OPTIMIZED)
    )
    assert _row(prepared).result.delivered == 2
    assert _row(prepared, _query(config=shortest)).result.delivered == 2


def test_capacity_requested_details_total_matches():
    row = _row(_prepare(_simple_network()), _query(export_cost_distribution=True))
    assert row.result.delivered == 2
    assert [(bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins] == [
        (2, 2)
    ]


def test_capacity_true_minimum_cut_is_opt_in():
    prepared = _prepare(_simple_network())
    assert _row(prepared).result.min_cut is None
    row = _row(prepared, _query(outputs=ngc.OutputOptions(min_cut=True)))
    cut = [prepared.topology.edge_refs[edge] for edge in row.result.min_cut]
    assert {(edge.link, edge.direction) for edge in cut} == {
        ("S|A|0", "forward"),
        ("S|B|0", "forward"),
    }
    capacities = {"S|A|0": 1, "S|B|0": 1, "A|T|0": 1, "B|T|0": 1}
    assert sum(capacities[edge.link] for edge in cut) == row.result.delivered == 2


def test_network_dc_to_dc_reverse_edge_first_hop():
    prepared = _prepare(
        network_of(
            [
                ("A/leaf", "A/dc", 10, 1),
                ("A/leaf", "B/leaf", 10, 1),
                ("B/leaf", "B/dc", 10, 1),
            ]
        )
    )
    row = _row(prepared, _query("^A/dc$", "^B/dc$", export_cost_distribution=True))
    assert row.result.delivered == 10
    assert [(bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins] == [
        (3, 10)
    ]


def test_sensitivity_shortest_support_recomputes_after_each_failure():
    prepared = _prepare(
        network_of(
            [("S", "A", 10, 1), ("A", "T", 10, 1), ("S", "B", 5, 2), ("B", "T", 5, 2)]
        )
    )
    topology = prepared.topology
    full = edge_sensitivity(
        prepared,
        SensitivityQuery(Selector("^S$"), Selector("^T$"), _query().config, workers=2),
    )
    shortest = edge_sensitivity(
        prepared,
        SensitivityQuery(
            Selector("^S$"),
            Selector("^T$"),
            ngc.FlowPolicyConfig(
                routing=ngc.ShortestPaths(allocation=ngc.RouteAllocation.OPTIMIZED)
            ),
            workers=2,
        ),
    )

    def reductions(value):
        return {
            (
                topology.edge_refs[entry.edge].link,
                topology.edge_refs[entry.edge].direction,
            ): entry.delivery_reduction
            for entry in value.result.entries
            if entry.delivery_reduction
        }

    assert full.result.baseline.delivered == 15
    assert reductions(full) == {
        ("S|A|0", "forward"): 10,
        ("A|T|0", "forward"): 10,
        ("S|B|0", "forward"): 5,
        ("B|T|0", "forward"): 5,
    }
    # Deleting a cheap edge leaves the longer five-unit route as the new shortest.
    assert shortest.result.baseline.delivered == 10
    assert reductions(shortest) == {("S|A|0", "forward"): 5, ("A|T|0", "forward"): 5}


def test_capacity_blind_shortest_model_and_unrestricted_controller():
    prepared = _prepare(
        network_of(
            [
                ("S", "A", 0, 1),
                ("A", "T", 10, 1),
                ("S", "B", 100, 2),
                ("B", "T", 100, 2),
            ]
        )
    )
    shortest = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(allocation=ngc.RouteAllocation.OPTIMIZED)
    )
    assert _row(prepared, _query(config=shortest)).result.delivered == 0
    assert _row(prepared).result.delivered == 100
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        _query(require_capacity=True)


def test_cost_and_augmented_capacity_bounds():
    with pytest.raises(ValueError, match="cost.*2\\*\\*62|cost.*2\\^62"):
        _prepare(network_of([("S", "T", 10, 2**62)]))
    # Both directed capacities count toward the strict aggregate bound.
    with pytest.raises(ValueError, match="range|capacity|2\\^62|2\\*\\*62"):
        _prepare(network_of([("S", "T", 2**61, 1)]))
    prepared = _prepare(network_of([("S", "T", 5e15, 1)]))
    assert _row(prepared).result.delivered == 5_000_000_000_000_000
