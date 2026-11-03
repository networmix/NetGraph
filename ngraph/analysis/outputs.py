"""Native call outputs: the user's selection plus data needed by a report."""

import netgraph_core as ngc


def required_outputs(
    selected: ngc.OutputOptions, *, by_source: bool = False, program: bool = False
) -> ngc.OutputOptions:
    """Keep every user flag and add only required completed-result fields."""
    if (not by_source or selected.by_source) and (not program or selected.program):
        return selected
    return ngc.OutputOptions(
        edge_flows=selected.edge_flows,
        residual=selected.residual,
        edge_reservations=selected.edge_reservations,
        saturated_boundary_edges=selected.saturated_boundary_edges,
        min_cut=selected.min_cut,
        by_source=selected.by_source or by_source,
        program=selected.program or program,
    )
