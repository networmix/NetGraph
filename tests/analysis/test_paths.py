"""Public path selection, native path values and declared cross-pair ordering."""

import os
import subprocess
import sys
import textwrap
from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.paths import PathQuery, paths
from ngraph.analysis.units import UnitsSettings
from ngraph.model.network import Network, Node
from ngraph.model.selectors import Condition, MatchSpec, Selector
from ngraph.scenario import Scenario, prepare
from tests.placement_fixture import network_of


def _prepare(network):
    return prepare(Scenario(network, units=UnitsSettings(1)))


def _simple_path_network():
    return network_of([("A", "B", 10, 1), ("B", "C", 10, 1), ("A", "C", 10, 3)])


def _group_network():
    network = network_of(
        [("A", "X", 10, 1), ("X", "B", 10, 1), ("A", "Y", 10, 2), ("Y", "B", 10, 2)]
    )
    network.replace_node("A", attrs={"group": "src"})
    network.replace_node("B", attrs={"group": "dst"})
    return network


def _multi_source_sink_network():
    network = network_of(
        [("A", "X", 10, 1), ("B", "X", 10, 2), ("X", "C", 10, 1), ("X", "D", 10, 2)]
    )
    for name in ("A", "B", "C", "D"):
        network.replace_node(
            name, attrs={"group": "src" if name in ("A", "B") else "dst"}
        )
    return network


def _group_selector(group):
    return Selector(
        group_by="group", match=MatchSpec([Condition("group", "==", group)])
    )


def _row(
    prepared,
    *,
    source=None,
    target=None,
    k=None,
    costs_only=False,
    mode="combine",
    ceiling=None,
    nodes=(),
    links=(),
):
    topology = prepared.topology
    mask = topology.graph.eligibility(
        excluded_nodes=[topology.node_id_by_name[name] for name in nodes],
        excluded_edges=[
            edge for name in links for edge in topology.edges_by_link[name]
        ],
    )
    options = (
        ngc.SpfOptions(ngc.Direction.FORWARD, eligibility=mask)
        if k is None
        else ngc.KspOptions(k, cost_ceiling=ceiling, eligibility=mask)
    )
    return paths(
        prepared,
        PathQuery(
            source or Selector("^A$"),
            target or Selector("^C$"),
            mode=mode,
            options=options,
            costs_only=costs_only,
        ),
    ).rows[0]


def _node_sequence(prepared, path):
    names = [prepared.topology.node_names[path.source()]]
    for hop in path.hops():
        ref = prepared.topology.edge_refs[hop[0]]
        source, target, _ = ref.link.split("|")
        names.append(target if ref.direction == "forward" else source)
    return tuple(names)


class TestShortestPathCosts:
    def test_pairwise_mode(self):
        prepared = _prepare(_multi_source_sink_network())
        row = _row(
            prepared,
            source=_group_selector("src"),
            target=_group_selector("dst"),
            mode="pairwise",
            costs_only=True,
        )
        assert row.endpoints.sources == ("A", "B") and row.endpoints.destinations == (
            "C",
            "D",
        )
        assert row.cost == 2 and row.paths is None

    def test_combine_mode(self):
        row = _row(_prepare(_simple_path_network()), costs_only=True)
        assert row.cost == 2 and row.paths is None

    def test_no_path_returns_none(self):
        row = _row(
            _prepare(Network(nodes={name: Node(name) for name in "AC"})),
            costs_only=True,
        )
        assert row.cost is None and row.paths is None

    def test_excluded_nodes(self):
        prepared = _prepare(_simple_path_network())
        assert _row(prepared, costs_only=True, nodes=("B",)).cost == 3
        assert _row(prepared, costs_only=True).cost == 2


class TestShortestPaths:
    def test_returns_native_path_objects(self):
        prepared = _prepare(_simple_path_network())
        row = _row(prepared)
        assert len(row.paths) == 1 and isinstance(row.paths[0], ngc.Path)
        assert row.paths[0].cost() == row.cost == 2
        assert row.paths[0].graph_uid() == prepared.topology.graph.uid()
        assert _node_sequence(prepared, row.paths[0]) == ("A", "B", "C")

    def test_combine_mode_paths(self):
        prepared = _prepare(_group_network())
        row = _row(
            prepared, source=_group_selector("src"), target=_group_selector("dst")
        )
        assert row.cost == 2 and [
            _node_sequence(prepared, path) for path in row.paths
        ] == [("A", "X", "B")]

    def test_pairwise_mode_paths(self):
        prepared = _prepare(_multi_source_sink_network())
        value = paths(
            prepared,
            PathQuery(
                Selector("^[AB]$", group_by="name"),
                Selector("^[CD]$", group_by="name"),
                mode="pairwise",
            ),
        )
        assert [
            (row.endpoints.sources[0], row.endpoints.destinations[0], row.cost)
            for row in value.rows
        ] == [("A", "C", 2), ("A", "D", 3), ("B", "C", 3), ("B", "D", 4)]
        assert [_node_sequence(prepared, row.paths[0]) for row in value.rows] == [
            ("A", "X", "C"),
            ("A", "X", "D"),
            ("B", "X", "C"),
            ("B", "X", "D"),
        ]

    def test_path_contains_named_edge_references(self):
        prepared = _prepare(_simple_path_network())
        (path,) = _row(prepared).paths
        refs = [prepared.topology.edge_refs[hop[0]] for hop in path.hops()]
        assert [(ref.link, ref.direction) for ref in refs] == [
            ("A|B|0", "forward"),
            ("B|C|0", "forward"),
        ]
        assert _node_sequence(prepared, path) == ("A", "B", "C")


def _multi_member_group_network():
    return network_of(
        [
            ("x1", "y1", 10, 10),
            ("x2", "y2", 10, 11),
            ("x1", "m", 10, 5),
            ("m", "y1", 10, 10),
        ]
    )


def _tie_network():
    return network_of(
        [
            (source, middle, 10, 1)
            for source in ("S1", "S2")
            for middle in ("M1", "M2", "M3")
        ]
        + [
            (middle, target, 10, 1)
            for middle in ("M1", "M2", "M3")
            for target in ("T1", "T2")
        ]
    )


class TestKShortestPaths:
    def test_returns_multiple_paths(self):
        prepared = _prepare(_simple_path_network())
        row = _row(prepared, k=3, mode="pairwise")
        assert [path.cost() for path in row.paths] == [2, 3]
        assert [_node_sequence(prepared, path) for path in row.paths] == [
            ("A", "B", "C"),
            ("A", "C"),
        ]

    def test_k_limits_paths(self):
        row = _row(_prepare(_simple_path_network()), k=1)
        assert len(row.paths) == 1 and row.paths[0].cost() == 2

    def test_combine_mode(self):
        prepared = _prepare(_group_network())
        row = _row(
            prepared, source=_group_selector("src"), target=_group_selector("dst"), k=3
        )
        assert [path.cost() for path in row.paths] == [2, 4]

    def test_excluded_nodes(self):
        prepared = _prepare(_simple_path_network())
        row = _row(prepared, k=2, nodes=("B",))
        assert [path.cost() for path in row.paths] == [3]
        assert [path.cost() for path in _row(prepared, k=2).paths] == [2, 3]

    def test_exact_inclusive_cost_stretch(self):
        prepared = _prepare(_simple_path_network())
        assert [
            path.cost()
            for path in _row(
                prepared, k=5, ceiling=ngc.CostStretch(Fraction(3, 2))
            ).paths
        ] == [2, 3]
        assert [
            path.cost()
            for path in _row(
                prepared, k=5, ceiling=ngc.CostStretch(Fraction(149, 100))
            ).paths
        ] == [2]

    @pytest.mark.parametrize(
        "k,ceiling,expected",
        [
            (2, None, [10, 11]),
            (5, None, [10, 11, 15]),
            (5, ngc.CostStretch(Fraction(6, 5)), [10, 11]),
        ],
    )
    def test_multi_node_groups_merge_all_pairs(self, k, ceiling, expected):
        prepared = _prepare(_multi_member_group_network())
        row = _row(
            prepared, source=Selector("^x"), target=Selector("^y"), k=k, ceiling=ceiling
        )
        assert [path.cost() for path in row.paths] == expected

    def test_many_pairs_keep_global_top_k(self):
        network = network_of(
            [(f"A{i}", "X", 10, i + 1) for i in range(10)]
            + [("X", f"B{i}", 10, (i + 1) * 100) for i in range(10)]
        )
        prepared = _prepare(network)
        row = _row(prepared, source=Selector("^A"), target=Selector("^B"), k=3)
        assert [path.cost() for path in row.paths] == [101, 102, 103]
        assert [_node_sequence(prepared, path) for path in row.paths] == [
            ("A0", "X", "B0"),
            ("A1", "X", "B0"),
            ("A2", "X", "B0"),
        ]

    def test_equal_cost_truncation_uses_pair_ordinal_then_native_rank(self):
        for _ in range(2):
            prepared = _prepare(_tie_network())
            row = _row(prepared, source=Selector("^S"), target=Selector("^T"), k=3)
            assert [_node_sequence(prepared, path) for path in row.paths] == [
                ("S1", "M1", "T1"),
                ("S1", "M2", "T1"),
                ("S1", "M3", "T1"),
            ]

    def test_equal_cost_truncation_stable_across_hash_seeds(self):
        script = textwrap.dedent("""
            from ngraph.analysis.paths import PathQuery, paths
            from ngraph.model.selectors import Selector
            from tests.analysis.test_paths import _prepare, _tie_network, _node_sequence
            import netgraph_core as ngc
            prepared = _prepare(_tie_network())
            result = paths(prepared, PathQuery(Selector('^S'), Selector('^T'), options=ngc.KspOptions(3)))
            print([_node_sequence(prepared, path) for path in result.rows[0].paths])
        """)
        outputs = []
        for seed in ("1", "42"):
            result = subprocess.run(
                [sys.executable, "-c", script],
                env=dict(os.environ, PYTHONHASHSEED=seed),
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            outputs.append(result.stdout.strip())
        assert (
            outputs
            == ["[('S1', 'M1', 'T1'), ('S1', 'M2', 'T1'), ('S1', 'M3', 'T1')]"] * 2
        )


class TestTypedSelectors:
    def test_cost_with_grouping(self):
        prepared = _prepare(_multi_source_sink_network())
        assert (
            _row(
                prepared,
                source=_group_selector("src"),
                target=_group_selector("dst"),
                costs_only=True,
                mode="pairwise",
            ).cost
            == 2
        )

    def test_paths_with_match_conditions(self):
        prepared = _prepare(_multi_source_sink_network())
        row = _row(
            prepared, source=_group_selector("src"), target=_group_selector("dst")
        )
        assert [_node_sequence(prepared, path) for path in row.paths] == [
            ("A", "X", "C")
        ]

    def test_ksp_with_grouping(self):
        prepared = _prepare(_group_network())
        assert [
            path.cost()
            for path in _row(
                prepared,
                source=_group_selector("src"),
                target=_group_selector("dst"),
                k=3,
            ).paths
        ] == [2, 4]

    def test_no_route_is_empty(self):
        prepared = _prepare(Network(nodes={name: Node(name) for name in "AC"}))
        row = _row(prepared, k=3, mode="pairwise")
        assert row.cost is None and row.paths == ()


class TestPathExclusions:
    def test_excluded_links_in_shortest_path(self):
        prepared = _prepare(_simple_path_network())
        assert _row(prepared, links=("A|B|0",)).cost == 3
        assert _row(prepared).cost == 2

    def test_disabled_node_in_network(self):
        network = _simple_path_network()
        network.disable_node("B")
        assert _row(_prepare(network)).cost == 3
        network.enable_node("B")
        assert _row(_prepare(network)).cost == 2


class TestPreparedPathReuse:
    def test_repeated_costs(self):
        prepared = _prepare(_simple_path_network())
        assert [_row(prepared, costs_only=True).cost for _ in range(2)] == [2, 2]

    def test_repeated_costs_with_exclusions(self):
        prepared = _prepare(_simple_path_network())
        assert [
            _row(prepared, costs_only=True, nodes=nodes).cost
            for nodes in ((), ("B",), ())
        ] == [2, 3, 2]

    def test_repeated_shortest_paths(self):
        prepared = _prepare(_simple_path_network())
        for _ in range(2):
            assert [
                _node_sequence(prepared, path) for path in _row(prepared).paths
            ] == [("A", "B", "C")]

    def test_repeated_ksp(self):
        prepared = _prepare(_simple_path_network())
        for _ in range(2):
            assert [path.cost() for path in _row(prepared, k=3).paths] == [2, 3]

    def test_native_graph_counts(self):
        prepared = _prepare(_simple_path_network())
        assert prepared.topology.graph.num_nodes() == 3
        assert prepared.topology.graph.num_edges() == 6


def test_a_path_query_takes_no_explicit_pairs():
    from ngraph.analysis.paths import PathQuery
    from ngraph.model.selectors import Selector

    assert PathQuery(Selector("^a$"), Selector("^b$")).mode == "combine"
    with pytest.raises(TypeError, match="unexpected keyword argument 'pairs'"):
        PathQuery(Selector("^a$"), Selector("^b$"), pairs=(("a", "b"),))  # type: ignore[call-arg]
