from math import ceil

from ngraph import geo_helpers


def test_distance_1():
    lat1 = 37.3382
    lon1 = -121.8863

    lat2 = 40.7128
    lon2 = -74.0060

    assert ceil(geo_helpers.distance(lat1, lon1, lat2, lon2)) == 4102


def test_airport_iata_coords_1():
    lat1 = 37.362598
    lon1 = -121.929001

    assert (lat1, lon1) == geo_helpers.airport_iata_coords("sjc")
