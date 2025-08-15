"""Unified flow result containers for failure-analysis iterations.

Defines small, serializable dataclasses that capture per-iteration outcomes
for capacity and demand-placement style analyses in a unit-agnostic form.

Objects expose `to_dict()` that returns JSON-safe primitives. Float-keyed
distributions are normalized to string keys, and arbitrary `data` payloads are
sanitized. These dicts are written under `data.flow_results` by steps.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Dict, List, Optional

from ngraph.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class FlowEntry:
    """Represents a single source→destination flow outcome within an iteration.

    Fields are unit-agnostic. Callers can interpret numbers as needed for
    presentation (e.g., Gbit/s).

    Args:
        source: Source identifier.
        destination: Destination identifier.
        priority: Priority/class for traffic placement scenarios. Zero when not applicable.
        demand: Requested volume for this flow.
        placed: Delivered volume for this flow.
        dropped: Unmet volume (``demand - placed``).
        cost_distribution: Optional distribution of placed volume by path cost.
        data: Optional per-flow details (e.g., min-cut edges, used edges).
    """

    source: str
    destination: str
    priority: int
    demand: float
    placed: float
    dropped: float
    cost_distribution: Dict[float, float] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate invariants and types for early error detection.

        Raises:
            ValueError: If any numeric fields are NaN/inf or logically inconsistent.
            TypeError: If fields have unexpected types.
        """
        if not isinstance(self.source, str) or not self.source:
            logger.error("FlowEntry.source must be a non-empty string: %r", self.source)
            raise TypeError("FlowEntry.source must be a non-empty string")
        if not isinstance(self.destination, str) or not self.destination:
            logger.error(
                "FlowEntry.destination must be a non-empty string: %r", self.destination
            )
            raise TypeError("FlowEntry.destination must be a non-empty string")
        if not isinstance(self.priority, int) or self.priority < 0:
            logger.error(
                "FlowEntry.priority must be a non-negative int: %r", self.priority
            )
            raise TypeError("FlowEntry.priority must be a non-negative int")

        # Basic numeric validation
        for name, value in (
            ("demand", self.demand),
            ("placed", self.placed),
            ("dropped", self.dropped),
        ):
            if not isinstance(value, (int, float)):
                logger.error("FlowEntry.%s must be numeric: %r", name, value)
                raise TypeError(f"FlowEntry.{name} must be numeric")
            if not math.isfinite(float(value)):
                logger.error("FlowEntry.%s must be finite: %r", name, value)
                raise ValueError(f"FlowEntry.{name} must be finite")

        # Non-negativity with tolerance for floating-point artifacts on 'dropped'
        if float(self.demand) < 0.0:
            logger.error("FlowEntry.demand must be non-negative: %r", self.demand)
            raise ValueError("FlowEntry.demand must be non-negative")
        if float(self.placed) < 0.0:
            logger.error("FlowEntry.placed must be non-negative: %r", self.placed)
            raise ValueError("FlowEntry.placed must be non-negative")
        if float(self.dropped) < 0.0:
            # Clamp tiny negative values caused by rounding noise
            if abs(float(self.dropped)) <= 1e-9:
                logger.debug(
                    "Normalizing tiny negative FlowEntry.dropped %.12g to 0.0",
                    float(self.dropped),
                )
                self.dropped = 0.0
            else:
                logger.error("FlowEntry.dropped must be non-negative: %r", self.dropped)
                raise ValueError("FlowEntry.dropped must be non-negative")

        # Consistency: dropped ≈ demand - placed
        expected_drop = float(self.demand) - float(self.placed)
        if abs(float(self.dropped) - expected_drop) > 1e-9:
            logger.error(
                "FlowEntry.dropped inconsistent (demand - placed != dropped): demand=%.9g placed=%.9g dropped=%.9g",
                float(self.demand),
                float(self.placed),
                float(self.dropped),
            )
            raise ValueError(
                "FlowEntry.dropped must equal demand - placed (within tolerance)"
            )

        # Validate cost distribution: numeric, finite, non-negative
        if not isinstance(self.cost_distribution, dict):
            logger.error("FlowEntry.cost_distribution must be a dict")
            raise TypeError("FlowEntry.cost_distribution must be a dict")
        for k, v in self.cost_distribution.items():
            try:
                k_f = float(k)
                v_f = float(v)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "Invalid cost_distribution entry: %r -> %r (%s)", k, v, exc
                )
                raise TypeError(
                    "FlowEntry.cost_distribution keys/values must be numeric"
                ) from exc
            if not (math.isfinite(k_f) and math.isfinite(v_f)) or v_f < 0.0:
                logger.error(
                    "Invalid cost_distribution entry (non-finite or negative): %r -> %r",
                    k,
                    v,
                )
                raise ValueError("FlowEntry.cost_distribution contains invalid entries")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""

        # Canonicalize cost_distribution keys as strings to avoid float artifacts
        # and ensure stable JSON. Use decimal quantization for determinism.
        def _fmt_float_key(x: float, places: int = 9) -> str:
            q = Decimal(10) ** -places
            try:
                d = Decimal(str(float(x))).quantize(q, rounding=ROUND_HALF_EVEN)
                # Normalize to remove trailing zeros and exponent when possible
                d = d.normalize()
                return format(d, "f") if d == d.to_integral() else format(d, "f")
            except Exception:  # pragma: no cover - defensive
                return str(x)

        normalized_costs: Dict[str, float] = {}
        for k, v in self.cost_distribution.items():
            try:
                key_str = _fmt_float_key(float(k))
                normalized_costs[key_str] = float(v)
            except Exception:  # pragma: no cover - defensive
                normalized_costs[str(k)] = float(v)
        d = asdict(self)
        d["cost_distribution"] = normalized_costs
        # Ensure per-flow data payload is JSON-safe to avoid late failures
        d["data"] = _ensure_json_safe(self.data)
        return d


@dataclass(slots=True)
class FlowSummary:
    """Aggregated metrics across all flows in one iteration.

    Args:
        total_demand: Sum of all demands in this iteration.
        total_placed: Sum of all delivered volumes in this iteration.
        overall_ratio: ``total_placed / total_demand`` when demand > 0, else 1.0.
        dropped_flows: Number of flow entries with non-zero drop.
        num_flows: Total number of flows considered.
    """

    total_demand: float
    total_placed: float
    overall_ratio: float
    dropped_flows: int
    num_flows: int

    def __post_init__(self) -> None:
        """Validate summary invariants for correctness.

        Raises:
            ValueError: If totals/ratio are inconsistent or invalid.
        """
        for name, value in (
            ("total_demand", self.total_demand),
            ("total_placed", self.total_placed),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                logger.error("FlowSummary.%s must be finite numeric: %r", name, value)
                raise ValueError(f"FlowSummary.{name} must be finite numeric")
            if float(value) < 0.0:
                logger.error("FlowSummary.%s must be non-negative: %r", name, value)
                raise ValueError(f"FlowSummary.{name} must be non-negative")

        if not isinstance(self.dropped_flows, int) or self.dropped_flows < 0:
            logger.error(
                "FlowSummary.dropped_flows must be non-negative int: %r",
                self.dropped_flows,
            )
            raise ValueError("FlowSummary.dropped_flows must be non-negative int")
        if not isinstance(self.num_flows, int) or self.num_flows < 0:
            logger.error(
                "FlowSummary.num_flows must be non-negative int: %r", self.num_flows
            )
            raise ValueError("FlowSummary.num_flows must be non-negative int")

        # Ratio consistency
        td = float(self.total_demand)
        tp = float(self.total_placed)
        expected_ratio = 1.0 if td == 0.0 else (tp / td)
        if not isinstance(self.overall_ratio, (int, float)) or not math.isfinite(
            float(self.overall_ratio)
        ):
            logger.error(
                "FlowSummary.overall_ratio must be finite numeric: %r",
                self.overall_ratio,
            )
            raise ValueError("FlowSummary.overall_ratio must be finite numeric")
        if abs(float(self.overall_ratio) - expected_ratio) > 1e-9:
            logger.error(
                "FlowSummary.overall_ratio inconsistent: expected %.12g got %.12g",
                expected_ratio,
                float(self.overall_ratio),
            )
            raise ValueError("FlowSummary.overall_ratio inconsistent with totals")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return asdict(self)


@dataclass(slots=True)
class FlowIterationResult:
    """Container for per-iteration analysis results.

    Args:
        failure_id: Stable identifier for the failure scenario (e.g., "baseline" or a hash).
        failure_state: Optional excluded components for the iteration.
        flows: List of flow entries for this iteration.
        summary: Aggregated summary across ``flows``.
        data: Optional per-iteration extras.
    """

    failure_id: str = ""
    failure_state: Optional[Dict[str, List[str]]] = None
    flows: List[FlowEntry] = field(default_factory=list)
    summary: FlowSummary = field(
        default_factory=lambda: FlowSummary(
            total_demand=0.0,
            total_placed=0.0,
            overall_ratio=1.0,
            dropped_flows=0,
            num_flows=0,
        )
    )
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate iteration container and contained flows.

        Raises:
            ValueError: If summary/flow counts mismatch or failure_state invalid.
        """
        # Validate failure_state structure if present
        if self.failure_state is not None:
            if not isinstance(self.failure_state, dict):
                logger.error(
                    "failure_state must be a dict with excluded_nodes/links lists"
                )
                raise ValueError("failure_state must be a dict")
            for key in ("excluded_nodes", "excluded_links"):
                seq = self.failure_state.get(key)
                if not isinstance(seq, list) or not all(
                    isinstance(x, str) for x in seq
                ):
                    logger.error("failure_state.%s must be a list[str]", key)
                    raise ValueError("failure_state lists must be list[str]")

        # Validate contained flow entries
        for entry in self.flows:
            if not isinstance(entry, FlowEntry):
                logger.error("flows must contain FlowEntry instances: %r", type(entry))
                raise TypeError("flows must contain FlowEntry instances")

        # Summary consistency with flow count
        if self.summary.num_flows != len(self.flows):
            logger.error(
                "FlowIterationResult summary.num_flows (%d) != len(flows) (%d)",
                self.summary.num_flows,
                len(self.flows),
            )
            raise ValueError("summary.num_flows must match len(flows)")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return {
            "failure_id": self.failure_id,
            "failure_state": self.failure_state
            if self.failure_state is not None
            else None,
            "flows": [f.to_dict() for f in self.flows],
            "summary": self.summary.to_dict(),
            "data": _ensure_json_safe(self.data),
        }


def _ensure_json_safe(obj: Any, depth: int = 4) -> Any:
    """Return an equivalent object composed of JSON primitives (or raise).

    This defends against silently serializing non-JSON-safe structures.
    """
    if depth < 0:
        return obj
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            logger.error("Non-finite float in JSON payload: %r", obj)
            raise ValueError("Non-finite float in JSON payload")
        return obj
    if isinstance(obj, list):
        return [_ensure_json_safe(x, depth - 1) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _ensure_json_safe(v, depth - 1) for k, v in obj.items()}
    logger.error("Non-JSON-safe type in payload: %r", type(obj))
    raise TypeError("Non-JSON-safe type in payload")
