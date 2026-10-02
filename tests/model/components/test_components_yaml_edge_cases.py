"""Edge-case tests for ComponentsLibrary YAML parsing.

Covers presence-based dispatch of the top-level 'components' key and the
rejection of keys outside the component fields.
"""

import logging

import pytest

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


def test_build_component_rejects_unknown_keys() -> None:
    """Keys outside the component fields raise; 'cost' gets a capex hint."""
    yaml_str = """
components:
  Switch:
    component_type: chassis
    cost: 20000
"""
    with pytest.raises(ValueError, match="unrecognized key.*cost.*Use 'capex'"):
        ComponentsLibrary.from_yaml(yaml_str)

    nested = {"Chassis": {"children": {"Card": {"vendor": "x"}}}}
    with pytest.raises(ValueError, match="Component 'Card'.*vendor"):
        ComponentsLibrary.from_dict(nested)


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
