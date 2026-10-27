"""Hardware uses the inventory and the one-end resolver as its public boundary."""

import ngraph.model.components as components


def test_the_old_two_end_resolver_is_removed_and_disclosed():
    retired = "resolve_" + "link_end_components"
    assert not hasattr(components, retired)
