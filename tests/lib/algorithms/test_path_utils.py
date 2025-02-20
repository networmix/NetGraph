import pytest
from ngraph.lib.algorithms.path_utils import resolve_to_paths


def test_no_path_if_dst_not_in_pred():
    """If the dst_node is not present in pred, no paths should be yielded."""
    # Source is "Z", which SPF would record as pred["Z"] = {} if Z is in the graph.
    # But "B" is absent entirely, meaning 'B' was unreachable.
    pred = {
        "Z": {},  # source node with empty predecessor set
        "A": {"Z": ["edgeA_Z"]},
    }
    # dst_node="B" is not in pred, so there's no path
    paths = list(resolve_to_paths("Z", "B", pred))
    assert paths == [], "Expected no paths when dst_node is missing from pred."


def test_trivial_path_src_eq_dst():
    """
    If src_node == dst_node and it's in pred, the function yields a single empty-edge path.
    SPF typically sets pred[src_node] = {} to indicate no predecessor for source.
    """
    # Here the source and destination are "A". SPF would store pred["A"] = {}.
    pred = {"A": {}}  # No actual predecessors, cost[A] = 0 in SPF
    paths = list(resolve_to_paths("A", "A", pred))
    # Expect exactly one trivial path: ((A, ()),)
    assert len(paths) == 1
    assert paths[0] == (("A", tuple()),)


def test_single_linear_path():
    """
    Tests a simple linear path: Z -> A -> B -> C, with src=Z, dst=C.
    Each node that is reachable from Z must be in pred, including Z itself.
    """
    pred = {
        # If spf found a route from Z -> A, it sets pred["A"] = {"Z": ["edgeZA"]}.
        "Z": {},  # source node
        "A": {"Z": ["edgeZA"]},
        "B": {"A": ["edgeAB"]},
        "C": {"B": ["edgeBC"]},
    }
    # There's only one path: Z -> A -> B -> C
    paths = list(resolve_to_paths("Z", "C", pred))
    assert len(paths) == 1

    expected = (
        ("Z", ("edgeZA",)),
        ("A", ("edgeAB",)),
        ("B", ("edgeBC",)),
        ("C", ()),
    )
    assert paths[0] == expected


def test_multiple_predecessors_branching():
    """
    Tests a branching scenario where the dst node (D) can come from
    two predecessors: B or C, and each of those from A.
    """
    pred = {
        "A": {},  # source
        "B": {"A": ["edgeAB"]},
        "C": {"A": ["edgeAC"]},
        "D": {"B": ["edgeBD1", "edgeBD2"], "C": ["edgeCD"]},
    }
    # So potential paths from A to D:
    # 1) A->B->D (with edges edgeAB, plus one of [edgeBD1 or edgeBD2])
    # 2) A->C->D (with edges edgeAC, edgeCD)
    # Without parallel-edge splitting, multiple edges B->D are grouped
    paths_no_split = list(resolve_to_paths("A", "D", pred, split_parallel_edges=False))
    assert len(paths_no_split) == 2

    # With parallel-edge splitting, we expand B->D from 2 edges into 2 separate paths
    # plus 1 path from A->C->D = total 3.
    paths_split = list(resolve_to_paths("A", "D", pred, split_parallel_edges=True))
    assert len(paths_split) == 3


def test_parallel_edges_expansion():
    """
    Tests a single segment with multiple parallel edges: A->B has e1, e2, e3.
    No branching, just parallel edges.
    """
    pred = {
        "A": {},  # source
        "B": {"A": ["e1", "e2", "e3"]},
    }
    # Without split, there's a single path from A->B
    paths_no_split = list(resolve_to_paths("A", "B", pred, split_parallel_edges=False))
    assert len(paths_no_split) == 1
    expected_no_split = (
        ("A", ("e1", "e2", "e3")),
        ("B", ()),
    )
    assert paths_no_split[0] == expected_no_split

    # With split, we get 3 expansions: one for e1, one for e2, one for e3
    paths_split = list(resolve_to_paths("A", "B", pred, split_parallel_edges=True))
    assert len(paths_split) == 3
    # They should be:
    #  1) (A, (e1,)), (B, ())
    #  2) (A, (e2,)), (B, ())
    #  3) (A, (e3,)), (B, ())
    actual = set(paths_split)
    expected_variants = {
        (("A", ("e1",)), ("B", ())),
        (("A", ("e2",)), ("B", ())),
        (("A", ("e3",)), ("B", ())),
    }
    assert actual == expected_variants


def test_cycle_prevention():
    """
    Although the code assumes a DAG, we test a scenario with an actual cycle to
    ensure it doesn't loop infinitely. We'll see if 'seen' set logic works properly.
    A -> B -> A is a cycle, plus B -> C is normal. We want at least one path from A->C.
    The code might yield duplicates if it partially re-traverses; we only check
    that at least the main path is produced (A->B->C).
    """
    pred = {
        "A": {"B": ["edgeBA"]},  # cycle part
        "B": {"A": ["edgeAB"]},  # cycle part
        "C": {"B": ["edgeBC"]},
    }
    # Even though there's a cycle A <-> B, let's confirm we find at least one path A->B->C
    paths = list(resolve_to_paths("A", "C", pred))
    # The code might produce duplicates because each partial stack expansion can yield a path.
    # We'll just check that we do have the correct path at least once.
    assert len(paths) >= 1, "Expected at least one path, found none."

    # Check that the main path is in the results
    expected = (
        ("A", ("edgeAB",)),
        ("B", ("edgeBC",)),
        ("C", ()),
    )
    assert expected in paths, "Missing the main path from A->B->C"


def test_no_predecessors_for_dst():
    """
    If the dst_node is in pred but has an empty dict of predecessors,
    it means there's no actual incoming edge. Should yield no results.
    """
    pred = {
        "A": {},  # Suppose A is source, but not relevant here
        "C": {},  # 'C' was discovered in SPF's node set, but no predecessors
    }
    paths = list(resolve_to_paths("A", "C", pred))
    assert paths == [], "Expected no paths since 'C' has no incoming edges."


def test_multiple_path_expansions():
    """
    A more complex scenario with parallel edges at multiple steps:
        A -> B has e1, e2
        B -> C has e3, e4
        C -> D has e5
    So from A to D (via B, C), we get expansions for each combination
    of (e1 or e2) and (e3 or e4). 2 x 2 = 4 expansions if split_parallel_edges=True.
    """
    pred = {
        "A": {},  # source
        "B": {"A": ["e1", "e2"]},
        "C": {"B": ["e3", "e4"]},
        "D": {"C": ["e5"]},
    }
    # With no splitting, each set of parallel edges is collapsed into one path
    no_split = list(resolve_to_paths("A", "D", pred, split_parallel_edges=False))
    assert len(no_split) == 1

    # With splitting
    split = list(resolve_to_paths("A", "D", pred, split_parallel_edges=True))
    # We expect 4 expansions: (e1,e3), (e1,e4), (e2,e3), (e2,e4)
    assert len(split) == 4

    # Let's check the final shape of one of them:
    # For example, (("A", ("e1",)), ("B", ("e3",)), ("C", ("e5",)), ("D", ()))
    # And similarly for the others.
    expected_combos = {
        ("e1", "e3", "e5"),
        ("e1", "e4", "e5"),
        ("e2", "e3", "e5"),
        ("e2", "e4", "e5"),
    }
    actual_combos = set()
    for path in split:
        # path looks like (("A",(eX,)), ("B",(eY,)), ("C",(e5,)), ("D",()))
        edges_used = tuple(elem[1][0] for elem in path[:-1])  # omit the final empty
        actual_combos.add(edges_used)
    assert actual_combos == expected_combos
