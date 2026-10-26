"""A provisional link cannot change identity in a prepared snapshot."""

import pytest

from ngraph import Link, Network, Node, Scenario, prepare


@pytest.mark.parametrize("insert_later", [False, True])
def test_snapshot_owns_a_link_whose_identity_is_still_provisional(insert_later):
    link = Link("a", "b", 100)
    original = link.id
    n = Network(
        nodes={s: Node(s) for s in ("a", "b")},
        links={} if insert_later else {original: link},
    )
    if insert_later:
        n.links[original] = link
    p = prepare(Scenario(n))
    frozen = p.scenario.network.links[original]
    other = Network(nodes=dict(n.nodes))
    other.add_link(link)
    assert link.id == "a|b|0"
    assert frozen.id == original
    assert tuple(p.scenario.network.links) == (original,)
    assert p.topology.edges_by_link.keys() == {original}
    again = prepare(p.scenario)
    assert tuple(again.scenario.network.links) == (original,)
    assert again.scenario.network.links[original].id == original
    with pytest.raises(ValueError, match="already been added"):
        other.add_link(frozen)


def test_snapshot_link_mapping_remains_read_only():
    n = Network(nodes={s: Node(s) for s in ("a", "b")})
    n.add_link(Link("a", "b", 10))
    p = prepare(Scenario(n))
    with pytest.raises(TypeError):
        p.scenario.network.links["a|b|0"] = Link("a", "b", 20)
    assert p.scenario.network.links["a|b|0"].capacity == 10


def test_snapshot_metadata_is_owned_and_read_only_alongside_link_records():
    n = Network(attrs={"nested": {"answer": 1}})
    frozen = n.snapshot()
    n.attrs["nested"]["answer"] = 2
    assert frozen.attrs["nested"]["answer"] == 1
    with pytest.raises(TypeError):
        frozen.attrs["nested"]["answer"] = 3
