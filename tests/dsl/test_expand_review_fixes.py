"""Regression tests for DSL blueprint expansion review fixes.

Covers:
- Full variable substitution in link expand blocks (attrs, risk_groups,
  selector match values), not just source/target path strings.
- Regex-escaping of literal parent paths when joining blueprint link
  selectors (metacharacters in group names must not leak into the regex).
- Validation of blueprint params override keys (typos and unsupported
  deep dotted 'params.*' paths raise instead of silently no-opping).
- link_rules requiring source/target at both schema and expansion level.
- node_rules/link_rules of the wrong type raising instead of being ignored.
- Deterministic (sorted) risk_groups in flattened node/link attrs.
- Per-expansion mesh reversed-pair dedup semantics (pinned behavior).
"""

import jsonschema
import pytest

from ngraph.dsl.blueprints.expand import expand_network_dsl
from ngraph.dsl.loader import load_scenario_yaml
from ngraph.dsl.selectors import flatten_link_attrs, flatten_node_attrs
from ngraph.model.network import Link, Node

# ──────────────────────────────────────────────────────────────────────────────
# Link expand block: full variable substitution
# ──────────────────────────────────────────────────────────────────────────────


class TestLinkExpandFullSubstitution:
    """Variables in a link expand block substitute into the whole definition."""

    def test_attrs_are_substituted_per_combination(self) -> None:
        """Link attrs receive per-combination values, not literal templates."""
        data = {
            "network": {
                "nodes": {
                    "dc1": {"nodes": {"gw": {}}},
                    "dc2": {"nodes": {"gw": {}}},
                    "hub": {},
                },
                "links": [
                    {
                        "source": "${dc}/gw",
                        "target": "hub",
                        "expand": {"vars": {"dc": ["dc1", "dc2"]}},
                        "attrs": {
                            "datacenter": "${dc}",
                            "ring": "${dc}_internal",
                        },
                    }
                ],
            }
        }
        net = expand_network_dsl(data)

        assert len(net.links) == 2
        by_source = {link.source: link for link in net.links.values()}
        assert by_source["dc1/gw"].attrs["datacenter"] == "dc1"
        assert by_source["dc1/gw"].attrs["ring"] == "dc1_internal"
        assert by_source["dc2/gw"].attrs["datacenter"] == "dc2"
        assert by_source["dc2/gw"].attrs["ring"] == "dc2_internal"

    def test_risk_groups_are_substituted(self) -> None:
        """Link risk_groups receive per-combination values."""
        data = {
            "network": {
                "nodes": {
                    "dc1": {"nodes": {"gw": {}}},
                    "dc2": {"nodes": {"gw": {}}},
                    "hub": {},
                },
                "links": [
                    {
                        "source": "${dc}/gw",
                        "target": "hub",
                        "expand": {"vars": {"dc": ["dc1", "dc2"]}},
                        "risk_groups": ["RG_${dc}"],
                    }
                ],
            }
        }
        net = expand_network_dsl(data)

        by_source = {link.source: link for link in net.links.values()}
        assert by_source["dc1/gw"].risk_groups == {"RG_dc1"}
        assert by_source["dc2/gw"].risk_groups == {"RG_dc2"}

    def test_match_only_selector_is_substituted(self) -> None:
        """A dict selector with only 'match' honors the expand block."""
        data = {
            "network": {
                "nodes": {
                    "gw1": {"attrs": {"dc": "dc1"}},
                    "gw2": {"attrs": {"dc": "dc2"}},
                    "hub": {},
                },
                "links": [
                    {
                        "source": {
                            "match": {
                                "conditions": [
                                    {"attr": "dc", "op": "==", "value": "${d}"}
                                ]
                            }
                        },
                        "target": "hub",
                        "expand": {"vars": {"d": ["dc1", "dc2"]}},
                    }
                ],
            }
        }
        net = expand_network_dsl(data)

        sources = sorted(link.source for link in net.links.values())
        assert sources == ["gw1", "gw2"]

    def test_match_value_keeps_native_type_for_int_attr(self) -> None:
        """A whole-placeholder match value compares as int against int attrs."""
        data = {
            "network": {
                "nodes": {
                    "gw1": {"attrs": {"tier": 2}},
                    "gw2": {"attrs": {"tier": 1}},
                    "hub": {},
                },
                "links": [
                    {
                        "source": {
                            "match": {
                                "conditions": [
                                    {"attr": "tier", "op": "==", "value": "${t}"}
                                ]
                            }
                        },
                        "target": "hub",
                        "expand": {"vars": {"t": [2]}},
                    }
                ],
            }
        }
        net = expand_network_dsl(data)

        sources = sorted(link.source for link in net.links.values())
        assert sources == ["gw1"]

    def test_node_rule_match_value_keeps_native_type(self) -> None:
        """node_rules with '${t}' match values apply attrs to int-attr nodes."""
        data = {
            "network": {
                "nodes": {
                    "n1": {"attrs": {"tier": 2}},
                    "n2": {"attrs": {"tier": 1}},
                },
                "node_rules": [
                    {
                        "path": ".*",
                        "match": {
                            "conditions": [
                                {"attr": "tier", "op": "==", "value": "${t}"}
                            ]
                        },
                        "attrs": {"selected_tier": "${t}"},
                        "expand": {"vars": {"t": [2]}},
                    }
                ],
            }
        }
        net = expand_network_dsl(data)

        assert net.nodes["n1"].attrs.get("selected_tier") == 2
        assert "selected_tier" not in net.nodes["n2"].attrs

    def test_mesh_dedup_is_per_expansion_combination(self) -> None:
        """Each variable combination is an independent link definition.

        Cartesian expansion over symmetric variable lists produces both
        orientations as separate parallel links (documented semantics).
        """
        data = {
            "network": {
                "nodes": {
                    "dc1": {"nodes": {"gw": {}}},
                    "dc2": {"nodes": {"gw": {}}},
                },
                "links": [
                    {
                        "source": "dc${a}/gw",
                        "target": "dc${b}/gw",
                        "expand": {"vars": {"a": [1, 2], "b": [1, 2]}},
                    }
                ],
            }
        }
        net = expand_network_dsl(data)

        pairs = sorted((link.source, link.target) for link in net.links.values())
        assert pairs == [("dc1/gw", "dc2/gw"), ("dc2/gw", "dc1/gw")]


# ──────────────────────────────────────────────────────────────────────────────
# Parent path regex escaping in blueprint links
# ──────────────────────────────────────────────────────────────────────────────


class TestBlueprintParentPathEscaping:
    """Literal parent paths are escaped before regex compilation."""

    BLUEPRINT = {
        "nodes": {
            "leaf": {"count": 2, "template": "leaf-{n}"},
            "spine": {"count": 2, "template": "spine-{n}"},
        },
        "links": [{"source": "/leaf", "target": "/spine", "pattern": "mesh"}],
    }

    def test_dot_in_group_name_does_not_match_siblings(self) -> None:
        """A '.' in a group name must not act as a regex wildcard."""
        data = {
            "blueprints": {"bp": self.BLUEPRINT},
            "network": {
                "nodes": {
                    "dc.1": {"blueprint": "bp"},
                    "dcX1": {"blueprint": "bp"},
                }
            },
        }
        net = expand_network_dsl(data)

        # 2x2 mesh inside each of the two instances; no cross-subtree links.
        assert len(net.links) == 8
        for link in net.links.values():
            src_root = link.source.split("/")[0]
            tgt_root = link.target.split("/")[0]
            assert src_root == tgt_root

    def test_plus_in_group_name_still_creates_links(self) -> None:
        """A '+' in a group name must not break blueprint link selection."""
        data = {
            "blueprints": {"bp": self.BLUEPRINT},
            "network": {"nodes": {"agg+core": {"blueprint": "bp"}}},
        }
        net = expand_network_dsl(data)

        assert len(net.links) == 4
        for link in net.links.values():
            assert link.source.startswith("agg+core/")
            assert link.target.startswith("agg+core/")


# ──────────────────────────────────────────────────────────────────────────────
# Blueprint params override validation
# ──────────────────────────────────────────────────────────────────────────────


class TestBlueprintParamsValidation:
    """params override keys must address an existing blueprint subgroup."""

    def test_typo_in_subgroup_prefix_raises(self) -> None:
        data = {
            "blueprints": {
                "bp": {"nodes": {"spine": {"count": 2, "template": "s-{n}"}}}
            },
            "network": {
                "nodes": {"pod1": {"blueprint": "bp", "params": {"spnie.count": 8}}}
            },
        }
        with pytest.raises(ValueError, match="matches no node group"):
            expand_network_dsl(data)

    def test_key_without_field_part_raises(self) -> None:
        data = {
            "blueprints": {
                "bp": {"nodes": {"spine": {"count": 2, "template": "s-{n}"}}}
            },
            "network": {"nodes": {"pod1": {"blueprint": "bp", "params": {"spine": 8}}}},
        }
        with pytest.raises(ValueError, match="must be of the form"):
            expand_network_dsl(data)

    def test_deep_dotted_nested_params_raises(self) -> None:
        """'group.params.sub.field' no longer silently no-ops."""
        data = {
            "blueprints": {
                "inner": {"nodes": {"spine": {"count": 2, "template": "s-{n}"}}},
                "outer": {"nodes": {"pod1": {"blueprint": "inner"}}},
            },
            "network": {
                "nodes": {
                    "site": {
                        "blueprint": "outer",
                        "params": {"pod1.params.spine.count": 8},
                    }
                }
            },
        }
        with pytest.raises(ValueError, match="must be of the form"):
            expand_network_dsl(data)

    def test_dict_valued_nested_params_pass_through_works(self) -> None:
        """The supported dict-valued form overrides nested blueprint params."""
        data = {
            "blueprints": {
                "inner": {"nodes": {"spine": {"count": 2, "template": "s-{n}"}}},
                "outer": {"nodes": {"pod1": {"blueprint": "inner"}}},
            },
            "network": {
                "nodes": {
                    "site": {
                        "blueprint": "outer",
                        "params": {"pod1.params": {"spine.count": 4}},
                    }
                }
            },
        }
        net = expand_network_dsl(data)

        spines = [n for n in net.nodes if n.startswith("site/pod1/spine/")]
        assert len(spines) == 4

    def test_dotted_subgroup_name_override_applies(self) -> None:
        """Overrides address subgroup names that themselves contain dots."""
        data = {
            "blueprints": {
                "bp": {"nodes": {"rack.a": {"count": 1, "template": "n-{n}"}}}
            },
            "network": {
                "nodes": {"pod1": {"blueprint": "bp", "params": {"rack.a.count": 3}}}
            },
        }
        net = expand_network_dsl(data)

        rack_nodes = [n for n in net.nodes if n.startswith("pod1/rack.a/")]
        assert len(rack_nodes) == 3

    def test_dotted_subgroup_longest_prefix_wins(self) -> None:
        """When one group name extends another, the longest prefix applies."""
        data = {
            "blueprints": {
                "bp": {
                    "nodes": {
                        "rack": {"count": 1, "template": "r-{n}"},
                        "rack.a": {"count": 1, "template": "a-{n}"},
                    }
                }
            },
            "network": {
                "nodes": {
                    "pod1": {
                        "blueprint": "bp",
                        "params": {"rack.a.count": 3, "rack.count": 2},
                    }
                }
            },
        }
        net = expand_network_dsl(data)

        rack_a_nodes = [n for n in net.nodes if n.startswith("pod1/rack.a/")]
        rack_nodes = [n for n in net.nodes if n.startswith("pod1/rack/")]
        assert len(rack_a_nodes) == 3
        assert len(rack_nodes) == 2

    def test_key_equal_to_dotted_group_name_raises_form_error(self) -> None:
        """A key naming a dotted group without a field raises the form error."""
        data = {
            "blueprints": {
                "bp": {"nodes": {"rack.a": {"count": 1, "template": "n-{n}"}}}
            },
            "network": {
                "nodes": {"pod1": {"blueprint": "bp", "params": {"rack.a": 3}}}
            },
        }
        with pytest.raises(ValueError, match="must be of the form"):
            expand_network_dsl(data)

    def test_valid_override_with_bracket_pattern_group(self) -> None:
        """Overrides keyed on literal (unexpanded) bracket names stay valid."""
        data = {
            "blueprints": {
                "bp": {"nodes": {"plane[1-2]": {"count": 1, "template": "n-{n}"}}}
            },
            "network": {
                "nodes": {
                    "pod1": {"blueprint": "bp", "params": {"plane[1-2].count": 2}}
                }
            },
        }
        net = expand_network_dsl(data)

        plane_nodes = [n for n in net.nodes if "/plane" in n]
        assert len(plane_nodes) == 4


# ──────────────────────────────────────────────────────────────────────────────
# link_rules source/target requirement
# ──────────────────────────────────────────────────────────────────────────────


class TestLinkRulesSourceTargetRequired:
    """link_rules entries must declare both source and target."""

    def test_schema_rejects_link_rule_without_source_target(self) -> None:
        yaml_content = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
  link_rules:
    - capacity: 99
"""
        with pytest.raises(jsonschema.ValidationError):
            load_scenario_yaml(yaml_content)

    def test_expansion_raises_value_error_not_key_error(self) -> None:
        data = {
            "network": {
                "nodes": {"A": {}, "B": {}},
                "links": [{"source": "A", "target": "B"}],
                "link_rules": [{"capacity": 99}],
            }
        }
        with pytest.raises(ValueError, match="'source' and 'target'"):
            expand_network_dsl(data)


# ──────────────────────────────────────────────────────────────────────────────
# Malformed rules sections raise
# ──────────────────────────────────────────────────────────────────────────────


class TestMalformedRulesSectionsRaise:
    """Non-list node_rules/link_rules raise instead of being ignored."""

    def test_node_rules_mapping_raises(self) -> None:
        data = {
            "network": {
                "nodes": {"A": {}},
                "node_rules": {"path": "A"},
            }
        }
        with pytest.raises(ValueError, match="'node_rules' must be a list"):
            expand_network_dsl(data)

    def test_link_rules_mapping_raises(self) -> None:
        data = {
            "network": {
                "nodes": {"A": {}, "B": {}},
                "links": [{"source": "A", "target": "B"}],
                "link_rules": {"source": "A", "target": "B"},
            }
        }
        with pytest.raises(ValueError, match="'link_rules' must be a list"):
            expand_network_dsl(data)

    def test_absent_rules_sections_are_noop(self) -> None:
        data = {"network": {"nodes": {"A": {}}}}
        net = expand_network_dsl(data)
        assert "A" in net.nodes


# ──────────────────────────────────────────────────────────────────────────────
# Deterministic flattened risk_groups
# ──────────────────────────────────────────────────────────────────────────────


class TestFlattenedRiskGroupsSorted:
    """flatten_node_attrs/flatten_link_attrs expose sorted risk_groups."""

    def test_node_risk_groups_sorted(self) -> None:
        node = Node("n1")
        node.risk_groups = {"rg1", "rg3", "beta", "alpha", "rg2"}
        attrs = flatten_node_attrs(node)
        assert attrs["risk_groups"] == ["alpha", "beta", "rg1", "rg2", "rg3"]

    def test_link_risk_groups_sorted(self) -> None:
        link = Link(source="a", target="b")
        link.risk_groups = {"zeta", "alpha", "mid"}
        attrs = flatten_link_attrs(link, "link-id-1")
        assert attrs["risk_groups"] == ["alpha", "mid", "zeta"]
