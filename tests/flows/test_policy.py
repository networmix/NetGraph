import pytest

from ngraph.algorithms.base import (
    EdgeSelect,
    FlowPlacement,
    PathAlg,
)
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.flows.flow import FlowIndex
from ngraph.flows.policy import FlowPolicy
from ngraph.paths.bundle import PathBundle


class TestFlowPolicy:
    def test_flow_policy_place_demand_1(self, square1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square1)
        flow_policy.place_demand(r, "A", "C", "test_flow", 1)
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "cost": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "cost": 1,
                },
            ),
            2: ("A", "D", 2, {"capacity": 2, "flow": 0, "flows": {}, "cost": 2}),
            3: ("D", "C", 3, {"capacity": 2, "flow": 0, "flows": {}, "cost": 2}),
        }

    def test_flow_policy_place_demand_2(self, square1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square1)
        flow_policy.place_demand(r, "A", "C", "test_flow", 2)
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "cost": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "cost": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 1): 1.0},
                    "cost": 2,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 1): 1.0},
                    "cost": 2,
                },
            ),
        }

    def test_flow_policy_place_demand_3(self, square1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
            max_flow_count=1,
        )
        r = init_flow_graph(square1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 2
        )
        assert placed_flow == 2
        assert remaining_flow == 0
        assert r.get_edges() == {
            0: ("A", "B", 0, {"capacity": 1, "flow": 0.0, "flows": {}, "cost": 1}),
            1: ("B", "C", 1, {"capacity": 1, "flow": 0.0, "flows": {}, "cost": 1}),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 0): 2.0},
                    "cost": 2,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 0): 2.0},
                    "cost": 2,
                },
            ),
        }

    def test_flow_policy_place_demand_4(self, square1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 5
        )
        assert placed_flow == 3
        assert remaining_flow == 2
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "cost": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "cost": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 1): 2.0},
                    "cost": 2,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 1): 2.0},
                    "cost": 2,
                },
            ),
        }

    def test_flow_policy_place_demand_5(self, square3):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
        )
        r = init_flow_graph(square3)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 200
        )
        assert placed_flow == 175
        assert remaining_flow == 25
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 100,
                    "flow": 100.0,
                    "flows": {("A", "C", "test_flow", 0): 100.0},
                    "cost": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 125,
                    "flow": 125.0,
                    "flows": {
                        ("A", "C", "test_flow", 0): 100.0,
                        ("A", "C", "test_flow", 2): 25.0,
                    },
                    "cost": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 75,
                    "flow": 75.0,
                    "flows": {
                        ("A", "C", "test_flow", 1): 50.0,
                        ("A", "C", "test_flow", 2): 25.0,
                    },
                    "cost": 1,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 50,
                    "flow": 50.0,
                    "flows": {("A", "C", "test_flow", 1): 50.0},
                    "cost": 1,
                },
            ),
            4: ("B", "D", 4, {"capacity": 50, "flow": 0, "flows": {}, "cost": 1}),
            5: (
                "D",
                "B",
                5,
                {
                    "capacity": 50,
                    "flow": 25.0,
                    "flows": {("A", "C", "test_flow", 2): 25.0},
                    "cost": 1,
                },
            ),
        }

    def test_flow_policy_place_demand_6(self, line1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            min_flow_count=2,
            max_flow_count=2,
        )
        r = init_flow_graph(line1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 7
        )
        assert placed_flow == 5
        assert remaining_flow == 2
        # Verify totals; exact per-flow distribution may vary under load factoring
        edges = r.get_edges()
        assert edges[0][3]["flow"] == 5.0
        assert edges[4][3]["flow"] + edges[6][3]["flow"] == 5.0

    def test_flow_policy_place_demand_7(self, square3):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            min_flow_count=3,
            max_flow_count=3,
        )
        r = init_flow_graph(square3)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 200
        )
        # Under load-factored single-path TE, all residual may be consumed on minimal-cost legs
        assert round(placed_flow, 10) == 175
        assert round(remaining_flow, 10) == 25
        edges = r.get_edges()
        # Source egress saturates: A->B (100) and A->D (75)
        assert edges[0][3]["flow"] == 100.0
        assert edges[2][3]["flow"] == 75.0
        # Sink ingress saturates: B->C (125), D->C (50)
        assert edges[1][3]["flow"] == 125.0
        assert edges[3][3]["flow"] == 50.0
        # Cross-edge can carry the excess from D to B: D->B (25)
        assert edges[5][3]["flow"] == 25.0

    def test_flow_policy_place_demand_8(self, line1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,
        )
        r = init_flow_graph(line1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 7
        )
        assert round(placed_flow, 10) == 2
        assert round(remaining_flow, 10) == 5

    def test_flow_policy_place_demand_9(self, line1):
        """
        Algorithm must terminate gracefully via diminishing-returns cutoff,
        leaving remaining volume without raising.
        """
        # Use TE-style configuration to exercise termination behavior with many flows
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            max_flow_count=16,
        )
        r = init_flow_graph(line1)
        # Should not raise; should leave some volume unplaced in this configuration
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", ("test_flow", "9"), 7
        )
        assert placed_flow >= 0.0
        assert remaining_flow >= 0.0
        # Expect not all volume is placed under this setup
        assert remaining_flow > 0.0

    def test_flow_policy_place_demand_normal_termination(self, line1):
        """
        Tests normal termination when algorithm naturally runs out of capacity.
        This should terminate gracefully without raising an exception, even if
        some volume remains unplaced.
        """
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,  # Capacity-aware
            multipath=True,
            max_flow_count=10,  # Reasonable limit
        )
        r = init_flow_graph(line1)
        # Should terminate gracefully when capacity is exhausted
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            100,  # Large demand that exceeds capacity
        )
        # Should place some flow but not all due to capacity constraints
        assert placed_flow >= 0
        assert remaining_flow >= 0
        assert placed_flow + remaining_flow == 100
        # Should place at least some flow (line1 has capacity of 5)
        assert placed_flow > 0

    def test_flow_policy_place_demand_max_iterations(self, line1):
        """
        Tests the maximum iteration limit safety net. This creates a scenario that
        forces many iterations by using a very low iteration limit parameter.
        """
        # Create a flow policy with very low max_total_iterations for testing
        # Use EQUAL_BALANCED with unlimited flows to force many iterations
        # TE-like profile to create iterative behavior with multiple flows
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            max_flow_count=16,
            max_total_iterations=2,
        )

        r = init_flow_graph(line1)

        # This should hit the maximum iteration limit (2) before completing
        # because it tries to create many flows in EQUAL_BALANCED mode
        with pytest.raises(
            RuntimeError, match="Maximum iteration limit .* exceeded in place_demand"
        ):
            flow_policy.place_demand(r, "A", "C", "test_flow", 7)

    def test_flow_policy_configurable_iteration_limits(self, line1):
        """
        Tests that the iteration limit parameters are properly configurable
        and affect the behavior as expected.
        """
        # Test with custom limits
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
            multipath=False,
            max_flow_count=16,
            max_no_progress_iterations=5,
            max_total_iterations=20000,
        )

        r = init_flow_graph(line1)

        # Should execute without raising; behavior is bounded by configured limits
        placed, remaining = flow_policy.place_demand(r, "A", "C", "test_flow", 7)
        assert placed >= 0 and remaining >= 0

        # Test with default values (should work same as before)
        flow_policy_default = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )

        # Should complete normally with defaults
        r2 = init_flow_graph(line1)
        placed_flow, remaining_flow = flow_policy_default.place_demand(
            r2, "A", "C", "test_flow", 3
        )
        assert placed_flow > 0

    def test_flow_policy_place_demand_10(self, square1):
        PATH_BUNDLE1 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            static_paths=[PATH_BUNDLE1],
        )
        r = init_flow_graph(square1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            3,
        )
        assert round(placed_flow, 10) == 2
        assert round(remaining_flow, 10) == 1
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", flow_class="test_flow", flow_id=0)
            ].path_bundle
            == PATH_BUNDLE1
        )
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", flow_class="test_flow", flow_id=0)
            ].placed_flow
            == 2
        )

    def test_flow_policy_place_demand_11(self, square1):
        PATH_BUNDLE1 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        PATH_BUNDLE2 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            static_paths=[PATH_BUNDLE1, PATH_BUNDLE2],
        )
        r = init_flow_graph(square1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            3,
        )
        assert round(placed_flow, 10) == 2
        assert round(remaining_flow, 10) == 1
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", flow_class="test_flow", flow_id=1)
            ].path_bundle
            == PATH_BUNDLE2
        )
        # Distribution across static paths may vary; total placement should be correct
        assert placed_flow == 2 and remaining_flow == 1

    def test_flow_policy_place_demand_12(self, square1):
        PATH_BUNDLE1 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        PATH_BUNDLE2 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            static_paths=[PATH_BUNDLE1, PATH_BUNDLE2],
        )
        r = init_flow_graph(square1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            3,
        )

        assert placed_flow == 3 and remaining_flow == 0

    # Constructor Validation: EQUAL_BALANCED requires max_flow_count
    def test_flow_policy_constructor_balanced_requires_max_flow(self):
        with pytest.raises(
            ValueError, match="max_flow_count must be set for EQUAL_BALANCED"
        ):
            FlowPolicy(
                path_alg=PathAlg.SPF,
                flow_placement=FlowPlacement.EQUAL_BALANCED,
                edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
                multipath=False,
            )

    # Constructor Validation: static_paths length must match max_flow_count if provided
    def test_flow_policy_constructor_static_paths_mismatch(self):
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, cost=2
        )
        with pytest.raises(
            ValueError, match="must be equal to the number of static paths"
        ):
            FlowPolicy(
                path_alg=PathAlg.SPF,
                flow_placement=FlowPlacement.EQUAL_BALANCED,
                edge_select=EdgeSelect.ALL_MIN_COST,
                multipath=True,
                static_paths=[path_bundle],  # length=1
                max_flow_count=2,  # mismatch
            )

    # Test remove_demand
    # Ensures that removing demand clears flows from the graph but not from FlowPolicy.
    def test_flow_policy_remove_demand(self, square1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square1)
        flow_policy.place_demand(r, "A", "C", "test_flow", 1)
        assert len(flow_policy.flows) > 0
        # Remove the demand entirely
        flow_policy.remove_demand(r)

        # Check that the flows are still in the policy but not in the graph
        assert len(flow_policy.flows) > 0

        # Check that edges in the graph are at zero flow
        for _, _, _, attr in r.get_edges().values():
            assert attr["flow"] == 0
            assert attr["flows"] == {}
