import math

import geopy.distance
import pytest

from ngraph.network import Network


def calculate_latency_km(km_distance):
    """Calculate latency in nanoseconds for a given distance in km."""
    speed_of_light_km_per_ns = 0.2  # Speed of light in fiber in km/ns
    return math.ceil(km_distance / speed_of_light_km_per_ns)


# Coordinates of the airports (latitude, longitude)
airport_coords = {
    "JFK": (40.641766, -73.780968),
    "LAX": (33.941589, -118.40853),
    "ORD": (41.974163, -87.907321),
    "IAH": (29.99022, -95.336783),
    "PHX": (33.437269, -112.007788),
    "PHL": (39.874395, -75.242423),
    "SAT": (29.424122, -98.493629),
    "SAN": (32.733801, -117.193304),
    "DFW": (32.899809, -97.040335),
    "SJC": (37.363947, -121.928938),
    "AUS": (30.197475, -97.666305),
    "JAX": (30.332184, -81.655651),
    "CMH": (39.961176, -82.998794),
    "IND": (39.768403, -86.158068),
    "CLT": (35.227087, -80.843127),
    "SFO": (37.774929, -122.419416),
    "SEA": (47.606209, -122.332071),
    "DEN": (39.739236, -104.990251),
    "DCA": (38.907192, -77.036871),
}

connections = [
    ("JFK", "PHL", 100),
    ("JFK", "DCA", 100),
    ("LAX", "SFO", 100),
    ("LAX", "SAN", 100),
    ("ORD", "IND", 100),
    ("ORD", "CMH", 100),
    ("IAH", "DFW", 100),
    ("IAH", "AUS", 100),
    ("PHX", "LAX", 100),
    ("SAT", "AUS", 100),
    ("DFW", "AUS", 100),
    ("SJC", "SFO", 100),
    ("SJC", "LAX", 100),
    ("CLT", "DCA", 100),
    ("SEA", "SFO", 100),
    ("DEN", "PHX", 100),
    ("DEN", "SEA", 100),
    ("SFO", "DEN", 200),
    ("DEN", "ORD", 300),
    ("PHX", "DFW", 300),
    ("CMH", "JFK", 100),
    ("IND", "CLT", 100),
    ("IAH", "JAX", 100),
    ("SAT", "AUS", 100),
    ("SAT", "IAH", 100),
    ("JAX", "CLT", 100),
    ("SAN", "PHX", 100),
    ("DFW", "IND", 100),
]


connections_with_capacity_and_metric = []
for src, dst, cap in connections:
    src_coord = airport_coords[src]
    dst_coord = airport_coords[dst]
    distance_km = geopy.distance.distance(src_coord, dst_coord).km
    latency_ns = calculate_latency_km(distance_km)
    connections_with_capacity_and_metric.append((src, dst, cap, latency_ns))


@pytest.fixture
def network1():
    network = Network()
    for plane_id in ["Plane1", "Plane2"]:
        network.add_plane(plane_id)

    for src, dst, cap, metric in connections_with_capacity_and_metric:
        network.add_node(src)
        network.add_node(dst)
        network.add_link(src, dst, capacity=cap, metric=metric)
    return network
