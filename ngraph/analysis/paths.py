"""Named SPF/KSP selection and the declared cross-pair merge."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from operator import index as as_index
from typing import TYPE_CHECKING, Literal

import netgraph_core as ngc
import numpy as np

from ngraph.analysis.demands import selected_pairs
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.topology import PreparedTopology
from ngraph.model.selectors import Selector
from ngraph.results import PathAnalysis, PathRow
from ngraph.utils.values import flag, optional_flag, optional_integer, own

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


@dataclass(frozen=True)
class PathQuery:
    source: Selector
    target: Selector
    mode: Literal["combine", "pairwise"] = "combine"
    options: ngc.SpfOptions | ngc.KspOptions = field(
        default_factory=lambda: ngc.SpfOptions(ngc.Direction.FORWARD)
    )
    costs_only: bool = False
    max_paths: int | None = None
    split_parallel_edges: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, Selector) or not isinstance(
            self.target, Selector
        ):
            raise TypeError(
                f"paths endpoints: expected Selectors, got {(self.source, self.target)!r}"
            )
        if not isinstance(self.mode, str) or self.mode not in ("combine", "pairwise"):
            raise ValueError(
                f"paths.mode: expected combine or pairwise, got {self.mode!r}"
            )
        if not isinstance(self.options, (ngc.SpfOptions, ngc.KspOptions)):
            raise TypeError(
                f"paths.options: expected native SpfOptions or KspOptions, got {self.options!r}"
            )
        own(
            self,
            mode=str.__str__(self.mode),
            costs_only=flag(self.costs_only, "paths.costs_only"),
        )
        if isinstance(self.options, ngc.SpfOptions):
            if (
                self.options.direction != ngc.Direction.FORWARD
                or self.options.targets is not None
            ):
                raise ValueError(
                    "paths SPF requires FORWARD and targets=None; Selectors supply endpoints"
                )
            if (
                self.options.tie_break != ngc.RouteTieBreak.FEWER_HOPS
                and self.options.multipath
                and self.options.parallel_edges
            ):
                raise ValueError(
                    "paths SPF tie_break requires multipath=False or parallel_edges=False"
                )
            own(
                self,
                max_paths=optional_integer(
                    self.max_paths, "paths.max_paths", minimum=1
                ),
                split_parallel_edges=optional_flag(
                    self.split_parallel_edges, "paths.split_parallel_edges"
                ),
            )
        else:
            if self.max_paths is not None:
                raise ValueError("paths.max_paths: SPF-only")
            if self.split_parallel_edges is not None:
                raise ValueError("paths.split_parallel_edges: SPF-only")
            ceiling = self.options.cost_ceiling
            if isinstance(ceiling, ngc.AbsoluteCost) and ceiling.cost < 0:
                raise ValueError(
                    "paths.cost_ceiling: absolute cost must be nonnegative"
                )
            if isinstance(ceiling, ngc.CostStretch) and ceiling.factor < 1:
                raise ValueError("paths.cost_ceiling: stretch must be at least one")


def _residual(topology: PreparedTopology, residual) -> tuple[int, ...] | None:
    if residual is None:
        return None
    if len(residual) != topology.graph.num_edges():
        raise ValueError("paths.residual: length must equal graph edge count")
    capacities = topology.graph.edge_capacity_units()
    values = []
    for index, value in enumerate(residual):
        if isinstance(value, (bool, np.bool_)):
            raise TypeError(f"paths.residual[{index}]: expected integer units")
        try:
            units = as_index(value)
        except TypeError as exc:
            raise TypeError(f"paths.residual[{index}]: expected integer units") from exc
        if not 0 <= units <= int(capacities[index]):
            raise ValueError(f"paths.residual[{index}]: outside edge capacity")
        values.append(units)
    return tuple(values)


def paths(prepared: PreparedScenario, query: PathQuery) -> PathAnalysis:
    topology = prepared.topology
    pairs = selected_pairs(
        prepared.scenario.network, query.source, query.target, query.mode, "paths"
    )
    native = query.options
    mask = (
        topology.disabled
        if native.eligibility is None
        else ngc.Eligibility.intersect(topology.disabled, native.eligibility)
    )
    residual = _residual(topology, native.residual)
    spf = isinstance(native, ngc.SpfOptions)
    count = None
    if spf:
        minimum = native.min_residual
        if isinstance(minimum, (bool, np.bool_)):
            raise TypeError("paths.min_residual: expected integer >=1")
        try:
            minimum = as_index(minimum)
        except TypeError as exc:
            raise TypeError("paths.min_residual: expected integer >=1") from exc
        if minimum < 1:
            raise ValueError("paths.min_residual: expected integer >=1")
        algorithm = "spf"
        split = (
            query.split_parallel_edges
            if query.split_parallel_edges is not None
            else False
        )
    else:
        algorithm = "ksp"
        minimum = None
        split = None
        if isinstance(native.k, (bool, np.bool_)):
            raise TypeError("paths.k: expected integer >=1")
        try:
            count = as_index(native.k)
        except TypeError as exc:
            raise TypeError("paths.k: expected integer >=1") from exc
        if count < 1:
            raise ValueError("paths.k: expected integer >=1")
    rows = []
    for index, endpoints in enumerate(pairs):
        identity = f"pair-{index:06d}"
        if endpoints.sources == endpoints.destinations and len(endpoints.sources) == 1:
            rows.append(
                PathRow(
                    identity, endpoints, "self", 0, None if query.costs_only else ()
                )
            )
            continue
        concrete = tuple(product(endpoints.sources, endpoints.destinations))
        candidates = []
        for pair_index, (source, destination) in enumerate(concrete):
            source_id = topology.node_id_by_name[source]
            destination_id = topology.node_id_by_name[destination]
            if spf:
                assert minimum is not None
                options = ngc.SpfOptions(
                    ngc.Direction.FORWARD,
                    targets=[destination_id],
                    tie_break=native.tie_break,
                    multipath=native.multipath,
                    parallel_edges=native.parallel_edges,
                    residual=residual,
                    min_residual=minimum,
                    eligibility=mask,
                )
                found = ngc.spf(topology.graph, [source_id], options)
                if found.target_cost is not None:
                    candidates.append(
                        (
                            found.target_cost,
                            pair_index,
                            source_id,
                            destination_id,
                            found.dag,
                        )
                    )
            else:
                options = ngc.KspOptions(
                    native.k,
                    tie_break=native.tie_break,
                    parallel_edges=native.parallel_edges,
                    cost_ceiling=native.cost_ceiling,
                    residual=residual,
                    eligibility=mask,
                )
                for rank, (cost, path) in enumerate(
                    ngc.ksp(topology.graph, source_id, destination_id, options)
                ):
                    candidates.append((cost, pair_index, rank, path))
        candidates.sort(key=lambda row: row[:2] if spf else row[:3])
        cost = candidates[0][0] if candidates else None
        selected = []
        if not query.costs_only:
            if spf:
                for candidate_cost, _, source_id, destination_id, dag in candidates:
                    if candidate_cost != cost:
                        break
                    remaining = (
                        None
                        if query.max_paths is None
                        else query.max_paths - len(selected)
                    )
                    if remaining == 0:
                        break
                    selected.extend(
                        ngc.resolve_to_paths(
                            topology.graph,
                            dag,
                            source_id,
                            destination_id,
                            split_parallel_edges=bool(split),
                            max_paths=remaining,
                        )
                    )
            else:
                selected = [row[3] for row in candidates[:count]]
        rows.append(
            PathRow(
                identity,
                endpoints,
                "paths",
                cost,
                None if query.costs_only else tuple(selected),
            )
        )
    return PathAnalysis(
        prepared,
        (),
        analysis_metadata(1),
        algorithm,
        query.mode,
        query.costs_only,
        tuple(rows),
        query,
    )
