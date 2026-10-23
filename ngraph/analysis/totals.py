"""Exact converged-state totals with the declared reference denominator."""

from fractions import Fraction

from ngraph.results import PlacementTotals


def placement_totals(entries) -> PlacementTotals:
    """Totals of (demand id, reference request units, native result) entries."""
    requested = delivered = unadmitted = source_drop = edge_drop = 0
    feasible = True
    for identity, reference, result in entries:
        value = result.delivered
        drops = result.edge_drops
        source = result.source_drops
        unadmitted_value = result.unadmitted
        if unadmitted_value is None:
            raise ValueError(
                f"placement {identity}: finite request has no unadmitted count"
            )
        requested += reference
        delivered += value
        unadmitted += unadmitted_value
        source_drop += source
        edge_drop += sum(amount for _, amount in drops)
        feasible = (
            feasible
            and value == reference
            and unadmitted_value == 0
            and source == 0
            and not any(amount for _, amount in drops)
        )
    return PlacementTotals(
        requested,
        delivered,
        unadmitted,
        source_drop,
        edge_drop,
        requested - delivered,
        Fraction(delivered, requested) if requested else Fraction(1),
        feasible,
    )
