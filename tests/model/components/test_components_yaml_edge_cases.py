"""Edge-case tests for ComponentsLibrary YAML parsing.

Covers presence-based dispatch of the top-level 'components' key and the
warning emitted when a component definition uses 'cost' instead of 'capex'.
"""

import logging

from ngraph.model.components import ComponentsLibrary


def test_from_yaml_empty_components_mapping_yields_empty_library() -> None:
    """An explicit `components: {}` yields an empty library, not a phantom one."""
    lib = ComponentsLibrary.from_yaml("components: {}")
    assert lib.components == {}


def test_from_yaml_null_components_yields_empty_library() -> None:
    """An explicit `components:` (null) yields an empty library."""
    lib = ComponentsLibrary.from_yaml("components:\n")
    assert lib.components == {}


def test_from_yaml_empty_components_ignores_sibling_keys() -> None:
    """Sibling top-level keys are not parsed as components when key is present."""
    yaml_str = """
components: {}
other_section:
  capex: 5
"""
    lib = ComponentsLibrary.from_yaml(yaml_str)
    assert lib.components == {}


def test_build_component_warns_on_cost_key(caplog) -> None:
    """A leftover 'cost' key logs a warning and contributes 0 to capex."""
    yaml_str = """
components:
  Switch:
    component_type: chassis
    cost: 20000
"""
    with caplog.at_level(logging.WARNING, logger="ngraph.model.components"):
        lib = ComponentsLibrary.from_yaml(yaml_str)

    comp = lib.get("Switch")
    assert comp is not None
    assert comp.capex == 0.0
    assert comp.attrs["cost"] == 20000
    assert any(
        "'cost'" in record.message
        and "Switch" in str(record.args or ())
        or "Switch" in record.getMessage()
        for record in caplog.records
    )
    assert any("capex" in record.getMessage() for record in caplog.records)


def test_build_component_no_warning_with_capex(caplog) -> None:
    """No warning is emitted when 'capex' is used as documented."""
    yaml_str = """
components:
  Switch:
    component_type: chassis
    capex: 20000
"""
    with caplog.at_level(logging.WARNING, logger="ngraph.model.components"):
        lib = ComponentsLibrary.from_yaml(yaml_str)

    comp = lib.get("Switch")
    assert comp is not None
    assert comp.capex == 20000.0
    assert not caplog.records
