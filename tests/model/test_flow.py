"""Named capacity questions on prepared physical topologies."""

import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.units import UnitsSettings
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare


def _network(nodes, links):
    network = Network(nodes={name: Node(name) for name in nodes})
    for source, target, amount in links:
        network.add_link(Link(source, target, amount, 1))
    return network


def _prepared(network):
    return prepare(Scenario(network, units=UnitsSettings(1)))


class TestMaxFlow:
    def test_max_flow_simple(self):
        prepared = _prepared(_network(("A", "B", "C"), (("A", "B", 5), ("B", "C", 3))))
        result = capacity(
            prepared, CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1)
        )
        (row,) = result.cases[0].states["converged"].rows
        assert row.endpoints.sources == ("A",) and row.endpoints.destinations == ("C",)
        assert row.result.delivered == 3

    def test_max_flow_multi_parallel(self):
        prepared = _prepared(
            _network(
                ("A", "B", "C", "D"),
                (("A", "B", 5), ("B", "C", 5), ("A", "D", 5), ("D", "C", 5)),
            )
        )
        result = capacity(
            prepared, CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1)
        )
        assert result.cases[0].states["converged"].rows[0].result.delivered == 10

    def test_max_flow_no_source(self):
        prepared = _prepared(_network(("B", "C"), (("B", "C", 10),)))
        with pytest.raises(ValueError, match="source.*empty|no source"):
            capacity(
                prepared, CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1)
            )
        assert (
            capacity(
                prepared, CapacityQuery(Selector("^B$"), Selector("^C$"), workers=1)
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 10
        )

    def test_max_flow_no_sink(self):
        prepared = _prepared(_network(("A", "B"), (("A", "B", 10),)))
        with pytest.raises(ValueError, match="target.*empty|no target"):
            capacity(
                prepared, CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1)
            )
        assert (
            capacity(
                prepared, CapacityQuery(Selector("^A$"), Selector("^B$"), workers=1)
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 10
        )

    def test_max_flow_with_attribute_grouping_combine(self):
        network = _network(("S1", "S2", "T1"), (("S1", "T1", 5), ("S2", "T1", 3)))
        for name in ("S1", "S2"):
            network.replace_node(name, attrs={"src_group": "src"})
        network.replace_node("T1", attrs={"dst_group": "dst"})
        result = capacity(
            _prepared(network),
            CapacityQuery(
                Selector(group_by="src_group"),
                Selector(group_by="dst_group"),
                workers=1,
            ),
        )
        (row,) = result.cases[0].states["converged"].rows
        assert row.endpoints.sources == ("S1", "S2") and row.endpoints.destinations == (
            "T1",
        )
        assert row.result.delivered == 8

    def test_max_flow_with_mixed_attr_and_regex(self):
        network = _network(("S1", "S2", "T1", "T2"), (("S1", "T1", 2), ("S2", "T2", 3)))
        for name in ("S1", "S2"):
            network.replace_node(name, attrs={"role": "edge"})
        result = capacity(
            _prepared(network),
            CapacityQuery(
                Selector(group_by="role"),
                Selector(r"^T\d$", group_by="name"),
                mode="pairwise",
                workers=1,
            ),
        )
        rows = result.cases[0].states["converged"].rows
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.result.delivered)
            for row in rows
        ] == [(("S1", "S2"), ("T1",), 2), (("S1", "S2"), ("T2",), 3)]

    def test_max_flow_overlap_detection_coverage(self):
        prepared = _prepared(_network(("A", "B", "C"), (("A", "B", 5), ("B", "C", 3))))
        with pytest.raises(ValueError, match="overlap.*B"):
            capacity(
                prepared,
                CapacityQuery(Selector("^[AB]$"), Selector("^[BC]$"), workers=1),
            )
        assert (
            capacity(
                prepared, CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1)
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 3
        )

    def test_max_flow_disabled_nodes_coverage(self):
        network = _network(("A", "B", "C"), (("A", "B", 10), ("B", "C", 10)))
        network.disable_node("A")
        with pytest.raises(ValueError, match="source.*empty|no source"):
            capacity(
                _prepared(network),
                CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1),
            )
        network.enable_node("A")
        assert (
            capacity(
                _prepared(network),
                CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1),
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 10
        )

    def test_max_flow_disabled_link_coverage(self):
        network = _network(("A", "B", "C"), (("A", "B", 10), ("B", "C", 10)))
        network.disable_link("A|B|0")
        result = capacity(
            _prepared(network),
            CapacityQuery(Selector("^A$"), Selector("^C$"), workers=1),
        )
        assert result.cases[0].states["converged"].rows[0].result.delivered == 0


class TestMaxFlowPairwise:
    def test_pairwise_mode_basic(self):
        prepared = _prepared(
            _network(("S1", "S2", "T1", "T2"), (("S1", "T1", 5), ("S2", "T2", 3)))
        )
        result = capacity(
            prepared,
            CapacityQuery(
                Selector(r"^(S\d)$"), Selector(r"^(T\d)$"), mode="pairwise", workers=2
            ),
        )
        rows = result.cases[0].states["converged"].rows
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.result.delivered)
            for row in rows
        ] == [
            (("S1",), ("T1",), 5),
            (("S1",), ("T2",), 0),
            (("S2",), ("T1",), 0),
            (("S2",), ("T2",), 3),
        ]

    def test_pairwise_with_shared_intermediate(self):
        prepared = _prepared(
            _network(
                ("S1", "S2", "X", "T1", "T2"),
                (("S1", "X", 10), ("S2", "X", 10), ("X", "T1", 5), ("X", "T2", 5)),
            )
        )
        result = capacity(
            prepared,
            CapacityQuery(
                Selector(r"^(S\d)$"), Selector(r"^(T\d)$"), mode="pairwise", workers=2
            ),
        )
        rows = result.cases[0].states["converged"].rows
        assert len(rows) == 4 and all(row.result.delivered == 5 for row in rows)


class TestMaxFlowCombine:
    def test_combine_mode_aggregates(self):
        prepared = _prepared(
            _network(
                ("S1", "S2", "X", "T1", "T2"),
                (("S1", "X", 5), ("S2", "X", 5), ("X", "T1", 5), ("X", "T2", 5)),
            )
        )
        (row,) = (
            capacity(
                prepared,
                CapacityQuery(Selector(r"^(S\d)$"), Selector(r"^(T\d)$"), workers=1),
            )
            .cases[0]
            .states["converged"]
            .rows
        )
        assert row.endpoints.sources == ("S1", "S2") and row.endpoints.destinations == (
            "T1",
            "T2",
        )
        assert row.result.delivered == 10


class TestExclusions:
    @pytest.mark.parametrize("scope,path", [("node", "^B$"), ("link", r"^A\|B$")])
    def test_exclude_node_or_link(self, scope, path):
        prepared = _prepared(
            _network(
                ("A", "B", "C", "D"),
                (("A", "B", 5), ("B", "D", 5), ("A", "C", 3), ("C", "D", 3)),
            )
        )
        policy = FailurePolicy(modes=[FailureMode(1, [FailureRule(scope, path=path)])])
        result = capacity(
            prepared,
            CapacityQuery(
                Selector("^A$"),
                Selector("^D$"),
                failures=FailureRequest(policy, 1, 42),
                workers=2,
            ),
        )
        assert [
            case.states["converged"].rows[0].result.delivered for case in result.cases
        ] == [8, 3]


class TestPreparedRepeat:
    def test_repeated_cases(self):
        prepared = _prepared(
            _network(
                ("A", "B", "C", "D"),
                (("A", "B", 5), ("B", "D", 5), ("A", "C", 3), ("C", "D", 3)),
            )
        )
        query = CapacityQuery(Selector("^A$"), Selector("^D$"), workers=1)
        assert (
            capacity(prepared, query)
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 8
        )
        for name, expected in (("B", 3), ("C", 5)):
            policy = FailurePolicy(
                modes=[FailureMode(1, [FailureRule("node", path=f"^{name}$")])]
            )
            result = capacity(
                prepared,
                CapacityQuery(
                    Selector("^A$"),
                    Selector("^D$"),
                    failures=FailureRequest(policy, 1, 42),
                    workers=1,
                ),
            )
            assert (
                result.cases[1].states["converged"].rows[0].result.delivered == expected
            )
        assert (
            capacity(prepared, query)
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 8
        )
