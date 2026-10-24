"""What each failure state forwards: one case's native demand configs per state.

``converged`` evaluates the declared demands on the failed topology (a WCMP
controller set on the case's own tables); ``stale`` forwards each demand's
baseline program unchanged, LOSSY, at its baseline admitted total, with the
case's failures as black holes; ``repair`` forwards the baseline program under
the failure mask (native repair: survivors re-split, no new search) at the
declared request, except that declared group caps get a table recompiled from
the surviving routes. Nothing here forwards traffic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import netgraph_core as ngc

from ngraph.results import CaseState, FailureCase, ForwardingFailure

# The two outcomes of native lossy forwarding (CONTRACT 9.4) a case can report.
LOSS_ITERATION = frozenset(
    (
        "lossy forwarding iteration entered a period-2 cycle",
        "lossy forwarding iteration did not reach a fixed point within the round limit",
    )
)


def forwarding_failure(exc: ValueError) -> ForwardingFailure | None:
    """The case outcome a native error stands for, or None for any other error."""
    message = str(exc)
    return ForwardingFailure(message) if message in LOSS_ITERATION else None


@dataclass(frozen=True)
class Baseline:
    """Each demand's baseline program and admitted total, by demand id."""

    programs: Mapping[str, ngc.ForwardingProgram]
    admitted: Mapping[str, int]

    @classmethod
    def of(cls, state: CaseState) -> Baseline:
        if state.failure is not None:
            raise ValueError(
                f"case baseline: {state.failure.message}; stale and repair need "
                "the baseline programs"
            )
        programs, admitted = {}, {}
        for row in state.rows:
            if row.result.program is None:
                raise RuntimeError(f"demand.{row.id}: the baseline has no program")
            programs[row.id] = row.result.program
            admitted[row.id] = row.result.admitted
        return cls(programs, admitted)


def simultaneous_role(routing) -> str:
    """How a model joins a SIMULTANEOUS list (CONTRACT 11.1).

    ``tunnels`` (T1, T2) are set up first and forwarded; a live
    ``controller`` cannot be LOSSY, so its prepared program is imported;
    every other model is replaced directly on the common view.
    """
    if isinstance(routing, ngc.DistributedTE) or (
        isinstance(routing, ngc.CentralizedTE) and routing.tunnel_count is not None
    ):
        return "tunnels"
    if isinstance(routing, ngc.CentralizedTE) or (
        isinstance(routing, ngc.ShortestPaths)
        and routing.allocation == ngc.RouteAllocation.OPTIMIZED
    ):
        return "controller"
    return "direct"


def participants(
    topology,
    setup,
    demands,
    controlled,
    case: FailureCase,
    state,
    requests,
    baseline,
    tables,
):
    """Per demand, in demand order: (native config, policy eligibility, request).

    ``controlled`` holds the demand ids the WCMP controller programs;
    ``tables`` the case's tables by destination (None: the demands' own
    configs, as in the baseline case).
    """
    entries = []
    for demand in demands.demands:
        request = requests[demand.id]
        if state == "stale":
            program = ngc.Pinned(
                baseline.programs[demand.id], black_holes=case.eligibility
            )
            config = ngc.FlowPolicyConfig(
                routing=program, admission=ngc.Admission.LOSSY
            )
            entries.append((config, topology.disabled, baseline.admitted[demand.id]))
        elif tables is not None and demand.id in controlled:
            table = tables[demand.endpoints.destinations[0]]
            config = setup.leaf_config(
                topology, table, demand.endpoints, case.eligibility
            )
            entries.append((config, topology.disabled, request))
        elif state == "repair":
            config = ngc.FlowPolicyConfig(
                routing=ngc.Pinned(baseline.programs[demand.id]),
                admission=demand.config.admission,
            )
            entries.append((config, case.eligibility, request))
        else:
            entries.append((demand.config, case.eligibility, request))
    return tuple(entries)
