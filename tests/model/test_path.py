"""Tests for Path dataclass."""

import pytest

from ngraph.model.path import Path
from ngraph.types.dto import EdgeRef


def test_path_basic_creation():
    """Test basic Path creation."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", ()),
    )
    path = Path(path_data, cost=1.0)

    assert path.cost == 1.0
    assert len(path.path) == 2
    assert path.src_node == "A"
    assert path.dst_node == "B"


def test_path_post_init_populates_fields():
    """Test that __post_init__ populates edges, nodes, and edge_tuples."""
    edge1 = EdgeRef("link1", "AB")
    edge2 = EdgeRef("link2", "BC")
    path_data = (
        ("A", (edge1,)),
        ("B", (edge2,)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    assert "A" in path.nodes
    assert "B" in path.nodes
    assert "C" in path.nodes
    assert edge1 in path.edges
    assert edge2 in path.edges
    assert (edge1,) in path.edge_tuples
    assert (edge2,) in path.edge_tuples


def test_path_getitem():
    """Test __getitem__ access."""
    edge1 = EdgeRef("link1", "AB")
    path_data = (
        ("A", (edge1,)),
        ("B", ()),
    )
    path = Path(path_data, cost=1.0)

    assert path[0] == ("A", (edge1,))
    assert path[1] == ("B", ())
    assert path[-1] == ("B", ())


def test_path_iter():
    """Test __iter__ iteration."""
    edge1 = EdgeRef("link1", "AB")
    edge2 = EdgeRef("link2", "BC")
    path_data = (
        ("A", (edge1,)),
        ("B", (edge2,)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    elements = list(path)
    assert len(elements) == 3
    assert elements[0] == ("A", (edge1,))
    assert elements[1] == ("B", (edge2,))
    assert elements[2] == ("C", ())


def test_path_len():
    """Test __len__."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", (EdgeRef("link2", "BC"),)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    assert len(path) == 3


def test_path_src_node():
    """Test src_node property."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", (EdgeRef("link2", "BC"),)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    assert path.src_node == "A"


def test_path_dst_node():
    """Test dst_node property."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", (EdgeRef("link2", "BC"),)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    assert path.dst_node == "C"


def test_path_lt():
    """Test __lt__ comparison based on cost."""
    path1 = Path((("A", ()), ("B", ())), cost=1.0)
    path2 = Path((("A", ()), ("B", ())), cost=2.0)

    assert path1 < path2
    assert not path2 < path1
    assert not path1 < path1


def test_path_lt_with_non_path():
    """Test __lt__ with non-Path returns NotImplemented."""
    path = Path((("A", ()), ("B", ())), cost=1.0)

    result = path.__lt__("not a path")
    assert result is NotImplemented


def test_path_eq():
    """Test __eq__ comparison."""
    edge1 = EdgeRef("link1", "AB")
    path_data = (
        ("A", (edge1,)),
        ("B", ()),
    )
    path1 = Path(path_data, cost=1.0)
    path2 = Path(path_data, cost=1.0)

    assert path1 == path2


def test_path_eq_different_cost():
    """Test __eq__ with different costs."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", ()),
    )
    path1 = Path(path_data, cost=1.0)
    path2 = Path(path_data, cost=2.0)

    assert path1 != path2


def test_path_eq_different_path():
    """Test __eq__ with different paths."""
    path1 = Path((("A", ()), ("B", ())), cost=1.0)
    path2 = Path((("A", ()), ("C", ())), cost=1.0)

    assert path1 != path2


def test_path_eq_with_non_path():
    """Test __eq__ with non-Path returns NotImplemented."""
    path = Path((("A", ()), ("B", ())), cost=1.0)

    result = path.__eq__("not a path")
    assert result is NotImplemented


def test_path_hash():
    """Test __hash__ for set/dict usage."""
    edge1 = EdgeRef("link1", "AB")
    path_data = (
        ("A", (edge1,)),
        ("B", ()),
    )
    path1 = Path(path_data, cost=1.0)
    path2 = Path(path_data, cost=1.0)

    # Same path should have same hash
    assert hash(path1) == hash(path2)

    # Can be used in sets
    path_set = {path1, path2}
    assert len(path_set) == 1


def test_path_hash_different_paths():
    """Test __hash__ for different paths."""
    path1 = Path((("A", ()), ("B", ())), cost=1.0)
    path2 = Path((("A", ()), ("C", ())), cost=1.0)

    # Different paths should (likely) have different hashes
    # Note: hash collisions are possible but unlikely for these simple cases
    assert hash(path1) != hash(path2)


def test_path_repr():
    """Test __repr__ string representation."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", ()),
    )
    path = Path(path_data, cost=1.0)

    repr_str = repr(path)
    assert "Path(" in repr_str
    assert "cost=1.0" in repr_str


def test_path_edges_seq():
    """Test edges_seq cached property."""
    edge1 = EdgeRef("link1", "AB")
    edge2 = EdgeRef("link2", "BC")
    path_data = (
        ("A", (edge1,)),
        ("B", (edge2,)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    edges_seq = path.edges_seq
    assert len(edges_seq) == 2
    assert edges_seq[0] == (edge1,)
    assert edges_seq[1] == (edge2,)


def test_path_edges_seq_single_node():
    """Test edges_seq with single node path."""
    path = Path((("A", ()),), cost=0.0)

    edges_seq = path.edges_seq
    assert edges_seq == ()


def test_path_edges_seq_two_nodes():
    """Test edges_seq with two node path."""
    edge1 = EdgeRef("link1", "AB")
    path = Path((("A", (edge1,)), ("B", ())), cost=1.0)

    edges_seq = path.edges_seq
    assert len(edges_seq) == 1
    assert edges_seq[0] == (edge1,)


def test_path_nodes_seq():
    """Test nodes_seq cached property."""
    edge1 = EdgeRef("link1", "AB")
    edge2 = EdgeRef("link2", "BC")
    path_data = (
        ("A", (edge1,)),
        ("B", (edge2,)),
        ("C", ()),
    )
    path = Path(path_data, cost=2.0)

    nodes_seq = path.nodes_seq
    assert nodes_seq == ("A", "B", "C")


def test_path_get_sub_path():
    """Test get_sub_path method."""
    edge1 = EdgeRef("link1", "AB")
    edge2 = EdgeRef("link2", "BC")
    edge3 = EdgeRef("link3", "CD")
    path_data = (
        ("A", (edge1,)),
        ("B", (edge2,)),
        ("C", (edge3,)),
        ("D", ()),
    )
    path = Path(path_data, cost=3.0)

    sub_path = path.get_sub_path("C")
    assert sub_path.src_node == "A"
    assert sub_path.dst_node == "C"
    assert len(sub_path) == 3
    assert sub_path[-1] == ("C", ())


def test_path_get_sub_path_source_node():
    """Test get_sub_path with source node as destination."""
    edge1 = EdgeRef("link1", "AB")
    path_data = (
        ("A", (edge1,)),
        ("B", ()),
    )
    path = Path(path_data, cost=1.0)

    sub_path = path.get_sub_path("A")
    assert sub_path.src_node == "A"
    assert sub_path.dst_node == "A"
    assert len(sub_path) == 1
    assert sub_path[0] == ("A", ())


def test_path_get_sub_path_node_not_found():
    """Test get_sub_path with non-existent node."""
    edge1 = EdgeRef("link1", "AB")
    path_data = (
        ("A", (edge1,)),
        ("B", ()),
    )
    path = Path(path_data, cost=1.0)

    with pytest.raises(ValueError, match="Node 'Z' not found in path"):
        path.get_sub_path("Z")


def test_path_parallel_edges():
    """Test Path with parallel edges."""
    edge1 = EdgeRef("link1", "AB")
    edge2 = EdgeRef("link2", "AB")
    path_data = (
        ("A", (edge1, edge2)),
        ("B", ()),
    )
    path = Path(path_data, cost=1.0)

    assert edge1 in path.edges
    assert edge2 in path.edges
    assert (edge1, edge2) in path.edge_tuples


def test_path_sorting():
    """Test that paths can be sorted by cost."""
    path1 = Path((("A", ()), ("B", ())), cost=3.0)
    path2 = Path((("A", ()), ("B", ())), cost=1.0)
    path3 = Path((("A", ()), ("B", ())), cost=2.0)

    sorted_paths = sorted([path1, path2, path3])
    assert sorted_paths[0].cost == 1.0
    assert sorted_paths[1].cost == 2.0
    assert sorted_paths[2].cost == 3.0


def test_path_set_deduplication():
    """Test that identical paths are deduplicated in sets."""
    path_data = (
        ("A", (EdgeRef("link1", "AB"),)),
        ("B", ()),
    )
    path1 = Path(path_data, cost=1.0)
    path2 = Path(path_data, cost=1.0)
    path3 = Path(path_data, cost=2.0)

    path_set = {path1, path2, path3}
    assert len(path_set) == 2  # path1 and path2 are identical
