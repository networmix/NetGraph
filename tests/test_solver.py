from typing import List
import pytest

from ngraph.lib.demand import Demand, DemandStatus
from ngraph.lib.flow_policy import FlowPolicy, FlowPolicyConfig
from ngraph.lib.flow import FlowIndex
from ngraph.net import Net, Link, Node
from ngraph.solver import (
    ConstraintType,
    Constraint,
    Failure,
    SolverParams,
    Solver,
    Problem,
)

from .sample_data.sample_problem import *


def test_solver_1(problem_1):
    solver = Solver()
    problem = solver.solve(problem_1)

    assert problem.net.graph.get_edges() == {
        0: (
            "bb.lon1",
            "bb.ams1",
            0,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [0, 1],
                "flow": 0,
                "flows": {},
                "link_id": 0,
                "metric": 175,
                "node_a": "bb.lon1",
                "node_z": "bb.ams1",
            },
        ),
        1: (
            "bb.ams1",
            "bb.lon1",
            1,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [0, 1],
                "flow": 0,
                "flows": {},
                "link_id": 0,
                "metric": 175,
                "node_a": "bb.lon1",
                "node_z": "bb.ams1",
            },
        ),
        2: (
            "bb.lon2",
            "bb.ams2",
            2,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [2, 3],
                "flow": 0,
                "flows": {},
                "link_id": 1,
                "metric": 175,
                "node_a": "bb.lon2",
                "node_z": "bb.ams2",
            },
        ),
        3: (
            "bb.ams2",
            "bb.lon2",
            3,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [2, 3],
                "flow": 0,
                "flows": {},
                "link_id": 1,
                "metric": 175,
                "node_a": "bb.lon2",
                "node_z": "bb.ams2",
            },
        ),
        4: (
            "bb.lon1",
            "bb.lon2",
            4,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [4, 5],
                "flow": 0,
                "flows": {},
                "link_id": 2,
                "metric": 10,
                "node_a": "bb.lon1",
                "node_z": "bb.lon2",
            },
        ),
        5: (
            "bb.lon2",
            "bb.lon1",
            5,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [4, 5],
                "flow": 0,
                "flows": {},
                "link_id": 2,
                "metric": 10,
                "node_a": "bb.lon1",
                "node_z": "bb.lon2",
            },
        ),
        6: (
            "bb.ams1",
            "bb.ams2",
            6,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [6, 7],
                "flow": 0,
                "flows": {},
                "link_id": 3,
                "metric": 10,
                "node_a": "bb.ams1",
                "node_z": "bb.ams2",
            },
        ),
        7: (
            "bb.ams2",
            "bb.ams1",
            7,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [6, 7],
                "flow": 0,
                "flows": {},
                "link_id": 3,
                "metric": 10,
                "node_a": "bb.ams1",
                "node_z": "bb.ams2",
            },
        ),
        8: (
            "bb.lon1",
            "bb.fra1",
            8,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [8, 9],
                "flow": 106.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 4,
                "metric": 310,
                "node_a": "bb.lon1",
                "node_z": "bb.fra1",
            },
        ),
        9: (
            "bb.fra1",
            "bb.lon1",
            9,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [8, 9],
                "flow": 106.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=8
                    ): 6.25,
                },
                "link_id": 4,
                "metric": 310,
                "node_a": "bb.lon1",
                "node_z": "bb.fra1",
            },
        ),
        10: (
            "bb.lon2",
            "bb.fra2",
            10,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [10, 11],
                "flow": 93.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=12
                    ): 6.25,
                },
                "link_id": 5,
                "metric": 310,
                "node_a": "bb.lon2",
                "node_z": "bb.fra2",
            },
        ),
        11: (
            "bb.fra2",
            "bb.lon2",
            11,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [10, 11],
                "flow": 93.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 5,
                "metric": 310,
                "node_a": "bb.lon2",
                "node_z": "bb.fra2",
            },
        ),
        12: (
            "bb.fra1",
            "bb.fra2",
            12,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [12, 13],
                "flow": 0,
                "flows": {},
                "link_id": 6,
                "metric": 10,
                "node_a": "bb.fra1",
                "node_z": "bb.fra2",
            },
        ),
        13: (
            "bb.fra2",
            "bb.fra1",
            13,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [12, 13],
                "flow": 0,
                "flows": {},
                "link_id": 6,
                "metric": 10,
                "node_a": "bb.fra1",
                "node_z": "bb.fra2",
            },
        ),
        14: (
            "bb.lon1",
            "bb.par1",
            14,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [14, 15],
                "flow": 100.0,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=11
                    ): 6.25,
                },
                "link_id": 7,
                "metric": 170,
                "node_a": "bb.lon1",
                "node_z": "bb.par1",
            },
        ),
        15: (
            "bb.par1",
            "bb.lon1",
            15,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [14, 15],
                "flow": 106.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 7,
                "metric": 170,
                "node_a": "bb.lon1",
                "node_z": "bb.par1",
            },
        ),
        16: (
            "bb.lon2",
            "bb.par2",
            16,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [16, 17],
                "flow": 100.0,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 8,
                "metric": 170,
                "node_a": "bb.lon2",
                "node_z": "bb.par2",
            },
        ),
        17: (
            "bb.par2",
            "bb.lon2",
            17,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [16, 17],
                "flow": 93.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=7
                    ): 6.25,
                },
                "link_id": 8,
                "metric": 170,
                "node_a": "bb.lon2",
                "node_z": "bb.par2",
            },
        ),
        18: (
            "bb.par1",
            "bb.par2",
            18,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [18, 19],
                "flow": 0,
                "flows": {},
                "link_id": 9,
                "metric": 10,
                "node_a": "bb.par1",
                "node_z": "bb.par2",
            },
        ),
        19: (
            "bb.par2",
            "bb.par1",
            19,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [18, 19],
                "flow": 0,
                "flows": {},
                "link_id": 9,
                "metric": 10,
                "node_a": "bb.par1",
                "node_z": "bb.par2",
            },
        ),
        20: (
            "dc1.lon",
            "bb.lon1",
            20,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [20, 21],
                "flow": 206.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=11
                    ): 6.25,
                },
                "link_id": 10,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon1",
            },
        ),
        21: (
            "bb.lon1",
            "dc1.lon",
            21,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [20, 21],
                "flow": 212.5,
                "flows": {
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 10,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon1",
            },
        ),
        22: (
            "dc1.lon",
            "bb.lon2",
            22,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [22, 23],
                "flow": 193.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 11,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon2",
            },
        ),
        23: (
            "bb.lon2",
            "dc1.lon",
            23,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [22, 23],
                "flow": 187.5,
                "flows": {
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=7
                    ): 6.25,
                },
                "link_id": 11,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon2",
            },
        ),
        24: (
            "dc1.fra",
            "bb.fra1",
            24,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [24, 25],
                "flow": 106.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=8
                    ): 6.25,
                },
                "link_id": 12,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra1",
            },
        ),
        25: (
            "bb.fra1",
            "dc1.fra",
            25,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [24, 25],
                "flow": 106.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 12,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra1",
            },
        ),
        26: (
            "dc1.fra",
            "bb.fra2",
            26,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [26, 27],
                "flow": 93.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.fra", dst_node="dc1.lon", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 13,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra2",
            },
        ),
        27: (
            "bb.fra2",
            "dc1.fra",
            27,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [26, 27],
                "flow": 93.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.fra", flow_class=2, flow_id=12
                    ): 6.25,
                },
                "link_id": 13,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra2",
            },
        ),
        28: (
            "dc1.par",
            "bb.par1",
            28,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [28, 29],
                "flow": 106.25,
                "flows": {
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 14,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par1",
            },
        ),
        29: (
            "bb.par1",
            "dc1.par",
            29,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [28, 29],
                "flow": 100.0,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=11
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=15
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=10
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=11
                    ): 6.25,
                },
                "link_id": 14,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par1",
            },
        ),
        30: (
            "dc1.par",
            "bb.par2",
            30,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [30, 31],
                "flow": 93.75,
                "flows": {
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.par", dst_node="dc1.lon", flow_class=2, flow_id=7
                    ): 6.25,
                },
                "link_id": 15,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par2",
            },
        ),
        31: (
            "bb.par2",
            "dc1.par",
            31,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [30, 31],
                "flow": 100.0,
                "flows": {
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=0
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=5
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=6
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=7
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=8
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=1, flow_id=9
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=1
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=2
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=3
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=4
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=12
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=13
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=14
                    ): 6.25,
                    FlowIndex(
                        src_node="dc1.lon", dst_node="dc1.par", flow_class=2, flow_id=15
                    ): 6.25,
                },
                "link_id": 15,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par2",
            },
        ),
        32: (
            "pop1.lon",
            "bb.lon1",
            32,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [32, 33],
                "flow": 0,
                "flows": {},
                "link_id": 16,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon1",
            },
        ),
        33: (
            "bb.lon1",
            "pop1.lon",
            33,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [32, 33],
                "flow": 0,
                "flows": {},
                "link_id": 16,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon1",
            },
        ),
        34: (
            "pop1.lon",
            "bb.lon2",
            34,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [34, 35],
                "flow": 0,
                "flows": {},
                "link_id": 17,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon2",
            },
        ),
        35: (
            "bb.lon2",
            "pop1.lon",
            35,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [34, 35],
                "flow": 0,
                "flows": {},
                "link_id": 17,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon2",
            },
        ),
        36: (
            "pop1.ams",
            "bb.ams1",
            36,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [36, 37],
                "flow": 0,
                "flows": {},
                "link_id": 18,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams1",
            },
        ),
        37: (
            "bb.ams1",
            "pop1.ams",
            37,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [36, 37],
                "flow": 0,
                "flows": {},
                "link_id": 18,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams1",
            },
        ),
        38: (
            "pop1.ams",
            "bb.ams2",
            38,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [38, 39],
                "flow": 0,
                "flows": {},
                "link_id": 19,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams2",
            },
        ),
        39: (
            "bb.ams2",
            "pop1.ams",
            39,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [38, 39],
                "flow": 0,
                "flows": {},
                "link_id": 19,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams2",
            },
        ),
    }
    assert problem.demand_status == DemandStatus.PLACED
