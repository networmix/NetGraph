import math
import pytest
from unittest.mock import MagicMock
from typing import Dict, List, Set, Tuple

from ngraph.lib.graph import StrictMultiDiGraph, NodeID, EdgeID, AttrDict
from ngraph.lib.algorithms.edge_select import EdgeSelect, edge_select_fabric
from ngraph.lib.algorithms.base import MIN_CAP, Cost


@pytest.fixture
def mock_graph() -> StrictMultiDiGraph:
    """A mock StrictMultiDiGraph for passing to selection functions."""
    return MagicMock(spec=StrictMultiDiGraph)


@pytest.fixture
def edge_map() -> Dict[EdgeID, AttrDict]:
    """
    A basic edge_map with varying costs/capacities/flows.
    """
    return {
        "edgeA": {"cost": 10, "capacity": 100, "flow": 0},  # leftover=100
        "edgeB": {"cost": 10, "capacity": 50, "flow": 25},  # leftover=25
        "edgeC": {"cost": 5, "capacity": 10, "flow": 0},  # leftover=10
        "edgeD": {"cost": 20, "capacity": 10, "flow": 5},  # leftover=5
        "edgeE": {"cost": 5, "capacity": 2, "flow": 1},  # leftover=1
    }


# ------------------------------------------------------------------------------
# Invalid usage / error conditions
# ------------------------------------------------------------------------------


def test_invalid_enum_value():
    """
    Using Python's Enum with an invalid int calls the Enum constructor
    and raises '999 is not a valid EdgeSelect'.
    This verifies that scenario rather than your custom error message.
    """
    with pytest.raises(ValueError, match="999 is not a valid EdgeSelect"):
        EdgeSelect(999)  # triggers Python's built-in check


def test_user_defined_no_func():
    """Provide edge_select=USER_DEFINED without 'edge_select_func', triggers ValueError."""
    with pytest.raises(ValueError, match="requires 'edge_select_func'"):
        edge_select_fabric(edge_select=EdgeSelect.USER_DEFINED)


# ------------------------------------------------------------------------------
# Basic functionality and edge cases
# ------------------------------------------------------------------------------


def test_empty_edge_map(mock_graph):
    """
    An empty edges_map must always yield (inf, []).
    We'll test multiple EdgeSelect variants in a loop to ensure coverage.
    """
    variants = [
        EdgeSelect.ALL_MIN_COST,
        EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
        EdgeSelect.SINGLE_MIN_COST,
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED,
    ]
    for variant in variants:
        select_func = edge_select_fabric(variant)
        cost, edges = select_func(
            mock_graph, "A", "B", {}, ignored_edges=set(), ignored_nodes=set()
        )
        assert cost == float("inf")
        assert edges == []


def test_excluded_nodes_all_min_cost(mock_graph, edge_map):
    """
    If dst_node is in ignored_nodes, we must get (inf, []) regardless of edges.
    """
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph,
        src_node="A",
        dst_node="excludedB",
        edges_map=edge_map,
        ignored_edges=None,
        ignored_nodes={"excludedB"},
    )
    assert cost == float("inf")
    assert edges == []


def test_all_min_cost_tie_break(mock_graph):
    """
    Two edges with effectively equal cost within 1e-12 must be returned together.
    We'll make the difference strictly < 1e-12 so they are recognized as equal.
    """
    edge_map_ = {
        "e1": {"cost": 10.0, "capacity": 50, "flow": 0},
        "e2": {
            "cost": 10.0000000000005,
            "capacity": 50,
            "flow": 0,
        },  # diff=5e-13 < 1e-12
        "e3": {"cost": 12.0, "capacity": 50, "flow": 0},
    }
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph, "A", "B", edge_map_, ignored_edges=set(), ignored_nodes=set()
    )
    assert math.isclose(cost, 10.0, abs_tol=1e-12)
    # e1 and e2 both returned
    assert set(edges) == {"e1", "e2"}


def test_all_min_cost_no_valid(mock_graph):
    """
    If all edges are in ignored_edges, we get (inf, []) from ALL_MIN_COST.
    """
    edge_map_ = {
        "e1": {"cost": 10, "capacity": 50, "flow": 0},
        "e2": {"cost": 20, "capacity": 50, "flow": 0},
    }
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph, "A", "B", edge_map_, ignored_edges={"e1", "e2"}, ignored_nodes=set()
    )
    assert cost == float("inf")
    assert edges == []


# ------------------------------------------------------------------------------
# Tests for each EdgeSelect variant
# ------------------------------------------------------------------------------


def test_edge_select_excluded_edges(mock_graph, edge_map):
    """
    Using ALL_MIN_COST. 'edgeC' has cost=5, but if excluded, next min is 'edgeE'=5, or else 10.
    So we skip 'edgeC' and pick 'edgeE'.
    """
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph,
        "nodeA",
        "nodeB",
        edge_map,
        ignored_edges={"edgeC"},  # exclude edgeC
        ignored_nodes=set(),
    )
    assert cost == 5
    assert edges == ["edgeE"]


def test_edge_select_all_min_cost(mock_graph, edge_map):
    """ALL_MIN_COST => all edges with minimal cost => 5 => edgeC, edgeE."""
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 5
    assert set(chosen) == {"edgeC", "edgeE"}


def test_edge_select_single_min_cost(mock_graph, edge_map):
    """
    SINGLE_MIN_COST => one edge with min cost => 5 => either edgeC or edgeE.
    """
    select_func = edge_select_fabric(EdgeSelect.SINGLE_MIN_COST)
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 5
    assert len(chosen) == 1
    assert chosen[0] in {"edgeC", "edgeE"}


def test_edge_select_all_min_cost_with_cap(mock_graph, edge_map):
    """
    ALL_MIN_COST_WITH_CAP_REMAINING => leftover>=10 => edgesA,B,C => among them, cost=5 => edgeC
    so cost=5, chosen=[edgeC]
    """
    select_func = edge_select_fabric(
        EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING, select_value=10
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 5
    assert chosen == ["edgeC"]


def test_edge_select_all_any_cost_with_cap(mock_graph, edge_map):
    """
    ALL_ANY_COST_WITH_CAP_REMAINING => leftover>=10 => edgesA,B,C. We return all three, ignoring
    cost except for returning min cost => 5
    """
    select_func = edge_select_fabric(
        EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING, select_value=10
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 5
    assert set(chosen) == {"edgeA", "edgeB", "edgeC"}


def test_edge_select_single_min_cost_with_cap_remaining(mock_graph, edge_map):
    """
    SINGLE_MIN_COST_WITH_CAP_REMAINING => leftover>=5 => edgesA(100),B(25),C(10),D(5).
    among them, min cost=5 => edgeC
    """
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING, select_value=5
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 5
    assert chosen == ["edgeC"]


def test_edge_select_single_min_cost_with_cap_remaining_no_valid(mock_graph, edge_map):
    """
    leftover>=999 => none qualify => (inf, []).
    """
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING, select_value=999
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == float("inf")
    assert chosen == []


def test_edge_select_single_min_cost_load_factored(mock_graph, edge_map):
    """
    cost= cost*100 + round((flow/capacity)*10). Among leftover>=MIN_CAP => all edges.
    edgeC => 5*100+0=500 => minimum => pick edgeC
    """
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 500.0
    assert chosen == ["edgeC"]


def test_load_factored_edge_under_min_cap(mock_graph, edge_map):
    """
    If leftover < select_value => skip the edge. We'll set leftover(E)=0.5 => skip it => pick edgeC
    """
    edge_map["edgeE"]["flow"] = 1.5  # leftover=0.5
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED, select_value=1.0
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == 500
    assert chosen == ["edgeC"]


def test_all_any_cost_with_cap_no_valid(mock_graph, edge_map):
    """
    leftover>=999 => none qualify => (inf, []).
    """
    select_func = edge_select_fabric(
        EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING, select_value=999
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == float("inf")
    assert chosen == []


# ------------------------------------------------------------------------------
# User-defined function tests
# ------------------------------------------------------------------------------


def test_user_defined_custom(mock_graph, edge_map):
    """
    Provide a user-defined function that picks edges with cost <=10
    and uses sum of costs as the cost.
    """

    def custom_func(
        graph: StrictMultiDiGraph,
        src: NodeID,
        dst: NodeID,
        edg_map: Dict[EdgeID, AttrDict],
        ignored_edges: Set[EdgeID],
        ignored_nodes: Set[NodeID],
    ) -> Tuple[Cost, List[EdgeID]]:
        chosen = []
        total = 0.0
        for eid, attrs in edg_map.items():
            if eid in ignored_edges:
                continue
            if attrs["cost"] <= 10:
                chosen.append(eid)
                total += attrs["cost"]
        if not chosen:
            return float("inf"), []
        return (total, chosen)

    select_func = edge_select_fabric(
        EdgeSelect.USER_DEFINED, edge_select_func=custom_func
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, ignored_edges=set(), ignored_nodes=set()
    )
    # Edges <=10 => A,B,C,E => sum=10+10+5+5=30
    assert cost == 30
    assert set(chosen) == {"edgeA", "edgeB", "edgeC", "edgeE"}


def test_user_defined_excludes_all(mock_graph):
    """
    If user function always returns (inf, []), we confirm no edges are chosen.
    """

    def exclude_all_func(*args, **kwargs):
        return float("inf"), []

    select_func = edge_select_fabric(
        EdgeSelect.USER_DEFINED, edge_select_func=exclude_all_func
    )
    cost, chosen = select_func(
        mock_graph, "X", "Y", {}, ignored_edges=set(), ignored_nodes=set()
    )
    assert cost == float("inf")
    assert chosen == []
