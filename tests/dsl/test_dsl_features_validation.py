"""Validation tests for DSL features to document in skill reference.

These tests verify the behavior of DSL features to ensure documentation accuracy.
"""

from ngraph.scenario import Scenario


class TestLinkMatchInLinkRules:
    """Validate `link_match` in link_rules - filter by link's own attributes."""

    def test_link_match_filters_by_capacity(self):
        """Only links matching link_match conditions should be updated."""
        yaml_str = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - {source: A, target: B, capacity: 100, cost: 1}
    - {source: A, target: B, capacity: 500, cost: 1}
  link_rules:
    - source: A
      target: B
      link_match:
        conditions:
          - {attr: capacity, op: ">=", value: 400}
      cost: 99
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # Check link costs
        costs = [link.cost for link in net.links.values()]
        assert sorted(costs) == [1, 99], f"Expected [1, 99], got {sorted(costs)}"

        # Verify only the high-capacity link was updated
        for link in net.links.values():
            if link.capacity >= 400:
                assert link.cost == 99, "High-capacity link should have cost 99"
            else:
                assert link.cost == 1, "Low-capacity link should have cost 1"

    def test_link_match_with_multiple_conditions(self):
        """link_match with multiple conditions using AND logic."""
        yaml_str = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - {source: A, target: B, capacity: 100, cost: 1, attrs: {type: fiber}}
    - {source: A, target: B, capacity: 500, cost: 1, attrs: {type: copper}}
    - {source: A, target: B, capacity: 500, cost: 1, attrs: {type: fiber}}
  link_rules:
    - source: A
      target: B
      link_match:
        logic: and
        conditions:
          - {attr: capacity, op: ">=", value: 400}
          - {attr: type, op: "==", value: fiber}
      cost: 99
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # Only the high-capacity fiber link should have cost 99
        updated_count = sum(1 for link in net.links.values() if link.cost == 99)
        assert updated_count == 1, f"Expected 1 updated link, got {updated_count}"


class TestMatchInNodeRules:
    """Validate `match` in node_rules - filter nodes by attribute conditions."""

    def test_match_filters_nodes(self):
        """Only nodes matching conditions should be updated."""
        yaml_str = """
network:
  nodes:
    srv1: {attrs: {role: compute, tier: 1}}
    srv2: {attrs: {role: compute, tier: 2}}
    srv3: {attrs: {role: storage, tier: 1}}
  node_rules:
    - path: ".*"
      match:
        logic: and
        conditions:
          - {attr: role, op: "==", value: compute}
          - {attr: tier, op: ">=", value: 2}
      disabled: true
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # Only srv2 should be disabled
        assert net.nodes["srv2"].disabled is True, "srv2 should be disabled"
        assert net.nodes["srv1"].disabled is False, "srv1 should not be disabled"
        assert net.nodes["srv3"].disabled is False, "srv3 should not be disabled"

    def test_match_with_or_logic(self):
        """match with OR logic should update any matching node."""
        yaml_str = """
network:
  nodes:
    srv1: {attrs: {role: compute, tier: 1}}
    srv2: {attrs: {role: compute, tier: 2}}
    srv3: {attrs: {role: storage, tier: 1}}
  node_rules:
    - path: ".*"
      match:
        logic: or
        conditions:
          - {attr: role, op: "==", value: storage}
          - {attr: tier, op: ">=", value: 2}
      attrs:
        tagged: true
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # srv2 (tier 2) and srv3 (storage) should be tagged
        assert net.nodes["srv2"].attrs.get("tagged") is True
        assert net.nodes["srv3"].attrs.get("tagged") is True
        assert net.nodes["srv1"].attrs.get("tagged") is not True


class TestExpandInRules:
    """Validate `expand` in node/link rules - variable expansion."""

    def test_expand_in_node_rules(self):
        """Variable expansion in node rules."""
        yaml_str = """
network:
  nodes:
    dc1_srv1: {}
    dc2_srv1: {}
    dc3_srv1: {}
  node_rules:
    - path: "${dc}_srv1"
      expand:
        vars:
          dc: [dc1, dc2]
        mode: cartesian
      attrs:
        tagged: true
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # dc1_srv1 and dc2_srv1 should be tagged, dc3_srv1 should not
        assert net.nodes["dc1_srv1"].attrs.get("tagged") is True
        assert net.nodes["dc2_srv1"].attrs.get("tagged") is True
        assert net.nodes["dc3_srv1"].attrs.get("tagged") is not True

    def test_expand_in_link_rules(self):
        """Variable expansion in link rules."""
        yaml_str = """
network:
  nodes:
    dc1_srv: {}
    dc2_srv: {}
    dc3_srv: {}
  links:
    - {source: dc1_srv, target: dc2_srv, capacity: 100}
    - {source: dc2_srv, target: dc3_srv, capacity: 100}
  link_rules:
    - source: "${src}_srv"
      target: "${tgt}_srv"
      expand:
        vars:
          src: [dc1]
          tgt: [dc2]
        mode: cartesian
      capacity: 200
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        for link in net.links.values():
            if link.source == "dc1_srv" and link.target == "dc2_srv":
                assert link.capacity == 200, "dc1->dc2 link should have capacity 200"
            else:
                assert link.capacity == 100, "Other links should have capacity 100"


class TestNestedInlineNodes:
    """Validate nested inline `nodes` - hierarchy without blueprints."""

    def test_nested_nodes_creates_hierarchy(self):
        """Nested nodes field creates hierarchical structure."""
        yaml_str = """
network:
  nodes:
    datacenter:
      nodes:
        rack1:
          count: 2
          template: "srv{n}"
        rack2:
          count: 2
          template: "srv{n}"
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        expected_nodes = {
            "datacenter/rack1/srv1",
            "datacenter/rack1/srv2",
            "datacenter/rack2/srv1",
            "datacenter/rack2/srv2",
        }
        actual_nodes = set(net.nodes.keys())

        assert expected_nodes == actual_nodes, (
            f"Expected {expected_nodes}, got {actual_nodes}"
        )

    def test_nested_nodes_inherits_attrs(self):
        """Nested nodes inherit parent attributes."""
        yaml_str = """
network:
  nodes:
    datacenter:
      attrs:
        region: west
      nodes:
        rack1:
          count: 1
          template: "srv{n}"
          attrs:
            role: compute
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        node = net.nodes["datacenter/rack1/srv1"]
        assert node.attrs.get("region") == "west", "Should inherit parent attrs"
        assert node.attrs.get("role") == "compute", "Should have own attrs"


class TestPathInGenerateBlocks:
    """Validate `path` in generate blocks - narrow entities before grouping."""

    def test_path_filters_nodes_in_generate(self):
        """path filter narrows nodes before generating risk groups."""
        yaml_str = """
network:
  nodes:
    prod_srv1: {attrs: {env: production}}
    prod_srv2: {attrs: {env: production}}
    dev_srv1: {attrs: {env: development}}

risk_groups:
  - generate:
      scope: node
      path: "^prod_.*"
      group_by: env
      name: "Env_${value}"
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # Only Env_production should be created (not Env_development)
        assert "Env_production" in net.risk_groups, "Env_production should exist"
        assert "Env_development" not in net.risk_groups, (
            "Env_development should not exist"
        )

        # Check membership
        assert "Env_production" in net.nodes["prod_srv1"].risk_groups
        assert "Env_production" in net.nodes["prod_srv2"].risk_groups

    def test_path_filters_links_in_generate(self):
        """path filter works on links in generate blocks."""
        yaml_str = """
network:
  nodes:
    A: {}
    B: {}
    C: {}
  links:
    - {source: A, target: B, capacity: 100, attrs: {type: backbone}}
    - {source: B, target: C, capacity: 100, attrs: {type: access}}

risk_groups:
  - generate:
      scope: link
      path: ".*A.*B.*"
      group_by: type
      name: "LinkType_${value}"
"""
        scenario = Scenario.from_yaml(yaml_str)
        net = scenario.network

        # Only LinkType_backbone should exist (A-B link)
        assert "LinkType_backbone" in net.risk_groups
        assert "LinkType_access" not in net.risk_groups


class TestInlineFlowPolicyObjects:
    """Validate inline flow_policy objects - custom policy configs."""

    def test_flow_policy_preset_string(self):
        """Preset string flow_policy should work."""
        yaml_str = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - {source: A, target: B, capacity: 100}

demands:
  test:
    - source: A
      target: B
      volume: 100
      flow_policy: SHORTEST_PATHS_ECMP
"""
        scenario = Scenario.from_yaml(yaml_str)
        demands = scenario.demand_set.sets.get("test", [])
        assert len(demands) == 1
        # flow_policy should be a FlowPolicyPreset enum
        from ngraph.model.flow.policy_config import FlowPolicyPreset

        assert demands[0].flow_policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP

    def test_flow_policy_inline_object_preserved(self):
        """Inline object flow_policy should be preserved (not converted to preset)."""
        yaml_str = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - {source: A, target: B, capacity: 100}

demands:
  test:
    - source: A
      target: B
      volume: 100
      flow_policy:
        path_alg: SPF
        flow_placement: PROPORTIONAL
"""
        scenario = Scenario.from_yaml(yaml_str)
        demands = scenario.demand_set.sets.get("test", [])
        assert len(demands) == 1
        # Inline object should be preserved as dict
        fp = demands[0].flow_policy
        assert isinstance(fp, dict), f"Expected dict, got {type(fp)}"
        assert fp.get("path_alg") == "SPF"
        assert fp.get("flow_placement") == "PROPORTIONAL"


# Run with: pytest tests/dsl/test_dsl_features_validation.py -v
