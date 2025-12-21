"""Tests for dynamic risk group generation.

Uses realistic physical infrastructure examples:
- Fiber domain: Generate conduit groups from fiber.path_id on links
- Facility domain: Generate power zone groups from facility.building_id on nodes
"""

import pytest

from ngraph.scenario import Scenario


class TestRiskGroupGenerationBasic:
    """Basic tests for risk group generation."""

    def test_generate_from_link_attribute(self) -> None:
        """Generate conduit risk groups from unique fiber.path_id values on links."""
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
            path_id: "NYC-CHI"
    - source: CHI
      target: LA
      link_params:
        attrs:
          fiber:
            path_id: "CHI-LA"
    - source: NYC
      target: LA
      link_params:
        attrs:
          fiber:
            path_id: "NYC-CHI"

risk_groups:
  - generate:
      entity_scope: link
      group_by: fiber.path_id
      name_template: Path_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Should have two generated path groups
        assert "Path_NYC-CHI" in scenario.network.risk_groups
        assert "Path_CHI-LA" in scenario.network.risk_groups

        # Links should be members of their respective path groups
        for link in scenario.network.links.values():
            path_id = link.attrs.get("fiber", {}).get("path_id")
            expected_group = f"Path_{path_id}"
            assert expected_group in link.risk_groups

    def test_generate_from_node_attribute(self) -> None:
        """Generate building risk groups from unique facility.building_id values."""
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
    Router_DC1_R2:
      attrs:
        facility:
          building_id: "DC1"

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.building_id
      name_template: Building_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Should have two generated building groups
        assert "Building_DC1" in scenario.network.risk_groups
        assert "Building_DC2" in scenario.network.risk_groups

        # Nodes should be members of their respective building groups
        assert "Building_DC1" in scenario.network.nodes["Router_DC1_R1"].risk_groups
        assert "Building_DC2" in scenario.network.nodes["Router_DC2_R1"].risk_groups
        assert "Building_DC1" in scenario.network.nodes["Router_DC1_R2"].risk_groups

    def test_generate_with_attrs(self) -> None:
        """Generated groups have specified static attrs for failure metadata."""
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
            conduit_id: "NYC-CHI-C1"
    - source: CHI
      target: NYC
      link_params:
        attrs:
          fiber:
            conduit_id: "NYC-CHI-C2"

risk_groups:
  - generate:
      entity_scope: link
      group_by: fiber.conduit_id
      name_template: Conduit_${value}
      attrs:
        type: fiber_conduit
        failure_probability: 0.001
"""
        scenario = Scenario.from_yaml(yaml_content)

        for rg in scenario.network.risk_groups.values():
            if rg.name.startswith("Conduit_"):
                assert rg.attrs["type"] == "fiber_conduit"
                assert rg.attrs["failure_probability"] == 0.001


class TestRiskGroupGenerationDotNotation:
    """Tests for generation with dot-notation attributes."""

    def test_generate_with_nested_attribute(self) -> None:
        """Generate power zone groups from nested facility.power_zone attribute."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1_RK01:
      attrs:
        facility:
          power_zone: "DC1-R1-PZ-A"
    Router_DC1_R1_RK02:
      attrs:
        facility:
          power_zone: "DC1-R1-PZ-B"
    Router_DC1_R2_RK01:
      attrs:
        facility:
          power_zone: "DC1-R1-PZ-A"

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.power_zone
      name_template: PowerZone_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        assert "PowerZone_DC1-R1-PZ-A" in scenario.network.risk_groups
        assert "PowerZone_DC1-R1-PZ-B" in scenario.network.risk_groups

        assert (
            "PowerZone_DC1-R1-PZ-A"
            in scenario.network.nodes["Router_DC1_R1_RK01"].risk_groups
        )
        assert (
            "PowerZone_DC1-R1-PZ-B"
            in scenario.network.nodes["Router_DC1_R1_RK02"].risk_groups
        )
        assert (
            "PowerZone_DC1-R1-PZ-A"
            in scenario.network.nodes["Router_DC1_R2_RK01"].risk_groups
        )


class TestRiskGroupGenerationEdgeCases:
    """Edge cases for risk group generation."""

    def test_generate_no_matches(self) -> None:
        """No groups generated when attribute is missing from all entities."""
        yaml_content = """
network:
  nodes:
    Router_DC1: {}
    Router_DC2: {}

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.nonexistent
      name_template: Missing_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        # No groups should be generated (attribute doesn't exist)
        missing_groups = [
            name for name in scenario.network.risk_groups if name.startswith("Missing_")
        ]
        assert len(missing_groups) == 0

    def test_generate_with_explicit_groups(self) -> None:
        """Generate works alongside explicit risk groups."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      risk_groups: ["Building_DC1_Manual"]
      attrs:
        facility:
          room_id: "DC1-R1"
    Router_DC2:
      attrs:
        facility:
          room_id: "DC1-R2"

risk_groups:
  - "Building_DC1_Manual"
  - generate:
      entity_scope: node
      group_by: facility.room_id
      name_template: Room_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Should have both explicit and generated groups
        assert "Building_DC1_Manual" in scenario.network.risk_groups
        assert "Room_DC1-R1" in scenario.network.risk_groups
        assert "Room_DC1-R2" in scenario.network.risk_groups

        # Router_DC1 should be in both explicit and generated
        assert "Building_DC1_Manual" in scenario.network.nodes["Router_DC1"].risk_groups
        assert "Room_DC1-R1" in scenario.network.nodes["Router_DC1"].risk_groups

    def test_generate_multiple_blocks(self) -> None:
        """Multiple generate blocks create separate risk group hierarchies."""
        yaml_content = """
network:
  nodes:
    Router_DC1_R1:
      attrs:
        facility:
          building_id: "DC1"
          power_zone: "DC1-R1-PZ-A"
    Router_DC2_R1:
      attrs:
        facility:
          building_id: "DC2"
          power_zone: "DC2-R1-PZ-A"

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.building_id
      name_template: Building_${value}
  - generate:
      entity_scope: node
      group_by: facility.power_zone
      name_template: PowerZone_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Should have groups from both generate blocks
        assert "Building_DC1" in scenario.network.risk_groups
        assert "Building_DC2" in scenario.network.risk_groups
        assert "PowerZone_DC1-R1-PZ-A" in scenario.network.risk_groups
        assert "PowerZone_DC2-R1-PZ-A" in scenario.network.risk_groups

        # Router should be in both building and power zone groups
        assert "Building_DC1" in scenario.network.nodes["Router_DC1_R1"].risk_groups
        assert (
            "PowerZone_DC1-R1-PZ-A"
            in scenario.network.nodes["Router_DC1_R1"].risk_groups
        )

    def test_generate_null_values_skipped(self) -> None:
        """Entities with null attribute values are skipped during generation."""
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
          building_id: null
    Router_DC3: {}

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.building_id
      name_template: Building_${value}
"""
        scenario = Scenario.from_yaml(yaml_content)

        # Only Building_DC1 should be generated (null and missing are skipped)
        building_groups = [
            name
            for name in scenario.network.risk_groups
            if name.startswith("Building_")
        ]
        assert building_groups == ["Building_DC1"]

        # Only Router_DC1 should be a member
        assert "Building_DC1" in scenario.network.nodes["Router_DC1"].risk_groups
        assert "Building_DC1" not in scenario.network.nodes["Router_DC2"].risk_groups
        assert "Building_DC1" not in scenario.network.nodes["Router_DC3"].risk_groups


class TestRiskGroupGenerationValidation:
    """Validation tests for generate blocks."""

    def test_missing_group_by(self) -> None:
        """Error when group_by is missing (schema validation)."""
        import jsonschema

        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - generate:
      entity_scope: node
      name_template: Test_${value}
"""
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            Scenario.from_yaml(yaml_content)

        assert "group_by" in str(exc_info.value)

    def test_missing_name_template(self) -> None:
        """Error when name_template is missing (schema validation)."""
        import jsonschema

        yaml_content = """
network:
  nodes:
    Router_DC1: {}

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.building_id
"""
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            Scenario.from_yaml(yaml_content)

        assert "name_template" in str(exc_info.value)

    def test_name_template_without_placeholder(self) -> None:
        """Error when name_template lacks ${value} placeholder."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      attrs:
        facility:
          building_id: "DC1"

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.building_id
      name_template: StaticBuildingName
"""
        with pytest.raises(ValueError) as exc_info:
            Scenario.from_yaml(yaml_content)

        assert "${value}" in str(exc_info.value)

    def test_generated_name_collision_with_explicit(self) -> None:
        """Error when generated group name collides with explicit group."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      attrs:
        facility:
          building_id: "DC1"

risk_groups:
  # Explicit group that will collide with generated name
  - name: "Building_DC1"
    attrs:
      explicit: true
  # Generate block that produces same name
  - generate:
      entity_scope: node
      group_by: facility.building_id
      name_template: Building_${value}
"""
        with pytest.raises(ValueError) as exc_info:
            Scenario.from_yaml(yaml_content)

        error_msg = str(exc_info.value)
        assert "Building_DC1" in error_msg
        assert "conflicts" in error_msg.lower() or "collision" in error_msg.lower()

    def test_generated_name_collision_between_generate_blocks(self) -> None:
        """Error when two generate blocks produce same name."""
        yaml_content = """
network:
  nodes:
    Router_DC1:
      attrs:
        facility:
          building_id: "DC1"
          campus_id: "DC1"

risk_groups:
  - generate:
      entity_scope: node
      group_by: facility.building_id
      name_template: Site_${value}
  - generate:
      entity_scope: node
      group_by: facility.campus_id
      name_template: Site_${value}
"""
        with pytest.raises(ValueError) as exc_info:
            Scenario.from_yaml(yaml_content)

        error_msg = str(exc_info.value)
        assert "Site_DC1" in error_msg
        assert "conflicts" in error_msg.lower()
