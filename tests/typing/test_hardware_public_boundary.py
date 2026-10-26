"""Hardware uses the inventory and the one-end resolver as its public boundary."""

from pathlib import Path

import ngraph.model.components as components


def test_the_old_two_end_resolver_is_removed_and_disclosed():
    retired = "resolve_" + "link_end_components"
    assert not hasattr(components, retired)
    release = (
        (Path(__file__).resolve().parents[2] / "CHANGELOG.md")
        .read_text()
        .split("## [0.24.1]")[0]
    )
    assert f"`ngraph.model.components.{retired}`" in release
    assert "`ngraph.hardware.hardware_inventory`" in release
