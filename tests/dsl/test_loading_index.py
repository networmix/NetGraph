"""Link-rule order and the lifetime of node selections during DSL expansion."""

import gc
import weakref

import pytest
import yaml

from ngraph import Scenario
from ngraph.dsl.blueprints.expand import (
    _LinkRuleIndex,
    _NodeSelection,
    _process_link_rules,
    expand_network_dsl,
)
from ngraph.model.network import Link, Network, Node
from ngraph.model.risk import MembershipIndex
from ngraph.model.selectors import Selector, normalize_selector, select_nodes


def match(attr, value):
    return {"conditions": [{"attr": attr, "op": "==", "value": value}]}


def test_parallel_link_rules_read_current_records_in_insertion_order(monkeypatch):
    net = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    for source, target, lane in (("A", "B", 0), ("C", "A", 2), ("A", "B", 1)):
        net.add_link(Link(source, target, attrs={"lane": lane, "nested": {"old": 1}}))
    trace = []
    original = Network.replace_link

    def replace(self, link_id, **changes):
        trace.append(link_id)
        return original(self, link_id, **changes)

    monkeypatch.setattr(Network, "replace_link", replace)
    _process_link_rules(
        net,
        {
            "link_rules": [
                {
                    "source": "A",
                    "target": "B",
                    "link_match": match("lane", 1),
                    "attrs": {"mark": "first", "nested": {"new": 2}},
                    "capacity": 0,
                    "disabled": True,
                    "risk_groups": ["old"],
                },
                {
                    "source": "B",
                    "target": "A",
                    "link_match": match("mark", "first"),
                    "attrs": {"mark": "last"},
                    "disabled": False,
                    "risk_groups": ["new"],
                },
                {"source": ".*", "target": ".*", "attrs": {"all": True}},
            ]
        },
        selection=_NodeSelection(net),
    )
    ids = ["A|B|0", "C|A|0", "A|B|1"]
    assert list(net.links) == ids
    assert trace == ["A|B|1", "A|B|1", *ids]
    link = net.links["A|B|1"]
    assert (
        link.id,
        link.source,
        link.target,
        link.capacity,
        link.cost,
        link.disabled,
    ) == ("A|B|1", "A", "B", 0, 1, False)
    assert link.risk_groups == {"new"}
    assert link.attrs == {"lane": 1, "nested": {"new": 2}, "mark": "last", "all": True}
    assert net.links["A|B|0"].attrs == {"lane": 0, "nested": {"old": 1}, "all": True}


def test_overlap_self_and_direction_apply_each_link_once(monkeypatch):
    net = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    for source, target in (("A", "B"), ("A", "A"), ("B", "A"), ("B", "C")):
        net.add_link(Link(source, target))
    trace = []
    original = Network.replace_link

    def replace(self, link_id, **changes):
        trace.append(link_id)
        return original(self, link_id, **changes)

    monkeypatch.setattr(Network, "replace_link", replace)
    _process_link_rules(
        net,
        {
            "link_rules": [
                {"source": "A|B", "target": "A|B", "cost": 2},
                {"source": "A", "target": "B", "bidirectional": False, "cost": 3},
            ]
        },
        selection=_NodeSelection(net),
    )
    assert trace == ["A|B|0", "A|A|0", "B|A|0", "A|B|0"]
    assert [link.cost for link in net.links.values()] == [3, 2, 2, 1]


def test_node_rules_finish_before_cached_deferred_and_top_level_links(monkeypatch):
    calls = []
    original = Network.select_node_groups_by_path

    def select(self, path):
        calls.append(path)
        return original(self, path)

    monkeypatch.setattr(Network, "select_node_groups_by_path", select)
    data = {
        "blueprints": {
            "pod": {
                "nodes": {"a": {}, "b": {}},
                "links": [{"source": "a", "target": "b"}],
            }
        },
        "network": {
            "nodes": {"P": {"blueprint": "pod"}},
            "node_rules": [
                {"path": "P/a", "attrs": {"role": "old"}},
                {
                    "path": "P/a",
                    "match": match("role", "old"),
                    "attrs": {"role": "new"},
                    "disabled": True,
                },
            ],
            "links": [
                {
                    "source": {"path": "P/a", "match": match("role", "new")},
                    "target": "P/b",
                }
            ],
            "link_rules": [
                {
                    "source": {"path": "P/a", "active_only": True},
                    "target": "P/b",
                    "cost": 9,
                },
                {"source": "P/a", "target": "P/b", "capacity": 3},
            ],
        },
    }
    net = expand_network_dsl(data)
    assert calls.count("P/a") == 3  # Two node rules, one shared post-rule lookup.
    assert calls.count("P/b") == 1
    assert net.nodes["P/a"].disabled and net.nodes["P/a"].attrs == {"role": "new"}
    assert list(net.links) == ["P/a|P/b|0", "P/a|P/b|1"]
    assert [(link.capacity, link.cost) for link in net.links.values()] == [
        (3, 1),
        (3, 1),
    ]


def test_cached_candidates_are_fresh_and_filters_are_per_selector():
    net = Network(
        nodes={
            "a1": Node("a1", attrs={"role": "edge"}),
            "a2": Node("a2", disabled=True, attrs={"role": "core"}),
        }
    )
    selection = _NodeSelection(net)
    first = selection.select(Selector("(a)(1)?"))
    assert {key: [node.name for node in nodes] for key, nodes in first.items()} == {
        "a|1": ["a1"],
        "a": ["a2"],
    }
    first["a"].clear()
    first.clear()
    again = selection.select(Selector("(a)(1)?"))
    assert len(again) == 2
    assert [node.name for node in again["a"]] == ["a2"]
    assert list(selection.select(Selector("^a", active_only=True))) == ["^a"]
    assert [
        node.name for node in selection.select(Selector("^a", active_only=True))["^a"]
    ] == ["a1"]
    grouped = selection.select(
        normalize_selector(
            {"path": "^a", "group_by": "role", "match": match("role", "core")},
            context="rule",
        )
    )
    assert {key: [node.name for node in nodes] for key, nodes in grouped.items()} == {
        "core": ["a2"]
    }
    assert selection.select(Selector("^missing$")) == {}
    assert selection.select(Selector("^missing$")) == {}


def test_rule_index_and_selection_do_not_survive_between_calls():
    net = Network(nodes={name: Node(name) for name in ("A", "B")})
    net.add_link(Link("A", "B"))
    rule = {"source": "A", "target": "B", "attrs": {"marked": True}}
    _process_link_rules(net, {"link_rules": [rule]}, selection=_NodeSelection(net))
    del net.links["A|B|0"]
    net.add_link(Link("B", "A"))
    net.nodes["A"] = Node("A", disabled=True)
    _process_link_rules(net, {"link_rules": [rule]}, selection=_NodeSelection(net))
    assert list(net.links) == ["B|A|0"]
    assert net.links["B|A|0"].attrs == {"marked": True}
    assert select_nodes(net, Selector("A", active_only=True), False) == {}
    other = expand_network_dsl(
        {"network": {"nodes": {"A": {"attrs": {"other": True}}}}}
    )
    assert select_nodes(other, Selector("A"), False)["A"][0].attrs == {"other": True}


def test_no_rule_builds_no_link_index(monkeypatch):
    def unexpected(self, network):
        raise AssertionError("index built without a link rule")

    monkeypatch.setattr(_LinkRuleIndex, "__init__", unexpected)
    net = Network()
    _process_link_rules(net, {}, selection=_NodeSelection(net))
    net = expand_network_dsl(
        {
            "network": {
                "nodes": {"A": {}, "B": {}},
                "links": [{"source": "A", "target": "B"}],
            }
        }
    )
    assert list(net.links) == ["A|B|0"]


def test_returned_network_does_not_retain_selection_cache(monkeypatch):
    caches = []
    original = _NodeSelection.__init__

    def init(self, network):
        original(self, network)
        caches.append(weakref.ref(self))

    monkeypatch.setattr(_NodeSelection, "__init__", init)
    net = expand_network_dsl(
        {
            "network": {
                "nodes": {"A": {}, "B": {}},
                "links": [{"source": "A", "target": "B"}],
            }
        }
    )
    gc.collect()
    assert caches and all(cache() is None for cache in caches)
    net.nodes["A"] = Node("A", attrs={"current": True})
    assert select_nodes(net, Selector("A"), False)["A"][0].attrs == {"current": True}


def test_membership_and_disable_cascade_read_final_link_rules():
    source = """
network:
  nodes: {A: {}, B: {}}
  links:
    - {source: A, target: B, attrs: {lane: 0}}
    - {source: A, target: B, attrs: {lane: 1}}
  link_rules:
    - {source: A, target: B, link_match: {conditions: [{attr: lane, op: '==', value: 0}]}, risk_groups: [old]}
    - {source: A, target: B, link_match: {conditions: [{attr: risk_groups, op: '==', value: [old]}]}, risk_groups: [child]}
risk_groups:
  - old
  - child
  - {name: parent, children: [child], disabled: true}
"""
    net = Scenario.from_yaml(source).network
    index = MembershipIndex.build(net)
    assert not index.members("old", recursive=True).links
    assert index.members("child", recursive=False).links == {"A|B|0"}
    assert index.members("parent", recursive=True).links == {"A|B|0"}
    assert index.link_groups["A|B|0"] == {"child"}
    assert [link.disabled for link in net.links.values()] == [True, False]
    assert [link.risk_groups for link in net.links.values()] == [
        frozenset({"child"}),
        frozenset(),
    ]


@pytest.mark.parametrize(
    "rule,message",
    [
        (
            {"source": "absent", "target": "B", "cost": 0},
            "cost",
        ),
        ({"source": "[", "target": "B"}, "source.path"),
        (
            {
                "source": "absent",
                "target": "B",
                "link_match": {
                    "conditions": [{"attr": "x", "op": "wrong", "value": 1}]
                },
            },
            "op",
        ),
    ],
)
def test_empty_candidates_do_not_skip_rule_validation(rule, message):
    net = Network()
    with pytest.raises(ValueError, match=message):
        _process_link_rules(net, {"link_rules": [rule]}, selection=_NodeSelection(net))
    _process_link_rules(
        net,
        {"link_rules": [{"source": "absent", "target": "B", "cost": 1}]},
        selection=_NodeSelection(net),
    )


def test_expanded_parallel_rules_replace_nested_values():
    source = {
        "network": {
            "nodes": {"A": {}, "B": {}},
            "links": [
                {
                    "source": "A",
                    "target": "B",
                    "expand": {"vars": {"v": [0, 1]}},
                    "attrs": {"lane": "${v}"},
                }
            ],
            "link_rules": [
                {
                    "source": "A",
                    "target": "B",
                    "expand": {"vars": {"v": [0, 1]}},
                    "link_match": match("lane", "${v}"),
                    "attrs": {"nested": {"value": "${v}"}},
                }
            ],
        }
    }
    net = Scenario.from_yaml(yaml.safe_dump(source, sort_keys=False)).network
    assert list(net.links) == ["A|B|0", "A|B|1"]
    assert [link.attrs for link in net.links.values()] == [
        {"lane": 0, "nested": {"value": 0}},
        {"lane": 1, "nested": {"value": 1}},
    ]
