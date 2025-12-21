"""Tests for risk group membership rule resolution.

Uses realistic physical infrastructure examples:
- Fiber domain: Links with fiber.conduit_id, fiber.path_id attributes
- Facility domain: Nodes with facility.building_id, facility.power_zone attributes
"""

import pytest

from ngraph.scenario import Scenario


class TestMembershipRulesBasic:
    """Basic tests for membership rule resolution."""

    def test_node_membership_simple(self) -> None:
        """Nodes matching facility.power_zone are added to power zone risk group."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1_RK01:
      attrs:
        facility:
          building_id: "DC1"
          room_id: "DC1-R1"
          power_zone: "DC1-R1-PZ-A"
    Router_DC1_R1_RK02:
      attrs:
        facility:
          building_id: "DC1"
          room_id: "DC1-R1"
          power_zone: "DC1-R1-PZ-A"
    Router_DC1_R2_RK01:
      attrs:
        facility:
          building_id: "DC1"
          room_id: "DC1-R2"
          power_zone: "DC1-R2-PZ-B"

risk_groups:
  - name: PowerZone_DC1_R1_PZA
    membership:
      entity_scope: node
      match:
        conditions:
          - attr: facility.power_zone
            operator: "=="
            value: "DC1-R1-PZ-A"
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Routers in power zone A should be in the risk group
        assert (
            "PowerZone_DC1_R1_PZA"
            in scenario.network.nodes["Router_DC1_R1_RK01"].risk_groups
        )
        assert (
            "PowerZone_DC1_R1_PZA"
            in scenario.network.nodes["Router_DC1_R1_RK02"].risk_groups
        )
        # Router in power zone B should not be
        assert (
            "PowerZone_DC1_R1_PZA"
            not in scenario.network.nodes["Router_DC1_R2_RK01"].risk_groups
        )

    def test_link_membership_simple(self) -> None:
        """Links matching fiber.conduit_id are added to conduit risk group."""
        yaml_content = """
network:
  nodes:
    NYC: {}
    CHI: {}
    LA: {}
  links:
    - source: NYC
      target: CHI
      link_params:
        attrs:
          fiber:
            conduit_id: "NYC-CHI-C1"
    - source: CHI
      target: LA
      link_params:
        attrs:
          fiber:
            conduit_id: "CHI-LA-C1"

risk_groups:
  - name: Conduit_NYC_CHI_C1
    membership:
      entity_scope: link
      match:
        conditions:
          - attr: fiber.conduit_id
            operator: "=="
            value: "NYC-CHI-C1"
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Find links and check membership
        for link in scenario.network.links.values():
            if link.attrs.get("fiber", {}).get("conduit_id") == "NYC-CHI-C1":
                assert "Conduit_NYC_CHI_C1" in link.risk_groups
            else:
                assert "Conduit_NYC_CHI_C1" not in link.risk_groups

    def test_risk_group_hierarchy_membership(self) -> None:
        """Risk groups matching conditions become children of parent group."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: Conduit_NYC_CHI_C1
    attrs:
      fiber:
        path_id: "NYC-CHI"
  - name: Conduit_NYC_CHI_C2
    attrs:
      fiber:
        path_id: "NYC-CHI"
  - name: Conduit_NYC_LA_C1
    attrs:
      fiber:
        path_id: "NYC-LA"
  - name: Path_NYC_CHI
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: fiber.path_id
            operator: "=="
            value: "NYC-CHI"
"""
        scenario = Scenario.from_yaml(yaml_content)

        path_rg = scenario.network.risk_groups["Path_NYC_CHI"]
        child_names = {c.name for c in path_rg.children}

        # NYC-CHI conduits should be children of the path
        assert child_names == {"Conduit_NYC_CHI_C1", "Conduit_NYC_CHI_C2"}
        # NYC-LA conduit should not be
        assert "Conduit_NYC_LA_C1" not in child_names


class TestMembershipRulesConditionLogic:
    """Tests for membership condition logic (and/or)."""

    def test_and_logic_all_must_match(self) -> None:
        """With 'and' logic, equipment must be in specific room AND power zone."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1_RK01:
      attrs:
        facility:
          room_id: "DC1-R1"
          power_zone: "DC1-R1-PZ-A"
    Router_DC1_R1_RK02:
      attrs:
        facility:
          room_id: "DC1-R1"
          power_zone: "DC1-R1-PZ-B"
    Router_DC1_R2_RK01:
      attrs:
        facility:
          room_id: "DC1-R2"
          power_zone: "DC1-R2-PZ-A"

risk_groups:
  - name: Room1_PowerZoneA
    membership:
      entity_scope: node
      match:
        logic: and
        conditions:
          - attr: facility.room_id
            operator: "=="
            value: "DC1-R1"
          - attr: facility.power_zone
            operator: "=="
            value: "DC1-R1-PZ-A"
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Only first router matches both conditions
        assert (
            "Room1_PowerZoneA"
            in scenario.network.nodes["Router_DC1_R1_RK01"].risk_groups
        )
        assert (
            "Room1_PowerZoneA"
            not in scenario.network.nodes["Router_DC1_R1_RK02"].risk_groups
        )
        assert (
            "Room1_PowerZoneA"
            not in scenario.network.nodes["Router_DC1_R2_RK01"].risk_groups
        )

    def test_or_logic_any_can_match(self) -> None:
        """With 'or' logic, links in either conduit are grouped together."""
        yaml_content = """
network:
  nodes:
    NYC: {}
    CHI: {}
    LA: {}
  links:
    - source: NYC
      target: CHI
      link_params:
        attrs:
          fiber:
            conduit_id: "NYC-CHI-C1"
    - source: NYC
      target: LA
      link_params:
        attrs:
          fiber:
            conduit_id: "NYC-LA-C1"
    - source: CHI
      target: LA
      link_params:
        attrs:
          fiber:
            conduit_id: "CHI-LA-C1"

risk_groups:
  - name: Path_NYC_Outbound
    membership:
      entity_scope: link
      match:
        logic: or
        conditions:
          - attr: fiber.conduit_id
            operator: "=="
            value: "NYC-CHI-C1"
          - attr: fiber.conduit_id
            operator: "=="
            value: "NYC-LA-C1"
"""
        scenario = Scenario.from_yaml(yaml_content)

        # NYC-CHI and NYC-LA links match
        nyc_links = 0
        chi_la_links = 0
        for link in scenario.network.links.values():
            conduit = link.attrs.get("fiber", {}).get("conduit_id", "")
            if conduit in ("NYC-CHI-C1", "NYC-LA-C1"):
                assert "Path_NYC_Outbound" in link.risk_groups
                nyc_links += 1
            elif conduit == "CHI-LA-C1":
                assert "Path_NYC_Outbound" not in link.risk_groups
                chi_la_links += 1

        assert nyc_links == 2
        assert chi_la_links == 1


class TestMembershipRulesWithDotNotation:
    """Tests for membership rules using dot-notation attributes."""

    def test_dot_notation_in_match(self) -> None:
        """Dot-notation works in membership conditions for nested attributes."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1:
      attrs:
        facility:
          building_id: "DC1"
    Router_DC2_R1:
      attrs:
        facility:
          building_id: "DC2"

risk_groups:
  - name: Building_DC1
    membership:
      entity_scope: node
      match:
        conditions:
          - attr: facility.building_id
            operator: "=="
            value: "DC1"
"""
        scenario = Scenario.from_yaml(yaml_content)

        assert "Building_DC1" in scenario.network.nodes["Router_DC1_R1"].risk_groups
        assert "Building_DC1" not in scenario.network.nodes["Router_DC2_R1"].risk_groups


class TestMembershipRulesEdgeCases:
    """Edge cases for membership rules."""

    def test_no_membership_rule(self) -> None:
        """Risk groups without membership rules work normally with explicit assignment."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Building_DC1"]

risk_groups:
  - name: Building_DC1
"""
        scenario = Scenario.from_yaml(yaml_content)

        assert "Building_DC1" in scenario.network.nodes["Router_DC1"].risk_groups

    def test_no_matches(self) -> None:
        """Membership rule with no matches creates empty group."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      attrs:
        facility:
          building_id: "DC1"

risk_groups:
  - name: Building_DC99
    membership:
      entity_scope: node
      match:
        conditions:
          - attr: facility.building_id
            operator: "=="
            value: "DC99"
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Group exists but no nodes are members
        assert "Building_DC99" in scenario.network.risk_groups
        assert "Building_DC99" not in scenario.network.nodes["Router_DC1"].risk_groups

    def test_self_reference_avoided(self) -> None:
        """Risk group doesn't add itself as a child."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: AllConduits
    attrs:
      type: meta
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: name
            operator: any_value
"""
        scenario = Scenario.from_yaml(yaml_content)

        all_conduits = scenario.network.risk_groups["AllConduits"]
        # Should not contain itself
        assert all(c.name != "AllConduits" for c in all_conduits.children)

    def test_membership_combines_with_explicit(self) -> None:
        """Membership rules combine with explicit risk group references."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1:
      risk_groups: ["CoolingZone_DC1_R1_CZA"]
      attrs:
        facility:
          power_zone: "DC1-R1-PZ-A"

risk_groups:
  - name: CoolingZone_DC1_R1_CZA
  - name: PowerZone_DC1_R1_PZA
    membership:
      entity_scope: node
      match:
        conditions:
          - attr: facility.power_zone
            operator: "=="
            value: "DC1-R1-PZ-A"
"""
        scenario = Scenario.from_yaml(yaml_content)

        node = scenario.network.nodes["Router_DC1_R1"]
        # Has both explicit and membership-assigned groups
        assert "CoolingZone_DC1_R1_CZA" in node.risk_groups
        assert "PowerZone_DC1_R1_PZA" in node.risk_groups


class TestMembershipRulesOperators:
    """Tests for various operators in membership conditions."""

    def test_contains_operator(self) -> None:
        """Contains operator for list attributes like fiber pair IDs."""
        yaml_content = """
network:
  nodes:
    NYC: {}
    CHI: {}
  links:
    - source: NYC
      target: CHI
      link_params:
        attrs:
          fiber:
            pair_ids: ["FP01", "FP02", "FP03"]
    - source: CHI
      target: NYC
      link_params:
        attrs:
          fiber:
            pair_ids: ["FP04", "FP05"]

risk_groups:
  - name: FiberPair_FP01
    membership:
      entity_scope: link
      match:
        conditions:
          - attr: fiber.pair_ids
            operator: contains
            value: "FP01"
"""
        scenario = Scenario.from_yaml(yaml_content)

        for link in scenario.network.links.values():
            pair_ids = link.attrs.get("fiber", {}).get("pair_ids", [])
            if "FP01" in pair_ids:
                assert "FiberPair_FP01" in link.risk_groups
            else:
                assert "FiberPair_FP01" not in link.risk_groups

    def test_in_operator(self) -> None:
        """In operator for matching building in list of buildings."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      attrs:
        facility:
          building_id: "DC1"
    Router_DC2:
      attrs:
        facility:
          building_id: "DC2"
    Router_DC3:
      attrs:
        facility:
          building_id: "DC3"

risk_groups:
  - name: Campus_East
    membership:
      entity_scope: node
      match:
        conditions:
          - attr: facility.building_id
            operator: in
            value: ["DC1", "DC2"]
"""
        scenario = Scenario.from_yaml(yaml_content)

        assert "Campus_East" in scenario.network.nodes["Router_DC1"].risk_groups
        assert "Campus_East" in scenario.network.nodes["Router_DC2"].risk_groups
        assert "Campus_East" not in scenario.network.nodes["Router_DC3"].risk_groups

    def test_numeric_comparison(self) -> None:
        """Numeric comparison for fiber distance."""
        yaml_content = """
network:
  nodes:
    NYC: {}
    CHI: {}
    LA: {}
  links:
    - source: NYC
      target: CHI
      link_params:
        attrs:
          fiber:
            distance_km: 1200
    - source: NYC
      target: LA
      link_params:
        attrs:
          fiber:
            distance_km: 4000
    - source: CHI
      target: LA
      link_params:
        attrs:
          fiber:
            distance_km: 2800

risk_groups:
  - name: LongHaulFiber
    membership:
      entity_scope: link
      match:
        conditions:
          - attr: fiber.distance_km
            operator: ">="
            value: 2000
"""
        scenario = Scenario.from_yaml(yaml_content)

        long_haul_count = 0
        short_haul_count = 0
        for link in scenario.network.links.values():
            distance = link.attrs.get("fiber", {}).get("distance_km", 0)
            if distance >= 2000:
                assert "LongHaulFiber" in link.risk_groups
                long_haul_count += 1
            else:
                assert "LongHaulFiber" not in link.risk_groups
                short_haul_count += 1

        assert long_haul_count == 2  # NYC-LA and CHI-LA
        assert short_haul_count == 1  # NYC-CHI


class TestRiskGroupHierarchyCycleDetection:
    """Tests for circular risk group hierarchy detection."""

    def test_direct_mutual_membership_cycle_detected(self) -> None:
        """Direct cycle where A adds B as child and B adds A as child is detected."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: Path_NYC_CHI
    attrs:
      type: path
      route: "NYC-CHI"
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: route
            operator: "=="
            value: "NYC-CHI"
  - name: Conduit_NYC_CHI_C1
    attrs:
      type: conduit
      route: "NYC-CHI"
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: type
            operator: "=="
            value: path
"""
        with pytest.raises(ValueError) as exc_info:
            Scenario.from_yaml(yaml_content)

        error_msg = str(exc_info.value)
        assert "circular" in error_msg.lower() or "cycle" in error_msg.lower()
        # Should mention the groups involved
        assert "Path_NYC_CHI" in error_msg or "Conduit_NYC_CHI_C1" in error_msg

    def test_transitive_cycle_detected(self) -> None:
        """Transitive cycle A->B->C->A is detected."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: GroupA
    attrs:
      tier: 1
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: tier
            operator: "=="
            value: 3
  - name: GroupB
    attrs:
      tier: 2
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: tier
            operator: "=="
            value: 1
  - name: GroupC
    attrs:
      tier: 3
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: tier
            operator: "=="
            value: 2
"""
        with pytest.raises(ValueError) as exc_info:
            Scenario.from_yaml(yaml_content)

        error_msg = str(exc_info.value)
        assert "circular" in error_msg.lower() or "cycle" in error_msg.lower()

    def test_valid_hierarchy_no_cycle(self) -> None:
        """Valid tree hierarchy without cycles works correctly."""
        yaml_content = """
network:
  nodes:
    NYC: {}

risk_groups:
  - name: Conduit_NYC_CHI_C1
    attrs:
      fiber:
        path_id: "NYC-CHI"
  - name: Conduit_NYC_CHI_C2
    attrs:
      fiber:
        path_id: "NYC-CHI"
  - name: Conduit_NYC_LA_C1
    attrs:
      fiber:
        path_id: "NYC-LA"
  - name: Path_NYC_CHI
    membership:
      entity_scope: risk_group
      match:
        conditions:
          - attr: fiber.path_id
            operator: "=="
            value: "NYC-CHI"
"""
        # Should not raise
        scenario = Scenario.from_yaml(yaml_content)

        path_rg = scenario.network.risk_groups["Path_NYC_CHI"]
        child_names = {c.name for c in path_rg.children}
        assert child_names == {"Conduit_NYC_CHI_C1", "Conduit_NYC_CHI_C2"}
