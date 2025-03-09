from math import isclose
import pytest
from unittest.mock import MagicMock
from typing import Dict, Set, Tuple

from ngraph.lib.graph import StrictMultiDiGraph, NodeID, EdgeID, AttrDict
from ngraph.lib.algorithms.edge_select import EdgeSelect, edge_select_fabric
from ngraph.lib.algorithms.base import Cost, MIN_CAP


@pytest.fixture
def mock_graph() -> StrictMultiDiGraph:
    """A mock StrictMultiDiGraph to pass to selection functions for testing."""
    return MagicMock(spec=StrictMultiDiGraph)


@pytest.fixture
def edge_map() -> Dict[EdgeID, AttrDict]:
    """
    A basic edge_map with varying costs/capacities/flows.
    Edge leftover capacity = capacity - flow.
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


def test_invalid_enum_value() -> None:
    """
    Ensure using an invalid int for the EdgeSelect enum raises a ValueError.
    E.g., 999 is not a valid EdgeSelect.
    """
    with pytest.raises(ValueError, match="999 is not a valid EdgeSelect"):
        EdgeSelect(999)


def test_user_defined_no_func() -> None:
    """
    Provide edge_select=USER_DEFINED without 'edge_select_func'.
    This must trigger ValueError.
    """
    with pytest.raises(ValueError, match="requires 'edge_select_func'"):
        edge_select_fabric(edge_select=EdgeSelect.USER_DEFINED)


# ------------------------------------------------------------------------------
# Basic functionality and edge cases
# ------------------------------------------------------------------------------


def test_empty_edge_map(mock_graph: StrictMultiDiGraph) -> None:
    """
    An empty edges_map must yield (inf, []) for any EdgeSelect variant.
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
            mock_graph, "A", "B", {}, excluded_edges=set(), excluded_nodes=set()
        )
        assert cost == float("inf")
        assert edges == []


def test_excluded_nodes_all_min_cost(
    mock_graph: StrictMultiDiGraph, edge_map: Dict[EdgeID, AttrDict]
) -> None:
    """
    If dst_node is in excluded_nodes, we must get (inf, []) regardless of edges.
    """
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph,
        src_node="A",
        dst_node="excludedB",
        edges_map=edge_map,
        excluded_edges=None,
        excluded_nodes={"excludedB"},
    )
    assert cost == float("inf")
    assert edges == []


def test_all_min_cost_tie_break(mock_graph: StrictMultiDiGraph) -> None:
    """
    Edges with costs within 1e-12 of each other are treated as equal.
    Both edges must be returned.
    """
    edge_map_ = {
        "e1": {"cost": 10.0, "capacity": 50, "flow": 0},
        "e2": {"cost": 10.0000000000005, "capacity": 50, "flow": 0},  # diff=5e-13
        "e3": {"cost": 12.0, "capacity": 50, "flow": 0},
    }
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph, "A", "B", edge_map_, excluded_edges=set(), excluded_nodes=set()
    )
    assert isclose(cost, 10.0, abs_tol=1e-12)
    assert set(edges) == {"e1", "e2"}


def test_all_min_cost_no_valid(mock_graph: StrictMultiDiGraph) -> None:
    """
    If all edges are in excluded_edges, we get (inf, []) from ALL_MIN_COST.
    """
    edge_map_ = {
        "e1": {"cost": 10, "capacity": 50, "flow": 0},
        "e2": {"cost": 20, "capacity": 50, "flow": 0},
    }
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph,
        "A",
        "B",
        edge_map_,
        excluded_edges={"e1", "e2"},
        excluded_nodes=set(),
    )
    assert cost == float("inf")
    assert edges == []


# ------------------------------------------------------------------------------
# Tests for each EdgeSelect variant
# ------------------------------------------------------------------------------


def test_edge_select_excluded_edges(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    Using ALL_MIN_COST. 'edgeC' has cost=5 but is excluded.
    So the next minimum is also 5 => 'edgeE'.
    """
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, edges = select_func(
        mock_graph,
        "nodeA",
        "nodeB",
        edge_map,
        excluded_edges={"edgeC"},
        excluded_nodes=set(),
    )
    assert cost == 5
    assert edges == ["edgeE"]


def test_edge_select_all_min_cost(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    ALL_MIN_COST => all edges with minimal cost => 5 => edgesC, E.
    """
    select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 5
    assert set(chosen) == {"edgeC", "edgeE"}


def test_edge_select_single_min_cost(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    SINGLE_MIN_COST => exactly one edge with minimal cost (5) => edgeC or edgeE.
    """
    select_func = edge_select_fabric(EdgeSelect.SINGLE_MIN_COST)
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 5
    assert len(chosen) == 1
    assert chosen[0] in {"edgeC", "edgeE"}


def test_edge_select_all_min_cost_with_cap(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    ALL_MIN_COST_WITH_CAP_REMAINING => leftover >= 10 => edgesA, B, C => among them cost=5 => edgeC.
    """
    select_func = edge_select_fabric(
        EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING, select_value=10
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 5
    assert chosen == ["edgeC"]


def test_edge_select_all_any_cost_with_cap(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    ALL_ANY_COST_WITH_CAP_REMAINING => leftover >= 10 => edgesA, B, C.
    All returned, min cost among them is 5.
    """
    select_func = edge_select_fabric(
        EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING, select_value=10
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 5
    assert set(chosen) == {"edgeA", "edgeB", "edgeC"}


def test_edge_select_single_min_cost_with_cap_remaining(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    SINGLE_MIN_COST_WITH_CAP_REMAINING => leftover >= 5 => edgesA(100), B(25), C(10), D(5).
    Among them, minimum cost=5 => edgeC.
    """
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING, select_value=5
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 5
    assert chosen == ["edgeC"]


def test_edge_select_single_min_cost_with_cap_remaining_no_valid(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    If leftover >= 999, none qualify => (inf, []).
    """
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING, select_value=999
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == float("inf")
    assert chosen == []


def test_edge_select_single_min_cost_load_factored(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    cost_val = cost*100 + round((flow/capacity)*10).
    Among leftover >= MIN_CAP => effectively all edges, the lowest combined cost is for edgeC => 5*100+0=500.
    """
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 500.0
    assert chosen == ["edgeC"]


def test_load_factored_edge_under_min_cap(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    If leftover < select_value => skip the edge. We'll set leftover(edgeE)=0.5 => skip it => pick edgeC.
    """
    edge_map["edgeE"]["flow"] = 1.5  # leftover=0.5
    select_func = edge_select_fabric(
        EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED, select_value=1.0
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == 500
    assert chosen == ["edgeC"]


def test_all_any_cost_with_cap_no_valid(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    leftover >= 999 => none qualify => (inf, []).
    """
    select_func = edge_select_fabric(
        EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING, select_value=999
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == float("inf")
    assert chosen == []


# ------------------------------------------------------------------------------
# User-defined function tests
# ------------------------------------------------------------------------------


def test_user_defined_custom(
    mock_graph: StrictMultiDiGraph,
    edge_map: Dict[EdgeID, AttrDict],
) -> None:
    """
    Provide a user-defined function that picks edges with cost <=10
    and uses sum of costs as the returned cost.
    """

    def custom_func(
        graph: StrictMultiDiGraph,
        src: NodeID,
        dst: NodeID,
        edg_map: Dict[EdgeID, AttrDict],
        excluded_edges: Set[EdgeID],
        excluded_nodes: Set[NodeID],
    ) -> Tuple[Cost, list]:
        chosen = []
        total = 0.0
        for eid, attrs in edg_map.items():
            if eid in excluded_edges:
                continue
            if attrs["cost"] <= 10:
                chosen.append(eid)
                total += attrs["cost"]
        if not chosen:
            return float("inf"), []
        return total, chosen

    select_func = edge_select_fabric(
        EdgeSelect.USER_DEFINED, edge_select_func=custom_func
    )
    cost, chosen = select_func(
        mock_graph, "A", "B", edge_map, excluded_edges=set(), excluded_nodes=set()
    )
    # Edges <=10 => A,B,C,E => sum=10+10+5+5=30
    assert cost == 30
    assert set(chosen) == {"edgeA", "edgeB", "edgeC", "edgeE"}


def test_user_defined_excludes_all(mock_graph: StrictMultiDiGraph) -> None:
    """
    If a user-defined function always returns (inf, []), confirm no edges are chosen.
    """

    def exclude_all_func(*args, **kwargs):
        return float("inf"), []

    select_func = edge_select_fabric(
        EdgeSelect.USER_DEFINED, edge_select_func=exclude_all_func
    )
    cost, chosen = select_func(
        mock_graph, "X", "Y", {}, excluded_edges=set(), excluded_nodes=set()
    )
    assert cost == float("inf")
    assert chosen == []
