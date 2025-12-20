"""Integration tests for bracket expansion in risk groups.

Tests:
- Risk group definition expansion (top-level risk_groups with bracket patterns)
- Risk group membership expansion (risk_groups arrays on nodes/links/groups)
"""

from ngraph.scenario import Scenario


class TestRiskGroupDefinitionExpansion:
    """Tests for bracket expansion in risk group definitions."""

    def test_simple_name_expansion(self) -> None:
        """Single bracket pattern creates multiple risk groups."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "RG[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {"RG1", "RG2", "RG3"}

    def test_list_expansion(self) -> None:
        """List bracket pattern creates multiple risk groups."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "DC[a,b,c]_Power"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {"DCa_Power", "DCb_Power", "DCc_Power"}

    def test_cartesian_expansion(self) -> None:
        """Multiple brackets create cartesian product of risk groups."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "DC[1-2]_Rack[a,b]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {"DC1_Racka", "DC1_Rackb", "DC2_Racka", "DC2_Rackb"}

    def test_attrs_preserved_on_expansion(self) -> None:
        """Attributes are copied to all expanded risk groups."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "Power[1-3]"
    attrs:
      type: power
      criticality: high
"""
        scenario = Scenario.from_yaml(yaml_content)
        for i in range(1, 4):
            rg = scenario.network.risk_groups[f"Power{i}"]
            assert rg.attrs["type"] == "power"
            assert rg.attrs["criticality"] == "high"

    def test_disabled_preserved_on_expansion(self) -> None:
        """Disabled flag is copied to all expanded risk groups."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "Maint[1-2]"
    disabled: true
"""
        scenario = Scenario.from_yaml(yaml_content)
        assert scenario.network.risk_groups["Maint1"].disabled is True
        assert scenario.network.risk_groups["Maint2"].disabled is True

    def test_children_expansion(self) -> None:
        """Children names are also expanded."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "DC1"
    children:
      - name: "Rack[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        dc1 = scenario.network.risk_groups["DC1"]
        child_names = {c.name for c in dc1.children}
        assert child_names == {"Rack1", "Rack2", "Rack3"}

    def test_parent_and_children_both_expand(self) -> None:
        """Both parent and children can have bracket patterns."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "DC[1-2]"
    children:
      - name: "Rack[a,b]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        # Should have DC1 and DC2
        assert "DC1" in scenario.network.risk_groups
        assert "DC2" in scenario.network.risk_groups
        # Each should have Racka and Rackb children
        for dc_name in ["DC1", "DC2"]:
            dc = scenario.network.risk_groups[dc_name]
            child_names = {c.name for c in dc.children}
            assert child_names == {"Racka", "Rackb"}

    def test_no_expansion_needed(self) -> None:
        """Literal names work unchanged."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: "PowerSupply"
  - name: "Cooling"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {"PowerSupply", "Cooling"}


class TestRiskGroupMembershipExpansion:
    """Tests for bracket expansion in risk group membership arrays."""

    def test_node_risk_groups_expansion(self) -> None:
        """Node risk_groups array expands bracket patterns."""
        yaml_content = """
network:
  nodes:
    ServerA:
      risk_groups: ["RG[1-3]"]

risk_groups:
  - name: "RG[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["ServerA"]
        assert node.risk_groups == {"RG1", "RG2", "RG3"}

    def test_group_risk_groups_expansion(self) -> None:
        """Group risk_groups array expands and inherits to nodes."""
        yaml_content = """
network:
  groups:
    servers:
      node_count: 2
      risk_groups: ["Power[1-2]"]

risk_groups:
  - name: "Power[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for node_name in ["servers/servers-1", "servers/servers-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {"Power1", "Power2"}

    def test_adjacency_link_risk_groups_expansion(self) -> None:
        """Adjacency link_params risk_groups expands."""
        yaml_content = """
network:
  groups:
    leaf:
      node_count: 2
    spine:
      node_count: 2
  adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_params:
        risk_groups: ["Fiber[1-2]"]

risk_groups:
  - name: "Fiber[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for link in scenario.network.links.values():
            assert link.risk_groups == {"Fiber1", "Fiber2"}

    def test_direct_link_risk_groups_expansion(self) -> None:
        """Direct link risk_groups expands."""
        yaml_content = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        risk_groups: ["Cable[a,b,c]"]

risk_groups:
  - name: "Cable[a,b,c]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        # Get the link (there's only one)
        link = next(iter(scenario.network.links.values()))
        assert link.risk_groups == {"Cablea", "Cableb", "Cablec"}

    def test_node_override_risk_groups_expansion(self) -> None:
        """Node override risk_groups expands."""
        yaml_content = """
network:
  groups:
    servers:
      node_count: 2
  node_overrides:
    - path: servers
      risk_groups: ["Zone[1-2]"]

risk_groups:
  - name: "Zone[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for node_name in ["servers/servers-1", "servers/servers-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {"Zone1", "Zone2"}

    def test_link_override_risk_groups_expansion(self) -> None:
        """Link override risk_groups expands."""
        yaml_content = """
network:
  groups:
    leaf:
      node_count: 2
    spine:
      node_count: 1
  adjacency:
    - source: leaf
      target: spine
      pattern: mesh
  link_overrides:
    - source: leaf
      target: spine
      link_params:
        risk_groups: ["Path[1-3]"]

risk_groups:
  - name: "Path[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for link in scenario.network.links.values():
            assert link.risk_groups == {"Path1", "Path2", "Path3"}

    def test_mixed_literal_and_pattern(self) -> None:
        """Mix of literal and pattern in risk_groups array."""
        yaml_content = """
network:
  nodes:
    Server:
      risk_groups: ["Static", "Dynamic[1-2]"]

risk_groups:
  - name: "Static"
  - name: "Dynamic[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Server"]
        assert node.risk_groups == {"Static", "Dynamic1", "Dynamic2"}

    def test_empty_risk_groups_array(self) -> None:
        """Empty risk_groups array works correctly."""
        yaml_content = """
network:
  nodes:
    Server:
      risk_groups: []
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Server"]
        assert node.risk_groups == set()


class TestRiskGroupExpansionEdgeCases:
    """Edge cases and error handling for risk group expansion."""

    def test_overlapping_patterns_deduplicated(self) -> None:
        """Overlapping patterns in membership array are deduplicated."""
        yaml_content = """
network:
  nodes:
    Server:
      risk_groups: ["RG[1-3]", "RG[2-4]"]

risk_groups:
  - name: "RG[1-4]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Server"]
        # RG2 and RG3 appear in both patterns but should only be in set once
        assert node.risk_groups == {"RG1", "RG2", "RG3", "RG4"}

    def test_inherited_plus_own_risk_groups(self) -> None:
        """Parent and child risk groups combine correctly via blueprint."""
        yaml_content = """
blueprints:
  pod:
    groups:
      servers:
        node_count: 2
        risk_groups: ["Child[a,b]"]

network:
  groups:
    parent:
      use_blueprint: pod
      risk_groups: ["Parent[1-2]"]

risk_groups:
  - name: "Parent[1-2]"
  - name: "Child[a,b]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        # Nodes should have both parent and child risk groups
        for node_name in ["parent/servers/servers-1", "parent/servers/servers-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {"Parent1", "Parent2", "Childa", "Childb"}

    def test_blueprint_risk_groups_expansion(self) -> None:
        """Risk groups in blueprint groups expand correctly."""
        yaml_content = """
blueprints:
  pod:
    groups:
      leaf:
        node_count: 2
        risk_groups: ["Leaf[1-2]"]

network:
  groups:
    pod1:
      use_blueprint: pod

risk_groups:
  - name: "Leaf[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for node_name in ["pod1/leaf/leaf-1", "pod1/leaf/leaf-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {"Leaf1", "Leaf2"}

    def test_definition_and_membership_consistency(self) -> None:
        """Expanded definitions and memberships reference same groups."""
        yaml_content = """
network:
  groups:
    servers:
      node_count: 3
      risk_groups: ["Power[1-3]"]

risk_groups:
  - name: "Power[1-3]"
    attrs:
      type: power
"""
        scenario = Scenario.from_yaml(yaml_content)
        # All referenced risk groups should exist
        node = scenario.network.nodes["servers/servers-1"]
        for rg_name in node.risk_groups:
            assert rg_name in scenario.network.risk_groups
            assert scenario.network.risk_groups[rg_name].attrs["type"] == "power"
