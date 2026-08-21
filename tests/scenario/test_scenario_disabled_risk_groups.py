"""Regression tests for disabled risk groups and late-assigned members.

The disable cascade for risk groups declared ``disabled: true`` must run after
membership rules and generate blocks, so entities assigned to groups by those
mechanisms are disabled as well.
"""

from ngraph.scenario import Scenario


def test_disabled_group_disables_membership_rule_nodes() -> None:
    """Nodes matched by a membership rule of a disabled group end up disabled."""
    yaml_content = """
network:
  nodes:
    RouterA:
      attrs:
        power_zone: "PZ-A"
    RouterB:
      attrs:
        power_zone: "PZ-A"
    RouterC:
      attrs:
        power_zone: "PZ-B"

risk_groups:
  - name: PowerZoneA
    disabled: true
    membership:
      scope: node
      match:
        conditions:
          - attr: power_zone
            op: "=="
            value: "PZ-A"
"""
    scenario = Scenario.from_yaml(yaml_content)
    network = scenario.network

    assert "PowerZoneA" in network.nodes["RouterA"].risk_groups
    assert "PowerZoneA" in network.nodes["RouterB"].risk_groups
    assert network.nodes["RouterA"].disabled is True
    assert network.nodes["RouterB"].disabled is True
    # Unmatched node remains enabled
    assert network.nodes["RouterC"].disabled is False


def test_disabled_group_disables_membership_rule_links() -> None:
    """Links matched by a membership rule of a disabled group end up disabled."""
    yaml_content = """
network:
  nodes:
    NYC: {}
    CHI: {}
    LA: {}
  links:
    - source: NYC
      target: CHI
      attrs:
        conduit_id: "C1"
    - source: CHI
      target: LA
      attrs:
        conduit_id: "C2"

risk_groups:
  - name: Conduit_C1
    disabled: true
    membership:
      scope: link
      match:
        conditions:
          - attr: conduit_id
            op: "=="
            value: "C1"
"""
    scenario = Scenario.from_yaml(yaml_content)
    network = scenario.network

    by_conduit = {link.attrs.get("conduit_id"): link for link in network.links.values()}
    assert "Conduit_C1" in by_conduit["C1"].risk_groups
    assert by_conduit["C1"].disabled is True
    assert by_conduit["C2"].disabled is False


def test_disabled_parent_cascades_to_membership_rule_children() -> None:
    """Recursive disable covers children added to a disabled parent via rules."""
    yaml_content = """
network:
  nodes:
    NodeC1:
      risk_groups: ["Conduit1"]
    NodeC2:
      risk_groups: ["Conduit2"]
    NodeOther: {}

risk_groups:
  - name: Conduit1
    attrs:
      route: "NYC-CHI"
  - name: Conduit2
    attrs:
      route: "NYC-CHI"
  - name: Route_NYC_CHI
    disabled: true
    membership:
      scope: risk_group
      match:
        conditions:
          - attr: route
            op: "=="
            value: "NYC-CHI"
"""
    scenario = Scenario.from_yaml(yaml_content)
    network = scenario.network

    parent = network.risk_groups["Route_NYC_CHI"]
    child_names = {child.name for child in parent.children}
    assert child_names == {"Conduit1", "Conduit2"}

    # Members of children added by the membership rule are disabled
    assert network.nodes["NodeC1"].disabled is True
    assert network.nodes["NodeC2"].disabled is True
    assert network.nodes["NodeOther"].disabled is False


def test_disabled_group_still_disables_direct_members() -> None:
    """Moving the cascade later keeps direct-member disabling intact."""
    yaml_content = """
network:
  nodes:
    A:
      risk_groups: ["RG1"]
    B: {}

risk_groups:
  - name: RG1
    disabled: true
"""
    scenario = Scenario.from_yaml(yaml_content)
    network = scenario.network

    assert network.nodes["A"].disabled is True
    assert network.nodes["B"].disabled is False
