import pytest
from ngraph.lib.algorithms.base import EdgeSelect, PathAlg, FlowPlacement
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.demand import Demand
from ngraph.lib.flow_policy import FlowPolicy, FlowPolicyConfig, get_flow_policy
from ngraph.lib.flow import FlowIndex
from .algorithms.sample_graphs import line1, square1, square2, triangle1, graph3


# Helper to create a FlowPolicy for testing given a config or explicit parameters.
def create_flow_policy(
    *,
    path_alg: PathAlg,
    flow_placement: FlowPlacement,
    edge_select: EdgeSelect,
    multipath: bool,
    max_flow_count: int = None,
    max_path_cost_factor: float = None
) -> FlowPolicy:
    return FlowPolicy(
        path_alg=path_alg,
        flow_placement=flow_placement,
        edge_select=edge_select,
        multipath=multipath,
        max_flow_count=max_flow_count,
        max_path_cost_factor=max_path_cost_factor,
    )


class TestDemand:
    def test_demand_initialization(self) -> None:
        """Test that a Demand object initializes correctly."""
        d = Demand("A", "C", float("inf"))
        assert d.src_node == "A"
        assert d.dst_node == "C"
        assert d.volume == float("inf")
        # Default demand_class is 0
        assert d.demand_class == 0

    def test_demand_comparison(self) -> None:
        """Test that Demand instances are compared based on their demand class."""
        d_high = Demand("A", "C", float("inf"), demand_class=99)
        d_low = Demand("A", "C", float("inf"), demand_class=0)
        assert d_high > d_low

    def test_demand_place_basic(self, line1) -> None:
        """Test placing a demand using a basic flow policy and check edge values."""
        # Initialize flow graph from fixture 'line1'
        r = init_flow_graph(line1)
        flow_policy = create_flow_policy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        d = Demand("A", "C", float("inf"), demand_class=99)
        placed_demand, remaining_demand = d.place(r, flow_policy)

        # Check placed/remaining values
        assert placed_demand == 5
        assert remaining_demand == float("inf")
        assert d.placed_demand == placed_demand

        # Verify no edge has flow exceeding capacity
        for edge in r.get_edges().values():
            assert edge[3]["flow"] <= edge[3]["capacity"]

        # Expected edges structure from the test graph 'line1'
        expected_edges = {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 5,
                    "flow": 5.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=99, flow_id=0
                        ): 5.0
                    },
                    "metric": 1,
                },
            ),
            1: ("B", "A", 1, {"capacity": 5, "flow": 0, "flows": {}, "metric": 1}),
            2: (
                "B",
                "C",
                2,
                {
                    "capacity": 1,
                    "flow": 0.45454545454545453,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=99, flow_id=0
                        ): 0.45454545454545453
                    },
                    "metric": 1,
                },
            ),
            3: ("C", "B", 3, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 3,
                    "flow": 1.3636363636363635,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=99, flow_id=0
                        ): 1.3636363636363635
                    },
                    "metric": 1,
                },
            ),
            5: ("C", "B", 5, {"capacity": 3, "flow": 0, "flows": {}, "metric": 1}),
            6: (
                "B",
                "C",
                6,
                {
                    "capacity": 7,
                    "flow": 3.1818181818181817,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=99, flow_id=0
                        ): 3.1818181818181817
                    },
                    "metric": 2,
                },
            ),
            7: ("C", "B", 7, {"capacity": 7, "flow": 0, "flows": {}, "metric": 2}),
        }
        assert r.get_edges() == expected_edges

    def test_demand_place_with_square1(self, square1) -> None:
        """Test demand placement on 'square1' graph with min cost flow policy."""
        r = init_flow_graph(square1)
        flow_policy = create_flow_policy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
            max_path_cost_factor=1,
        )
        d = Demand("A", "C", float("inf"), demand_class=99)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 1
        assert remaining_demand == float("inf")

    def test_demand_place_with_square1_anycost(self, square1) -> None:
        """Test demand placement on 'square1' graph using any-cost flow policy."""
        r = init_flow_graph(square1)
        flow_policy = create_flow_policy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        d = Demand("A", "C", float("inf"), demand_class=99)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 3
        assert remaining_demand == float("inf")

    def test_demand_place_with_square2_equal_balanced(self, square2) -> None:
        """Test demand placement on 'square2' graph with equal-balanced flow placement."""
        r = init_flow_graph(square2)
        flow_policy = create_flow_policy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,
        )
        d = Demand("A", "C", float("inf"), demand_class=99)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 2
        assert remaining_demand == float("inf")

    def test_multiple_demands_on_triangle(self, triangle1) -> None:
        """Test multiple demands placement on a triangle graph."""
        r = init_flow_graph(triangle1)
        # Create a list of six demands with same volume and demand class.
        demands = [
            Demand("A", "B", 10, demand_class=42),
            Demand("B", "A", 10, demand_class=42),
            Demand("B", "C", 10, demand_class=42),
            Demand("C", "B", 10, demand_class=42),
            Demand("A", "C", 10, demand_class=42),
            Demand("C", "A", 10, demand_class=42),
        ]
        for demand in demands:
            flow_policy = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
            demand.place(r, flow_policy)

        # Expected consolidated edges from the triangle graph.
        expected_edges = {
            0: (
                "A",
                "B",
                0,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "1",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="B", flow_class=42, flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=42, flow_id=1
                        ): 5.0,
                    },
                },
            ),
            1: (
                "B",
                "A",
                1,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "1",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="B", dst_node="A", flow_class=42, flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="C", dst_node="A", flow_class=42, flow_id=1
                        ): 5.0,
                    },
                },
            ),
            2: (
                "B",
                "C",
                2,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "2",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="B", dst_node="C", flow_class=42, flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=42, flow_id=1
                        ): 5.0,
                    },
                },
            ),
            3: (
                "C",
                "B",
                3,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "2",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="C", dst_node="B", flow_class=42, flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="C", dst_node="A", flow_class=42, flow_id=1
                        ): 5.0,
                    },
                },
            ),
            4: (
                "A",
                "C",
                4,
                {
                    "metric": 1,
                    "capacity": 5,
                    "label": "3",
                    "flow": 5.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", flow_class=42, flow_id=0
                        ): 5.0
                    },
                },
            ),
            5: (
                "C",
                "A",
                5,
                {
                    "metric": 1,
                    "capacity": 5,
                    "label": "3",
                    "flow": 5.0,
                    "flows": {
                        FlowIndex(
                            src_node="C", dst_node="A", flow_class=42, flow_id=0
                        ): 5.0
                    },
                },
            ),
        }
        assert r.get_edges() == expected_edges

        # Verify each demand has been fully placed (placed_demand == demand volume).
        for demand in demands:
            assert demand.placed_demand == 10

    def test_demand_place_partial_with_fraction(self, square2) -> None:
        """Test placing a demand in partial fractions on 'square2' graph."""
        r = init_flow_graph(square2)
        flow_policy = create_flow_policy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
            max_flow_count=2,
        )
        d = Demand("A", "C", 3, demand_class=99)
        # First placement: only half of the remaining demand should be placed.
        placed_demand, remaining_demand = d.place(r, flow_policy, max_fraction=0.5)
        assert placed_demand == 1.5
        assert remaining_demand == 0

        # Second placement: only 0.5 should be placed, leaving 1 unit unplaced.
        placed_demand, remaining_demand = d.place(r, flow_policy, max_fraction=0.5)
        assert placed_demand == 0.5
        assert remaining_demand == 1

    def test_demand_place_te_ucmp_unlim(self, square2) -> None:
        """Test demand placement using TE_UCMP_UNLIM flow policy on 'square2'."""
        r = init_flow_graph(square2)
        d = Demand("A", "C", 3, demand_class=99)
        flow_policy = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 3
        assert remaining_demand == 0

    def test_demand_place_shortest_paths_ecmp(self, square2) -> None:
        """Test demand placement using SHORTEST_PATHS_ECMP flow policy on 'square2'."""
        r = init_flow_graph(square2)
        d = Demand("A", "C", 3, demand_class=99)
        flow_policy = get_flow_policy(FlowPolicyConfig.SHORTEST_PATHS_ECMP)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 2
        assert remaining_demand == 1

    def test_demand_place_graph3_sp_ecmp(self, graph3) -> None:
        """Test demand placement on 'graph3' using SHORTEST_PATHS_ECMP."""
        r = init_flow_graph(graph3)
        d = Demand("A", "D", float("inf"), demand_class=99)
        flow_policy = get_flow_policy(FlowPolicyConfig.SHORTEST_PATHS_ECMP)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 2.5
        assert remaining_demand == float("inf")

    def test_demand_place_graph3_te_ucmp(self, graph3) -> None:
        """Test demand placement on 'graph3' using TE_UCMP_UNLIM."""
        r = init_flow_graph(graph3)
        d = Demand("A", "D", float("inf"), demand_class=99)
        flow_policy = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
        placed_demand, remaining_demand = d.place(r, flow_policy)
        assert placed_demand == 6
        assert remaining_demand == float("inf")
