"""Integration tests for bracket expansion in risk groups.

Uses realistic physical infrastructure naming patterns:
- Fiber domain: FiberPair_NYC_CHI_C1_FP[01-12], Conduit_NYC_CHI_C[1-2], Path_NYC_CHI
- Facility domain: Building_DC[1-2], Room_DC1_R[1-3], PowerZone_DC1_R1_PZ[A,B]

Tests:
- Risk group definition expansion (top-level risk_groups with bracket patterns)
- Risk group membership expansion (risk_groups arrays on nodes/links/groups)
"""

from ngraph.scenario import Scenario


class TestRiskGroupDefinitionExpansion:
    """Tests for bracket expansion in risk group definitions."""

    def test_simple_name_expansion(self) -> None:
        """Single bracket pattern creates multiple fiber pair risk groups."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: "FiberPair_NYC_CHI_C1_FP[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {
            "FiberPair_NYC_CHI_C1_FP1",
            "FiberPair_NYC_CHI_C1_FP2",
            "FiberPair_NYC_CHI_C1_FP3",
        }

    def test_list_expansion(self) -> None:
        """List bracket pattern creates multiple power zone risk groups."""
        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - name: "PowerZone_DC1_R1_PZ[A,B,C]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {
            "PowerZone_DC1_R1_PZA",
            "PowerZone_DC1_R1_PZB",
            "PowerZone_DC1_R1_PZC",
        }

    def test_cartesian_expansion(self) -> None:
        """Multiple brackets create cartesian product of rooms and power zones."""
        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - name: "PowerZone_DC1_R[1-2]_PZ[A,B]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {
            "PowerZone_DC1_R1_PZA",
            "PowerZone_DC1_R1_PZB",
            "PowerZone_DC1_R2_PZA",
            "PowerZone_DC1_R2_PZB",
        }

    def test_attrs_preserved_on_expansion(self) -> None:
        """Attributes are copied to all expanded conduit risk groups."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: "Conduit_NYC_CHI_C[1-3]"
    attrs:
      type: fiber_conduit
      failure_probability: 0.001
"""
        scenario = Scenario.from_yaml(yaml_content)
        for i in range(1, 4):
            rg = scenario.network.risk_groups[f"Conduit_NYC_CHI_C{i}"]
            assert rg.attrs["type"] == "fiber_conduit"
            assert rg.attrs["failure_probability"] == 0.001

    def test_disabled_preserved_on_expansion(self) -> None:
        """Disabled flag is copied to all expanded risk groups."""
        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - name: "Room_DC1_R[1-2]_Maintenance"
    disabled: true
"""
        scenario = Scenario.from_yaml(yaml_content)
        assert scenario.network.risk_groups["Room_DC1_R1_Maintenance"].disabled is True
        assert scenario.network.risk_groups["Room_DC1_R2_Maintenance"].disabled is True

    def test_children_expansion(self) -> None:
        """Children names are also expanded for hierarchical fiber groups."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: "Path_NYC_CHI"
    children:
      - name: "Conduit_NYC_CHI_C[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        path = scenario.network.risk_groups["Path_NYC_CHI"]
        child_names = {c.name for c in path.children}
        assert child_names == {
            "Conduit_NYC_CHI_C1",
            "Conduit_NYC_CHI_C2",
            "Conduit_NYC_CHI_C3",
        }

    def test_parent_and_children_both_expand(self) -> None:
        """Both parent building and children rooms can have bracket patterns."""
        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - name: "Building_DC[1-2]"
    children:
      - name: "Room_R[1,2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        # Should have Building_DC1 and Building_DC2
        assert "Building_DC1" in scenario.network.risk_groups
        assert "Building_DC2" in scenario.network.risk_groups
        # Each should have Room_R1 and Room_R2 children
        for dc_name in ["Building_DC1", "Building_DC2"]:
            dc = scenario.network.risk_groups[dc_name]
            child_names = {c.name for c in dc.children}
            assert child_names == {"Room_R1", "Room_R2"}

    def test_no_expansion_needed(self) -> None:
        """Literal names work unchanged."""
        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - name: "Building_DC1"
  - name: "CoolingZone_DC1_R1_CZA"
"""
        scenario = Scenario.from_yaml(yaml_content)
        rg_names = set(scenario.network.risk_groups.keys())
        assert rg_names == {"Building_DC1", "CoolingZone_DC1_R1_CZA"}


class TestRiskGroupMembershipExpansion:
    """Tests for bracket expansion in risk group membership arrays."""

    def test_node_risk_groups_expansion(self) -> None:
        """Node risk_groups array expands bracket patterns for power zones."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1:
      risk_groups: ["PowerZone_DC1_R1_PZ[A,B]"]

risk_groups:
  - name: "PowerZone_DC1_R1_PZ[A,B]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Router_DC1_R1"]
        assert node.risk_groups == {"PowerZone_DC1_R1_PZA", "PowerZone_DC1_R1_PZB"}

    def test_group_risk_groups_expansion(self) -> None:
        """Group risk_groups array expands and inherits to all nodes."""
        yaml_content = """
network:
  nodes:
    rack_DC1_R1:
      count: 2
      risk_groups: ["CoolingZone_DC1_R1_CZ[A,B]"]

risk_groups:
  - name: "CoolingZone_DC1_R1_CZ[A,B]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for node_name in ["rack_DC1_R1/rack_DC1_R1-1", "rack_DC1_R1/rack_DC1_R1-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {
                "CoolingZone_DC1_R1_CZA",
                "CoolingZone_DC1_R1_CZB",
            }

    def test_adjacency_link_risk_groups_expansion(self) -> None:
        """Link risk_groups expands for conduit groups."""
        yaml_content = """
network:
  nodes:
    leaf:
      count: 2
    spine:
      count: 2
  links:
    - source: /leaf
      target: /spine
      pattern: mesh
      risk_groups: ["Conduit_DC1_C[1-2]"]

risk_groups:
  - name: "Conduit_DC1_C[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for link in scenario.network.links.values():
            assert link.risk_groups == {"Conduit_DC1_C1", "Conduit_DC1_C2"}

    def test_direct_link_risk_groups_expansion(self) -> None:
        """Direct link risk_groups expands for fiber path groups."""
        yaml_content = """
network:
  nodes:
    NYC: {}
    CHI: {}
  links:
    - source: NYC
      target: CHI
      risk_groups: ["FiberPair_NYC_CHI_FP[01,02,03]"]

risk_groups:
  - name: "FiberPair_NYC_CHI_FP[01,02,03]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        # Get the link (there's only one)
        link = next(iter(scenario.network.links.values()))
        assert link.risk_groups == {
            "FiberPair_NYC_CHI_FP01",
            "FiberPair_NYC_CHI_FP02",
            "FiberPair_NYC_CHI_FP03",
        }

    def test_node_override_risk_groups_expansion(self) -> None:
        """Node override risk_groups expands for building groups."""
        yaml_content = """
network:
  nodes:
    routers:
      count: 2
  node_rules:
    - path: routers
      risk_groups: ["Building_DC[1-2]"]

risk_groups:
  - name: "Building_DC[1-2]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for node_name in ["routers/routers-1", "routers/routers-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {"Building_DC1", "Building_DC2"}

    def test_link_override_risk_groups_expansion(self) -> None:
        """Link override risk_groups expands for path groups."""
        yaml_content = """
network:
  nodes:
    leaf:
      count: 2
    spine:
      count: 1
  links:
    - source: leaf
      target: spine
      pattern: mesh
  link_rules:
    - source: leaf
      target: spine
      risk_groups: ["Path_DC1_P[1-3]"]

risk_groups:
  - name: "Path_DC1_P[1-3]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for link in scenario.network.links.values():
            assert link.risk_groups == {"Path_DC1_P1", "Path_DC1_P2", "Path_DC1_P3"}

    def test_mixed_literal_and_pattern(self) -> None:
        """Mix of literal and pattern in risk_groups array."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Building_DC1", "PowerZone_DC1_R1_PZ[A,B]"]

risk_groups:
  - name: "Building_DC1"
  - name: "PowerZone_DC1_R1_PZ[A,B]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Router_DC1"]
        assert node.risk_groups == {
            "Building_DC1",
            "PowerZone_DC1_R1_PZA",
            "PowerZone_DC1_R1_PZB",
        }

    def test_empty_risk_groups_array(self) -> None:
        """Empty risk_groups array works correctly."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: []
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Router_DC1"]
        assert node.risk_groups == set()


class TestRiskGroupExpansionEdgeCases:
    """Edge cases and error handling for risk group expansion."""

    def test_overlapping_patterns_deduplicated(self) -> None:
        """Overlapping patterns in membership array are deduplicated."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Conduit_C[1-3]", "Conduit_C[2-4]"]

risk_groups:
  - name: "Conduit_C[1-4]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        node = scenario.network.nodes["Router_DC1"]
        # C2 and C3 appear in both patterns but should only be in set once
        assert node.risk_groups == {
            "Conduit_C1",
            "Conduit_C2",
            "Conduit_C3",
            "Conduit_C4",
        }

    def test_inherited_plus_own_risk_groups(self) -> None:
        """Parent and child risk groups combine correctly via blueprint."""
        yaml_content = """
blueprints:
  rack:
    nodes:
      servers:
        count: 2
        risk_groups: ["CoolingZone_CZ[A,B]"]

network:
  nodes:
    dc1_rack1:
      blueprint: rack
      risk_groups: ["Building_DC1"]

risk_groups:
  - name: "Building_DC1"
  - name: "CoolingZone_CZ[A,B]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        # Nodes should have both parent and child risk groups
        for node_name in ["dc1_rack1/servers/servers-1", "dc1_rack1/servers/servers-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {
                "Building_DC1",
                "CoolingZone_CZA",
                "CoolingZone_CZB",
            }

    def test_blueprint_risk_groups_expansion(self) -> None:
        """Risk groups in blueprint nodes expand correctly."""
        yaml_content = """
blueprints:
  fabric:
    nodes:
      leaf:
        count: 2
        risk_groups: ["PowerZone_PZ[A,B]"]

network:
  nodes:
    dc1_fabric:
      blueprint: fabric

risk_groups:
  - name: "PowerZone_PZ[A,B]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        for node_name in ["dc1_fabric/leaf/leaf-1", "dc1_fabric/leaf/leaf-2"]:
            node = scenario.network.nodes[node_name]
            assert node.risk_groups == {"PowerZone_PZA", "PowerZone_PZB"}

    def test_definition_and_membership_consistency(self) -> None:
        """Expanded definitions and memberships reference same groups."""
        yaml_content = """
network:
  nodes:
    routers:
      count: 3
      risk_groups: ["Conduit_NYC_CHI_C[1-3]"]

risk_groups:
  - name: "Conduit_NYC_CHI_C[1-3]"
    attrs:
      type: fiber_conduit
"""
        scenario = Scenario.from_yaml(yaml_content)
        # All referenced risk groups should exist
        node = scenario.network.nodes["routers/routers-1"]
        for rg_name in node.risk_groups:
            assert rg_name in scenario.network.risk_groups
            assert (
                scenario.network.risk_groups[rg_name].attrs["type"] == "fiber_conduit"
            )


class TestRiskGroupStringShorthand:
    """Tests for string shorthand in risk group definitions."""

    def test_simple_string_shorthand(self) -> None:
        """String is equivalent to {name: string}."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Building_DC1"]

risk_groups:
  - "Building_DC1"
"""
        scenario = Scenario.from_yaml(yaml_content)
        assert "Building_DC1" in scenario.network.risk_groups
        rg = scenario.network.risk_groups["Building_DC1"]
        assert rg.name == "Building_DC1"
        assert rg.disabled is False
        assert rg.attrs == {}
        assert rg.children == []

    def test_string_shorthand_with_bracket_expansion(self) -> None:
        """String shorthand also supports bracket expansion."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["PowerZone_PZ[A,B,C]"]

risk_groups:
  - "PowerZone_PZ[A,B,C]"
"""
        scenario = Scenario.from_yaml(yaml_content)
        assert set(scenario.network.risk_groups.keys()) == {
            "PowerZone_PZA",
            "PowerZone_PZB",
            "PowerZone_PZC",
        }

    def test_mixed_string_and_dict_entries(self) -> None:
        """Can mix string and dict entries in risk_groups list."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Building_DC1", "PowerZone_DC1_R1_PZA"]

risk_groups:
  - "Building_DC1"
  - name: "PowerZone_DC1_R1_PZA"
    attrs:
      failure_probability: 0.005
"""
        scenario = Scenario.from_yaml(yaml_content)
        assert "Building_DC1" in scenario.network.risk_groups
        assert "PowerZone_DC1_R1_PZA" in scenario.network.risk_groups
        assert (
            scenario.network.risk_groups["PowerZone_DC1_R1_PZA"].attrs[
                "failure_probability"
            ]
            == 0.005
        )

    def test_multiple_string_shorthands(self) -> None:
        """Multiple string entries work correctly."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Conduit_C1", "Conduit_C2", "Conduit_C3"]

risk_groups:
  - "Conduit_C1"
  - "Conduit_C2"
  - "Conduit_C3"
"""
        scenario = Scenario.from_yaml(yaml_content)
        assert set(scenario.network.risk_groups.keys()) == {
            "Conduit_C1",
            "Conduit_C2",
            "Conduit_C3",
        }
