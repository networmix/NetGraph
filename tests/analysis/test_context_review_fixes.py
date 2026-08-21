"""Regression tests for AnalysisContext review fixes.

Covers:
- Fractional link costs raise ValueError instead of silent int64 truncation.
- Unbound contexts preserve custom augmentations in flow methods.
- Bound flow calls do not re-run node selection to fill missing pairs.
- Missing pairs are filled with fresh default objects, never one shared alias.
- PAIRWISE pseudo-node attachment edges are emitted once per group member.
- Unbound contexts build the Core graph lazily.
- sensitivity_with_flow computes max flow and sensitivity in one pass.
"""

from __future__ import annotations

import pytest

from ngraph import Link, Mode, Network, Node, analyze
from ngraph.analysis import AugmentationEdge


def _two_node_network() -> Network:
    """Build a minimal A->B network with unit capacity."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=1.0, cost=1.0))
    return net


class TestFractionalCostValidation:
    """Fractional link costs must raise instead of truncating to int64."""

    @staticmethod
    def _fractional_cost_network() -> Network:
        net = Network()
        for name in ["A", "B"]:
            net.add_node(Node(name))
        net.add_link(Link("A", "B", capacity=1.0, cost=2.5))
        return net

    def test_bound_context_raises_naming_link(self) -> None:
        net = self._fractional_cost_network()
        link_id = next(iter(net.links))

        with pytest.raises(ValueError, match="Non-integer link costs") as excinfo:
            analyze(net, source="^A$", sink="^B$")

        assert link_id in str(excinfo.value)
        assert "2.5" in str(excinfo.value)

    def test_unbound_context_raises_on_first_graph_use(self) -> None:
        net = self._fractional_cost_network()
        ctx = analyze(net)  # Lazy build: no error yet

        with pytest.raises(ValueError, match="Non-integer link costs"):
            ctx.shortest_path_cost("^A$", "^B$")

    def test_unbound_flow_call_raises(self) -> None:
        net = self._fractional_cost_network()

        with pytest.raises(ValueError, match="Non-integer link costs"):
            analyze(net).max_flow("^A$", "^B$")

    def test_fractional_augmentation_cost_raises(self) -> None:
        net = _two_node_network()

        with pytest.raises(ValueError, match="Non-integer link costs") as excinfo:
            analyze(
                net,
                source="^A$",
                sink="^B$",
                augmentations=[AugmentationEdge("A", "B", 5.0, 0.5)],
            )

        assert "augmentation 'A'->'B'" in str(excinfo.value)

    def test_integral_float_costs_accepted(self) -> None:
        net = Network()
        for name in ["A", "B"]:
            net.add_node(Node(name))
        net.add_link(Link("A", "B", capacity=1.0, cost=2.0))

        result = analyze(net).shortest_path_cost("^A$", "^B$")
        assert result[("^A$", "^B$")] == 2.0


class TestUnboundAugmentationsPreserved:
    """Unbound flow methods must use custom augmentations."""

    def test_unbound_max_flow_uses_augmentations(self) -> None:
        net = _two_node_network()
        augs = [AugmentationEdge("A", "B", 5.0, 1)]

        ctx = analyze(net, augmentations=augs)
        result = ctx.max_flow("^A$", "^B$")

        # 1.0 from the real link + 5.0 from the augmentation
        assert result[("^A$", "^B$")] == pytest.approx(6.0)

    def test_unbound_matches_bound_with_same_augmentations(self) -> None:
        net = _two_node_network()
        augs = [AugmentationEdge("A", "B", 5.0, 1)]

        bound = analyze(net, source="^A$", sink="^B$", augmentations=augs)
        unbound = analyze(net, augmentations=augs)

        assert unbound.max_flow("^A$", "^B$") == bound.max_flow()

    def test_unbound_max_flow_detailed_uses_augmentations(self) -> None:
        net = _two_node_network()
        augs = [AugmentationEdge("A", "B", 5.0, 1)]

        ctx = analyze(net, augmentations=augs)
        result = ctx.max_flow_detailed("^A$", "^B$")

        assert result[("^A$", "^B$")].total_flow == pytest.approx(6.0)

    def test_unbound_sensitivity_uses_augmentations(self) -> None:
        net = _two_node_network()
        augs = [AugmentationEdge("A", "B", 5.0, 1)]

        bound = analyze(net, source="^A$", sink="^B$", augmentations=augs)
        unbound = analyze(net, augmentations=augs)

        assert unbound.sensitivity("^A$", "^B$") == bound.sensitivity()


class TestFillMissingPairsPrecomputed:
    """Bound flow calls fill missing pairs without re-running selection."""

    @staticmethod
    def _pairwise_overlap_network() -> Network:
        net = Network()
        for name in ["S1", "S2", "T1"]:
            net.add_node(Node(name))
        net.add_link(Link("S1", "T1", capacity=5.0, cost=1.0))
        net.add_link(Link("S2", "T1", capacity=3.0, cost=1.0))
        return net

    def test_overlapping_pair_filled_with_default(self) -> None:
        net = self._pairwise_overlap_network()
        ctx = analyze(net, source=r"^(S\d)$", sink=r"^(S1|T1)$", mode=Mode.PAIRWISE)

        results = ctx.max_flow()

        # All 4 pairs present; (S1, S1) overlaps and is filled with 0.0
        assert set(results) == {("S1", "S1"), ("S1", "T1"), ("S2", "S1"), ("S2", "T1")}
        assert results[("S1", "S1")] == 0.0
        assert results[("S1", "T1")] == pytest.approx(5.0)

    def test_bound_flow_calls_do_not_rerun_node_selection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        net = self._pairwise_overlap_network()
        ctx = analyze(net, source=r"^(S\d)$", sink=r"^(S1|T1)$", mode=Mode.PAIRWISE)

        import ngraph.model.selectors as selectors_mod

        def _fail(*args: object, **kwargs: object) -> None:
            raise AssertionError("select_nodes must not run on bound flow calls")

        monkeypatch.setattr(selectors_mod, "select_nodes", _fail)

        results = ctx.max_flow()
        assert results[("S1", "S1")] == 0.0

        detailed = ctx.max_flow_detailed()
        assert detailed[("S1", "S1")].total_flow == 0.0

        sens = ctx.sensitivity()
        assert sens[("S1", "S1")] == {}

        combined = ctx.sensitivity_with_flow()
        assert combined[("S1", "S1")] == (0.0, {})

    def test_missing_pair_defaults_are_not_aliased(self) -> None:
        """Each missing pair gets a fresh default object.

        Regression: one mutable default (dict, MaxFlowResult) was stored
        under every missing pair key, so mutating one entry of a public
        API result would silently mutate the others.
        """
        net = Network()
        for name in ["A", "B"]:
            net.add_node(Node(name))
        net.add_link(Link("A", "B", capacity=1.0, cost=1.0))
        # Pairs (A, A) and (B, B) overlap and are filled with defaults
        ctx = analyze(net, source=r"^(A|B)$", sink=r"^(A|B)$", mode=Mode.PAIRWISE)

        sens = ctx.sensitivity()
        assert sens[("A", "A")] == {} and sens[("B", "B")] == {}
        assert sens[("A", "A")] is not sens[("B", "B")]

        detailed = ctx.max_flow_detailed()
        assert detailed[("A", "A")].total_flow == 0.0
        assert (
            detailed[("A", "A")].cost_distribution
            is not detailed[("B", "B")].cost_distribution
        )

        combined = ctx.sensitivity_with_flow()
        assert combined[("A", "A")] == (0.0, {})
        assert combined[("A", "A")][1] is not combined[("B", "B")][1]


class TestSensitivityWithFlow:
    """Combined max-flow + sensitivity matches the separate calls."""

    @staticmethod
    def _pairwise_network() -> Network:
        net = Network()
        for name in ["S1", "S2", "T1"]:
            net.add_node(Node(name))
        net.add_link(Link("S1", "T1", capacity=5.0, cost=1.0))
        net.add_link(Link("S2", "T1", capacity=3.0, cost=1.0))
        return net

    def test_bound_combined_matches_separate_calls(self) -> None:
        net = self._pairwise_network()
        ctx = analyze(net, source=r"^(S\d)$", sink=r"^(S1|T1)$", mode=Mode.PAIRWISE)

        combined = ctx.sensitivity_with_flow()
        flows = ctx.max_flow()
        sens = ctx.sensitivity()

        assert set(combined) == set(flows) == set(sens)
        for pair_key, (flow_value, sensitivity_map) in combined.items():
            assert flow_value == flows[pair_key]
            assert sensitivity_map == sens[pair_key]

    def test_overlapping_pair_filled_with_default(self) -> None:
        net = self._pairwise_network()
        ctx = analyze(net, source=r"^(S\d)$", sink=r"^(S1|T1)$", mode=Mode.PAIRWISE)

        combined = ctx.sensitivity_with_flow()

        assert combined[("S1", "S1")] == (0.0, {})
        assert combined[("S1", "T1")][0] == pytest.approx(5.0)

    def test_unbound_dispatch_preserves_augmentations(self) -> None:
        net = _two_node_network()
        augs = [AugmentationEdge("A", "B", 5.0, 1)]

        bound = analyze(net, source="^A$", sink="^B$", augmentations=augs)
        unbound = analyze(net, augmentations=augs)

        combined = unbound.sensitivity_with_flow("^A$", "^B$")
        assert combined == bound.sensitivity_with_flow()
        # 1.0 from the real link + 5.0 from the augmentation
        assert combined[("^A$", "^B$")][0] == pytest.approx(6.0)

    def test_selector_argument_validation(self) -> None:
        net = _two_node_network()
        bound = analyze(net, source="^A$", sink="^B$")
        unbound = analyze(net)

        with pytest.raises(ValueError, match="source/sink already configured"):
            bound.sensitivity_with_flow("^A$", "^B$")
        with pytest.raises(ValueError, match="source and sink are required"):
            unbound.sensitivity_with_flow()

    def test_combined_builds_masks_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from ngraph.analysis.context import AnalysisContext

        net = self._pairwise_network()
        ctx = analyze(net, source="^S1$", sink="^T1$")

        calls = {"node_mask": 0, "edge_mask": 0}
        orig_node_mask = AnalysisContext.build_node_mask
        orig_edge_mask = AnalysisContext.build_edge_mask

        def counting_node_mask(self: AnalysisContext, excluded_nodes=None):
            calls["node_mask"] += 1
            return orig_node_mask(self, excluded_nodes)

        def counting_edge_mask(self: AnalysisContext, excluded_links=None):
            calls["edge_mask"] += 1
            return orig_edge_mask(self, excluded_links)

        monkeypatch.setattr(AnalysisContext, "build_node_mask", counting_node_mask)
        monkeypatch.setattr(AnalysisContext, "build_edge_mask", counting_edge_mask)

        ctx.sensitivity_with_flow()

        assert calls == {"node_mask": 1, "edge_mask": 1}


class TestPairwisePseudoEdgeDeduplication:
    """PAIRWISE attachment edges are emitted once per group member."""

    @staticmethod
    def _grouped_network() -> Network:
        net = Network()
        # 3 source groups and 3 sink groups with 2 members each
        for prefix in ["s1", "s2", "s3", "t1", "t2", "t3"]:
            for suffix in ["a", "b"]:
                net.add_node(Node(f"{prefix}{suffix}"))
        net.add_link(Link("s1a", "t1a", capacity=1.0, cost=1.0))
        net.add_link(Link("s2a", "t2a", capacity=2.0, cost=1.0))
        return net

    def test_pseudo_edge_count_linear_in_group_members(self) -> None:
        net = self._grouped_network()
        ctx = analyze(net, source=r"^(s\d)", sink=r"^(t\d)", mode=Mode.PAIRWISE)

        # 2 links x 2 directions = 4 real edges; pseudo edges: one per
        # member per participating group = (3 + 3) groups * 2 members = 12
        # (previously duplicated once per opposing group: 24).
        assert ctx.edge_count == 4 + 12

    def test_pairwise_flows_unchanged(self) -> None:
        net = self._grouped_network()
        ctx = analyze(net, source=r"^(s\d)", sink=r"^(t\d)", mode=Mode.PAIRWISE)

        results = ctx.max_flow()

        assert len(results) == 9
        assert results[("s1", "t1")] == pytest.approx(1.0)
        assert results[("s2", "t2")] == pytest.approx(2.0)
        assert results[("s3", "t3")] == 0.0


class TestLazyCoreGraphBuild:
    """Unbound contexts defer the Core graph build until needed."""

    def test_unbound_context_is_lazy(self) -> None:
        net = _two_node_network()
        ctx = analyze(net)

        assert ctx._core is None

        # Unbound flow analysis builds a temporary bound context and does
        # not need this context's own Core graph.
        flow = ctx.max_flow("^A$", "^B$")
        assert flow[("^A$", "^B$")] == pytest.approx(1.0)
        assert ctx._core is None

        # Path analysis triggers the lazy build
        cost = ctx.shortest_path_cost("^A$", "^B$")
        assert cost[("^A$", "^B$")] == 1.0
        assert ctx._core is not None

    def test_bound_context_builds_eagerly(self) -> None:
        net = _two_node_network()
        ctx = analyze(net, source="^A$", sink="^B$")

        assert ctx._core is not None
        assert ctx.max_flow()[("^A$", "^B$")] == pytest.approx(1.0)

    def test_unbound_with_augmentations_builds_eagerly(self) -> None:
        net = _two_node_network()
        ctx = analyze(net, augmentations=[AugmentationEdge("A", "B", 5.0, 1)])

        assert ctx._core is not None
        # Augmented edge visible in the graph: 2 real + 1 augmentation
        assert ctx.edge_count == 3

    def test_core_accessors_trigger_lazy_build(self) -> None:
        net = _two_node_network()
        ctx = analyze(net)

        assert ctx._core is None
        assert ctx.node_count == 2
        assert ctx._core is not None
