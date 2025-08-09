"""Builders for traffic matrices.

Construct `TrafficMatrixSet` from raw dictionaries (e.g. parsed YAML).
This logic was previously embedded in `Scenario.from_yaml`.
"""

from __future__ import annotations

from typing import Dict, List

from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.yaml_utils import normalize_yaml_dict_keys


def build_traffic_matrix_set(raw: Dict[str, List[dict]]) -> TrafficMatrixSet:
    """Build a `TrafficMatrixSet` from a mapping of name -> list of dicts.

    Args:
        raw: Mapping where each key is a matrix name and each value is a list of
            dictionaries with `TrafficDemand` constructor fields.

    Returns:
        Initialized `TrafficMatrixSet` with constructed `TrafficDemand` objects.

    Raises:
        ValueError: If ``raw`` is not a mapping of name -> list[dict].
    """
    if not isinstance(raw, dict):
        raise ValueError(
            "'traffic_matrix_set' must be a mapping of name -> list[TrafficDemand]"
        )

    normalized_raw = normalize_yaml_dict_keys(raw)
    tms = TrafficMatrixSet()
    for name, td_list in normalized_raw.items():
        if not isinstance(td_list, list):
            raise ValueError(
                f"Matrix '{name}' must map to a list of TrafficDemand dicts"
            )
        tms.add(name, [TrafficDemand(**d) for d in td_list])

    return tms
