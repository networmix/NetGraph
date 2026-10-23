"""Independent integer-flow/minimum-cost oracle for every converged case."""

import netgraph_core as ngc
import pytest

from ngraph.analysis.demands import resolve_demands
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from tests.flow_oracle import EDGES, enumerate_optimum
from tests.prepared import prepare_network


def context(preset):
    network = Network()
    for name in ("t", "b", "a"):
        network.add_node(Node(name))
    for source, target, capacity, cost in (
        ("a", "b", 2, 1),
        ("b", "t", 2, 2),
        ("a", "t", 3, 5),
    ):
        network.add_link(Link(source, target, capacity, cost))
    prepared = prepare_network(network)
    specs = DemandSet(
        "load",
        tuple(
            DemandSpec(Selector("^a$"), Selector("^t$"), volume, preset)
            for volume in (4, 3)
        ),
    )
    return prepared, resolve_demands(prepared, specs)


@pytest.mark.parametrize(
    "preset,totals",
    [
        (
            FlowPolicyPreset.TE_MAXFLOW_UNLIM,
            {(): (4, 1), ("b",): (3, 0), ("a|t|0",): (2, 0)},
        ),
        (
            FlowPolicyPreset.SHORTEST_PATHS_MAXFLOW,
            {(): (2, 0), ("b",): (3, 0), ("a|t|0",): (2, 0)},
        ),
    ],
)
def test_each_case_uses_its_own_mask_and_native_support_with_minimum_cost(
    preset, totals
):
    prepared, demands = context(preset)
    policy = FailurePolicy(
        modes=[
            FailureMode(1, [FailureRule("node", path="^b$")]),
            FailureMode(1, [FailureRule("link", path=r"^a\|t$")]),
        ]
    )
    query = PlacementQuery(
        demands,
        failures=FailureRequest(policy, 24, seed=17),
        workers=2,
        outputs=ngc.OutputOptions(edge_flows=True, min_cut=True),
        export_cost_distribution=True,
    )
    analysis = place(prepared, query)
    assert len(analysis.cases) == 3
    assert sum(case.case.occurrences for case in analysis.cases) == 24
    seen = set()
    for case_result in analysis.cases:
        case = case_result.case
        nodes, links = case.pattern.excluded_nodes, case.pattern.excluded_links
        key = nodes or links
        seen.add(key)
        assert set(case_result.states) == {"converged"}
        state = case_result.states["converged"]
        assert tuple(row.result.delivered for row in state.rows) == totals[key]
        residual = [capacity for _, _, _, _, capacity, _ in EDGES]
        for row, request in zip(state.rows, (4, 3), strict=True):
            expected_value, expected_cost, expected_vector = enumerate_optimum(
                request,
                residual,
                nodes,
                links,
                preset == FlowPolicyPreset.SHORTEST_PATHS_MAXFLOW,
            )
            result = row.result
            assert result.delivered == expected_value
            assert result.total_cost == expected_cost
            actual = {
                (ref.link, ref.direction): int(flow)
                for ref, flow in zip(
                    prepared.topology.edge_refs, result.edge_flows, strict=True
                )
            }
            assert (
                tuple(actual[(link, direction)] for link, direction, *_ in EDGES)
                == expected_vector
            )
            assert result.source_drops == 0 and result.edge_drops == []
            assert result.unadmitted == request - expected_value
            assert (
                result.requested == request and row.reference_request_units == request
            )
            assert result.by_source[0].delivered == expected_value
            assert row.cost_distribution is not None and not row.unavailable_outputs
            if preset == FlowPolicyPreset.SHORTEST_PATHS_MAXFLOW:
                assert result.min_cut is None
            residual = [
                remaining - used
                for remaining, used in zip(residual, expected_vector, strict=True)
            ]
        assert state.totals.delivered_units == sum(totals[key])
        assert state.totals.reference_request_units == 7
        assert state.totals.reference_shortfall_units == 7 - sum(totals[key])
    assert seen == {(), ("b",), ("a|t|0",)}
    # A separate baseline after failed cases detects an escaped working ledger.
    repeated = place(
        prepared, PlacementQuery(demands, outputs=ngc.OutputOptions(edge_flows=True))
    )
    assert (
        tuple(
            row.result.delivered for row in repeated.cases[0].states["converged"].rows
        )
        == totals[()]
    )
