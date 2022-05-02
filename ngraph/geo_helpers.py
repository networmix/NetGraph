from math import radians, cos, sin, asin, sqrt
from typing import Tuple
from ngraph.resource_helpers import load_resource, json_to_dict
from ngraph import resources


def distance(
    lat1: float, lon1: float, lat2: float, lon2: float, round_ndigits: int = 2
) -> float:
    """
    Calculates distance between two points on a sphere given their longitudes and latitudes.
    https://en.wikipedia.org/wiki/Haversine_formula
    """
    EARTH_RADIUS = 6371  # https://en.wikipedia.org/wiki/Earth_radius

    lat1 = radians(lat1)
    lat2 = radians(lat2)
    lon1 = radians(lon1)
    lon2 = radians(lon2)

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return round(2 * EARTH_RADIUS * asin(sqrt(h)), round_ndigits)


def airport_iata_coords(iata_code: str) -> Tuple[float]:
    air_iata_dict = json_to_dict(load_resource("airports_iata.json", resources))
    if iata_code in air_iata_dict:
        return tuple(
            map(float, reversed(air_iata_dict[iata_code]["coordinates"].split(",")))
        )

    return 0, 0
