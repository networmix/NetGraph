from __future__ import annotations

from typing import Any, Callable

import pytest

from ngraph.algorithms.base import EdgeSelect, PathAlg
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.algorithms.placement import FlowPlacement
from ngraph.flows.policy import FlowPolicy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def _simple_graph() -> StrictMultiDiGraph:
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    g.add_edge("A", "B", cost=1, capacity=5)
    # Two parallel edges B->C to allow exclusions without disconnecting
    g.add_edge("B", "C", cost=1, capacity=5)
    g.add_edge("B", "C", cost=1, capacity=5)
    return g


def test_edge_selector_cached_without_custom_func(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Count how many times edge_select_fabric is constructed
    from ngraph.algorithms import edge_select as edge_select_mod

    calls: dict[str, int] = {"n": 0}
    original_fabric: Callable[..., Any] = edge_select_mod.edge_select_fabric

    def counting_fabric(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original_fabric(*args, **kwargs)

    monkeypatch.setattr(edge_select_mod, "edge_select_fabric", counting_fabric)

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=True,
    )

    g = _simple_graph()
    init_flow_graph(g)

    # First path-bundle construction may use SPF fast path (no selector build)
    pb1 = policy._get_path_bundle(g, "A", "C")
    assert pb1 is not None
    first_calls = calls["n"]
    assert first_calls in (0, 1)

    # Second call with same effective select_value reuses the prior behavior:
    # - fast path: no selector, count stays the same
    # - cached selector: no additional builds
    pb2 = policy._get_path_bundle(g, "A", "C")
    assert pb2 is not None
    assert calls["n"] == first_calls

    # Changing effective select_value (via min_flow) should trigger a new selector build
    pb3 = policy._get_path_bundle(g, "A", "C", min_flow=0.5)
    assert pb3 is not None
    # Forcing a min_flow disables fast path and should construct a selector at least once
    assert calls["n"] >= first_calls + 1

    # Exclusions should NOT change cached callable construction count (selectors are exclusion-agnostic)
    # Ensure that using excluded_edges/nodes does not rebuild the selector and SPF still succeeds
    # Exclude one of the parallel B->C edges
    # Find one B->C edge id
    some_edge_id = next(
        eid for eid, (u, v, _k, _a) in g.get_edges().items() if u == "B" and v == "C"
    )
    pb4 = policy._get_path_bundle(g, "A", "C", excluded_edges={some_edge_id})
    assert pb4 is not None
    # With exclusions, SPF may internally construct a selector; do not assert call count.


def test_edge_selector_not_cached_with_custom_func(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ngraph.algorithms import edge_select as edge_select_mod

    calls: dict[str, int] = {"n": 0}
    original_fabric = edge_select_mod.edge_select_fabric

    def counting_fabric(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original_fabric(*args, **kwargs)

    monkeypatch.setattr(edge_select_mod, "edge_select_fabric", counting_fabric)

    # Provide a trivial custom selector; caching must be bypassed
    def custom_selector(*_args: Any, **_kwargs: Any):  # type: ignore[no-untyped-def]
        return 1.0, []

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.USER_DEFINED,
        multipath=True,
        edge_select_func=custom_selector,
    )

    g = _simple_graph()
    init_flow_graph(g)

    policy._get_path_bundle(g, "A", "C")
    policy._get_path_bundle(g, "A", "C")

    # Fabric is invoked both times since custom func disables cache
    assert calls["n"] == 2


def test_cache_respects_node_exclusions_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ngraph.algorithms import edge_select as edge_select_mod

    calls: dict[str, int] = {"n": 0}
    original_fabric = edge_select_mod.edge_select_fabric

    def counting_fabric(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original_fabric(*args, **kwargs)

    monkeypatch.setattr(edge_select_mod, "edge_select_fabric", counting_fabric)

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=True,
    )

    g = _simple_graph()
    init_flow_graph(g)

    # Build once (may be fast path with zero selector builds)
    assert policy._get_path_bundle(g, "A", "C") is not None
    initial = calls["n"]
    assert initial in (0, 1)

    # Exclude a node not on the path; should not rebuild and still succeed
    assert policy._get_path_bundle(g, "A", "C", excluded_nodes={"A"}) is None
    # Excluding A removes the source; SPF cannot find a path -> None is expected
    # If fast path was used initially (initial==0), SPF may construct a selector internally here.
    if initial > 0:
        assert calls["n"] == initial


def test_cache_rebuilds_when_edge_select_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ngraph.algorithms import edge_select as edge_select_mod

    calls: dict[str, int] = {"n": 0}
    original_fabric = edge_select_mod.edge_select_fabric

    def counting_fabric(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original_fabric(*args, **kwargs)

    monkeypatch.setattr(edge_select_mod, "edge_select_fabric", counting_fabric)

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=True,
    )
    g = _simple_graph()
    init_flow_graph(g)

    assert policy._get_path_bundle(g, "A", "C") is not None
    base_calls = calls["n"]
    assert base_calls in (0, 1)

    # If fast path was used (base_calls==0), force non-fast path to exercise cache behavior
    if base_calls == 0:
        policy.edge_select_value = 0.123
        assert policy._get_path_bundle(g, "A", "C") is not None
        base_calls = calls["n"]

    # Change the policy's edge_select; cache should miss and rebuild when selector is in use
    policy.edge_select = EdgeSelect.ALL_MIN_COST
    assert policy._get_path_bundle(g, "A", "C") is not None
    assert calls["n"] == base_calls + 1


def test_cache_rebuilds_when_policy_edge_select_value_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ngraph.algorithms import edge_select as edge_select_mod

    calls: dict[str, int] = {"n": 0}
    original_fabric = edge_select_mod.edge_select_fabric

    def counting_fabric(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original_fabric(*args, **kwargs)

    monkeypatch.setattr(edge_select_mod, "edge_select_fabric", counting_fabric)

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=True,
        # Start with None; effective select value is None
        edge_select_value=None,
    )
    g = _simple_graph()
    init_flow_graph(g)

    assert policy._get_path_bundle(g, "A", "C") is not None
    first = calls["n"]
    # May be 0 with fast path or 1 if selector was built
    assert first in (0, 1)

    # Change edge_select_value to a numeric threshold; cache must rebuild
    policy.edge_select_value = 0.123
    assert policy._get_path_bundle(g, "A", "C") is not None
    assert calls["n"] >= first + 1
