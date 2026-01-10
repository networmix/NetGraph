"""Tests for enhanced rule selector support in link_rules and node_rules.

Tests that:
- link_rules supports full selectors (path + match) for source/target
- link_rules supports link_match for filtering by link attributes
- node_rules supports match conditions for filtering by node attributes
"""

import pytest

from ngraph.dsl.blueprints.expand import (
    _process_link_rules,
    _process_node_rules,
    expand_network_dsl,
)
from ngraph.model.network import Link, Network, Node

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def network_with_roles() -> Network:
    """Create a network with nodes having role attributes and links with costs."""
    net = Network()

    # Spine nodes
    net.add_node(Node("spine_1", attrs={"role": "spine", "tier": 2}))
    net.add_node(Node("spine_2", attrs={"role": "spine", "tier": 2}))

    # Leaf nodes
    net.add_node(Node("leaf_1", attrs={"role": "leaf", "tier": 1}))
    net.add_node(Node("leaf_2", attrs={"role": "leaf", "tier": 1}))
    net.add_node(Node("leaf_3", attrs={"role": "leaf", "tier": 1}))

    # Links with varying capacities
    net.add_link(Link(source="spine_1", target="leaf_1", capacity=100, cost=1))
    net.add_link(Link(source="spine_1", target="leaf_2", capacity=50, cost=2))
    net.add_link(Link(source="spine_1", target="leaf_3", capacity=100, cost=1))
    net.add_link(Link(source="spine_2", target="leaf_1", capacity=100, cost=1))
    net.add_link(Link(source="spine_2", target="leaf_2", capacity=100, cost=1))
    net.add_link(Link(source="spine_2", target="leaf_3", capacity=50, cost=2))

    return net


# ──────────────────────────────────────────────────────────────────────────────
# link_rules Full Selector Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestLinkRulesFullSelectors:
    """Tests for full selector support in link_rules source/target."""

    def test_link_rules_string_selector_still_works(
        self, network_with_roles: Network
    ) -> None:
        """String selectors in link_rules still work (backward compatible)."""
        scenario = {
            "network": {
                "nodes": {},
                "links": [],
                "link_rules": [
                    {
                        "source": "spine_1",
                        "target": "leaf_.*",
                        "capacity": 200,
                    }
                ],
            }
        }

        # Apply rules to existing network
        _process_link_rules(network_with_roles, scenario["network"])

        # Links from spine_1 should have updated capacity
        spine1_links = [
            link
            for link in network_with_roles.links.values()
            if link.source == "spine_1"
        ]
        assert all(link.capacity == 200 for link in spine1_links)

        # Links from spine_2 should be unchanged
        spine2_links = [
            link
            for link in network_with_roles.links.values()
            if link.source == "spine_2"
        ]
        assert any(link.capacity == 100 for link in spine2_links)

    def test_link_rules_dict_selector_with_match(
        self, network_with_roles: Network
    ) -> None:
        """Dict selectors with match conditions work in link_rules."""
        scenario = {
            "network": {
                "link_rules": [
                    {
                        "source": {
                            "path": ".*",
                            "match": {
                                "conditions": [
                                    {"attr": "role", "op": "==", "value": "spine"}
                                ]
                            },
                        },
                        "target": {
                            "path": ".*",
                            "match": {
                                "conditions": [
                                    {"attr": "role", "op": "==", "value": "leaf"}
                                ]
                            },
                        },
                        "attrs": {"tagged": True},
                    }
                ],
            }
        }

        _process_link_rules(network_with_roles, scenario["network"])

        # All spine->leaf links should have the 'tagged' attr
        for link in network_with_roles.links.values():
            src_node = network_with_roles.nodes[link.source]
            tgt_node = network_with_roles.nodes[link.target]
            if (
                src_node.attrs.get("role") == "spine"
                and tgt_node.attrs.get("role") == "leaf"
            ):
                assert link.attrs.get("tagged") is True


# ──────────────────────────────────────────────────────────────────────────────
# link_match Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestLinkMatch:
    """Tests for link_match filtering in link_rules."""

    def test_link_match_filters_by_capacity(self, network_with_roles: Network) -> None:
        """link_match filters links by their own attributes (capacity)."""
        scenario = {
            "network": {
                "link_rules": [
                    {
                        "source": ".*",
                        "target": ".*",
                        "link_match": {
                            "conditions": [
                                {"attr": "capacity", "op": "<", "value": 100}
                            ]
                        },
                        "risk_groups": ["low_capacity"],
                    }
                ],
            }
        }

        _process_link_rules(network_with_roles, scenario["network"])

        # Only links with capacity < 100 should have risk_groups
        for link in network_with_roles.links.values():
            if link.capacity < 100:
                assert "low_capacity" in link.risk_groups
            else:
                assert "low_capacity" not in link.risk_groups

    def test_link_match_filters_by_cost(self, network_with_roles: Network) -> None:
        """link_match filters links by cost attribute."""
        scenario = {
            "network": {
                "link_rules": [
                    {
                        "source": ".*",
                        "target": ".*",
                        "link_match": {
                            "conditions": [{"attr": "cost", "op": ">", "value": 1}]
                        },
                        "disabled": True,
                    }
                ],
            }
        }

        _process_link_rules(network_with_roles, scenario["network"])

        # Only links with cost > 1 should be disabled
        for link in network_with_roles.links.values():
            if link.cost > 1:
                assert link.disabled is True
            else:
                assert link.disabled is False

    def test_link_match_combined_with_endpoint_selectors(
        self, network_with_roles: Network
    ) -> None:
        """link_match works with endpoint selectors."""
        scenario = {
            "network": {
                "link_rules": [
                    {
                        "source": "spine_1",
                        "target": "leaf_.*",
                        "link_match": {
                            "conditions": [
                                {"attr": "capacity", "op": "==", "value": 100}
                            ]
                        },
                        "attrs": {"high_cap_spine1": True},
                    }
                ],
            }
        }

        _process_link_rules(network_with_roles, scenario["network"])

        # Only spine_1 -> leaf_* links with capacity=100 should have the attr
        for link in network_with_roles.links.values():
            if (
                link.source == "spine_1"
                and link.target.startswith("leaf_")
                and link.capacity == 100
            ):
                assert link.attrs.get("high_cap_spine1") is True
            else:
                assert link.attrs.get("high_cap_spine1") is None


# ──────────────────────────────────────────────────────────────────────────────
# node_rules match Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestNodeRulesMatch:
    """Tests for match support in node_rules."""

    def test_node_rules_match_filters_by_attribute(
        self, network_with_roles: Network
    ) -> None:
        """node_rules match filters nodes by attribute conditions."""
        scenario = {
            "network": {
                "node_rules": [
                    {
                        "path": ".*",
                        "match": {
                            "conditions": [
                                {"attr": "role", "op": "==", "value": "spine"}
                            ]
                        },
                        "attrs": {"is_spine": True},
                    }
                ],
            }
        }

        _process_node_rules(network_with_roles, scenario["network"])

        # Only spine nodes should have the attr
        for node in network_with_roles.nodes.values():
            if node.attrs.get("role") == "spine":
                assert node.attrs.get("is_spine") is True
            else:
                assert node.attrs.get("is_spine") is None

    def test_node_rules_match_with_tier(self, network_with_roles: Network) -> None:
        """node_rules match works with numeric comparison."""
        scenario = {
            "network": {
                "node_rules": [
                    {
                        "path": ".*",
                        "match": {
                            "conditions": [{"attr": "tier", "op": "==", "value": 1}]
                        },
                        "risk_groups": ["edge_tier"],
                    }
                ],
            }
        }

        _process_node_rules(network_with_roles, scenario["network"])

        # Only tier 1 nodes should have risk_groups
        for node in network_with_roles.nodes.values():
            if node.attrs.get("tier") == 1:
                assert "edge_tier" in node.risk_groups
            else:
                assert "edge_tier" not in node.risk_groups

    def test_node_rules_path_and_match_combined(
        self, network_with_roles: Network
    ) -> None:
        """node_rules with both path and match applies both filters."""
        scenario = {
            "network": {
                "node_rules": [
                    {
                        "path": "leaf_.*",
                        "match": {
                            "conditions": [{"attr": "tier", "op": "==", "value": 1}]
                        },
                        "attrs": {"leaf_tier1": True},
                    }
                ],
            }
        }

        _process_node_rules(network_with_roles, scenario["network"])

        # Only leaf nodes with tier 1 should have the attr
        for node in network_with_roles.nodes.values():
            if node.name.startswith("leaf_") and node.attrs.get("tier") == 1:
                assert node.attrs.get("leaf_tier1") is True
            else:
                assert node.attrs.get("leaf_tier1") is None


# ──────────────────────────────────────────────────────────────────────────────
# Integration: Full Network Expansion with Rules
# ──────────────────────────────────────────────────────────────────────────────


class TestRulesIntegration:
    """Integration tests for rules with full network expansion."""

    def test_full_scenario_with_rules(self) -> None:
        """Full scenario with node_rules and link_rules works end-to-end."""
        scenario = {
            "network": {
                "nodes": {
                    "spine_[1-2]": {"count": 1, "attrs": {"role": "spine", "tier": 2}},
                    "leaf_[1-3]": {"count": 1, "attrs": {"role": "leaf", "tier": 1}},
                },
                "links": [{"source": "spine_.*", "target": "leaf_.*", "capacity": 100}],
                "node_rules": [
                    {
                        "path": ".*",
                        "match": {
                            "conditions": [
                                {"attr": "role", "op": "==", "value": "spine"}
                            ]
                        },
                        "attrs": {"critical": True},
                    }
                ],
                "link_rules": [
                    {
                        "source": ".*",
                        "target": ".*",
                        "link_match": {
                            "conditions": [
                                {"attr": "capacity", "op": ">=", "value": 100}
                            ]
                        },
                        "attrs": {"high_capacity": True},
                    }
                ],
            }
        }

        net = expand_network_dsl(scenario)

        # Verify spine nodes have critical attr
        for node in net.nodes.values():
            if node.attrs.get("role") == "spine":
                assert node.attrs.get("critical") is True

        # Verify high capacity links have the attr
        for link in net.links.values():
            if link.capacity >= 100:
                assert link.attrs.get("high_capacity") is True
