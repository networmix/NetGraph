"""The same physical failure must reach scalar, batch and fixed-program calls."""

import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    PinnedRoutes,
    RouteSpec,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
)


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("failed", ["node", "link"])
@pytest.mark.parametrize("dispatch", ["scalar", "batch", "pinned"])
def test_case_mask_is_used_by_every_native_dispatch(
    monkeypatch, workers, failed, dispatch
):
    network = Network(nodes={name: Node(name) for name in ("s", "m", "t")})
    network.add_link(Link("s", "m", 4, 1))
    network.add_link(Link("m", "t", 4, 2))
    network.add_link(Link("s", "t", 3, 5))
    source, target = Selector("^s$"), Selector("^t$")
    declarations = DemandSet(
        "fixed", (DemandSpec(source, target, 5, PinnedRoutes(("r",))),)
    )
    prepared = prepare(
        Scenario(
            network,
            routes={"r": RouteSpec("s", nodes=("s", "m", "t"))},
            demand_sets={"fixed": declarations},
            units=UnitsSettings(1),
        ),
        demand_sets=("fixed",),
    )
    policy = FailurePolicy(
        modes=[
            FailureMode(
                1, [FailureRule(failed, path="^m$" if failed == "node" else r"^m\|t$")]
            )
        ]
    )
    config = (
        prepared.demand_sets["fixed"].demands[0].config
        if dispatch == "pinned"
        else CapacityQuery(source, target).config
    )
    original_pairs, original_scalar = ngc.evaluate_pairs, ngc.evaluate_demand
    calls = []

    def pairs(*args, **kwargs):
        calls.append("batch")
        return original_pairs(*args, **kwargs)

    def scalar(*args, **kwargs):
        calls.append("scalar")
        return original_scalar(*args, **kwargs)

    monkeypatch.setattr(ngc, "evaluate_pairs", pairs)
    monkeypatch.setattr(ngc, "evaluate_demand", scalar)
    value = capacity(
        prepared,
        CapacityQuery(
            source,
            target,
            config,
            mode="combine" if dispatch == "scalar" else "pairwise",
            offer=5 if dispatch == "pinned" else None,
            failures=FailureRequest(policy, 1, seed=7),
            workers=workers,
            outputs=ngc.OutputOptions(edge_flows=True),
            export_cost_distribution=True,
        ),
    )
    assert calls == ["batch" if dispatch == "batch" else "scalar"] * 2
    assert len(value.cases) == 2
    for index, case in enumerate(value.cases):
        row = case.states["converged"].rows[0]
        result = row.result
        cheap, direct = (
            ((4, 0) if dispatch == "pinned" else (4, 3))
            if index == 0
            else ((0, 0) if dispatch == "pinned" else (0, 3))
        )
        assert result.delivered == cheap + direct
        if dispatch == "pinned":
            assert result.total_cost is None
            assert [
                (part.cost, part.physical_path_cost, part.delivered_units)
                for part in row.cost_distribution.bins
            ] == ([(3, 3, cheap)] if cheap else [])
        else:
            assert result.total_cost == cheap * 3 + direct * 5
            assert (
                sum(
                    part.marginal_cost * part.units
                    for part in row.cost_distribution.bins
                )
                == result.total_cost
            )
        actual = {
            (ref.link, ref.direction): int(amount)
            for ref, amount in zip(
                prepared.topology.edge_refs, result.edge_flows, strict=True
            )
        }
        expected = {
            (identity, direction): 0
            for identity in network.links
            for direction in ("forward", "reverse")
        }
        expected.update(
            {
                ("s|m|0", "forward"): cheap,
                ("m|t|0", "forward"): cheap,
                ("s|t|0", "forward"): direct,
            }
        )
        assert actual == expected
    assert value.cases[1].case.occurrences == 1
    if failed == "node":
        assert value.cases[1].case.pattern.excluded_nodes == ("m",)
    else:
        assert value.cases[1].case.pattern.excluded_links == ("m|t|0",)
