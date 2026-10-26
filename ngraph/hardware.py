"""One inventory of the hardware installed in a network.

Each node platform and each link-end optic is one ``HardwareUse``. The
explorer and the CostPower step both read the inventory; each groups it in
its own way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ngraph.model.components import (
    Component,
    ComponentsLibrary,
    _require_mapping,
    resolve_link_end,
    resolve_node_hardware,
    totals_with_multiplier,
)

if TYPE_CHECKING:
    from ngraph.model.network import Link, Network


__all__ = [
    "hardware_inventory",
    "HardwareInventory",
    "HardwareUse",
    "link_active",
    "resolve_link_end",
]


def link_active(network: Network, link: Link) -> bool:
    """Return True when the link and both of its end nodes are enabled."""
    return not (
        link.disabled
        or network.nodes[link.source].disabled
        or network.nodes[link.target].disabled
    )


@dataclass(frozen=True)
class HardwareUse:
    """One installed platform or link-end optic.

    Attributes:
        node: Node the hardware sits at; consumers group by this name.
        link: Key of the link in ``Network.links`` for an optic; None for a
            node platform.
        end: ``"source"`` or ``"target"`` for an optic; None for a platform.
        component: The library component.
        count: Declared count.
        bom_count: Count in the bill of materials: the count, rounded up for
            an exclusive link end.
        capex: Component capex (children included) times ``count``.
        power_watts: Component typical power times ``count``.
        capacity: Component capacity times ``count``.
        active: In the enabled view: the node is enabled (platform), or the
            link is active (optic, see ``link_active``).
    """

    node: str
    link: Optional[str]
    end: Optional[str]
    component: Component
    count: float
    bom_count: float
    capex: float
    power_watts: float
    capacity: float
    active: bool


@dataclass(frozen=True)
class HardwareInventory:
    """The hardware uses of a network and its references to unknown components.

    Attributes:
        uses: Node platforms in node order, then each link's source end and
            target end in link order (the order of every sum over them).
        unknown: ``(entity, end, name)`` for each reference to a component the
            library lacks: a node name with end None, or a link key with its
            end.
    """

    uses: tuple[HardwareUse, ...]
    unknown: tuple[tuple[str, Optional[str], object], ...]


def _use(node, link, end, component, count, bom_count, active) -> HardwareUse:
    capex, power, capacity = totals_with_multiplier(component, count)
    return HardwareUse(
        node, link, end, component, count, bom_count, capex, power, capacity, active
    )


def hardware_inventory(
    network: Network, library: ComponentsLibrary
) -> HardwareInventory:
    """Resolve every node's and link end's hardware, in that order.

    A link end counts only where its endpoint node has a platform.

    Raises:
        ValueError: If any node, link or link end has a ``hardware`` value
            that is not a mapping or a count that is not a finite positive
            number; the message starts with the entity
            (``node <name>``, ``link <key>``, ``link <key> source end``).
    """
    uses: list[HardwareUse] = []
    unknown: list[tuple[str, Optional[str], object]] = []
    has_platform: dict[str, bool] = {}
    for node in network.nodes.values():
        try:
            component, count = resolve_node_hardware(node.attrs, library)
        except ValueError as exc:
            raise ValueError(f"node {node.name}: {exc}") from exc
        has_platform[node.name] = component is not None
        hardware = node.attrs.get("hardware")
        if component is not None:
            uses.append(
                _use(node.name, None, None, component, count, count, not node.disabled)
            )
        elif hardware:
            unknown.append((node.name, None, hardware.get("component")))
    for key, link in network.links.items():
        hardware = link.attrs.get("hardware")
        if hardware is None:
            continue
        try:
            _require_mapping(hardware)
        except ValueError as exc:
            raise ValueError(f"link {key}: {exc}") from exc
        active = link_active(network, link)
        for end, endpoint in (("source", link.source), ("target", link.target)):
            spec = hardware.get(end)
            if spec is None:
                continue
            try:
                component, count, exclusive = resolve_link_end(spec, library)
            except ValueError as exc:
                raise ValueError(f"link {key} {end} end: {exc}") from exc
            if component is None:
                if spec.get("component"):
                    unknown.append((key, end, spec["component"]))
            elif has_platform[endpoint]:
                bom_count = float(math.ceil(count)) if exclusive else count
                uses.append(
                    _use(endpoint, key, end, component, count, bom_count, active)
                )
    return HardwareInventory(tuple(uses), tuple(unknown))
