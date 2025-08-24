"""Validate docs/examples/clos-fabric.md code and key outputs.

Asserts the ECMP combine shortest-path example returns a positive flow
and checks ECMP vs WCMP relationship for the constructed topology.
"""

from __future__ import annotations

from ngraph.algorithms.base import FlowPlacement
from ngraph.scenario import Scenario


def main() -> None:
    scenario_yaml = """
blueprints:
  brick_2tier:
    groups:
      t1:
        node_count: 8
        name_template: t1-{node_num}
      t2:
        node_count: 8
        name_template: t2-{node_num}

    adjacency:
      - source: /t1
        target: /t2
        pattern: mesh
        link_params:
          capacity: 2
          cost: 1

  3tier_clos:
    groups:
      b1:
        use_blueprint: brick_2tier
      b2:
        use_blueprint: brick_2tier
      spine:
        node_count: 64
        name_template: t3-{node_num}

    adjacency:
      - source: b1/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1
      - source: b2/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1

network:
  name: "3tier_clos_network"
  version: 1.0

  groups:
    my_clos1:
      use_blueprint: 3tier_clos

    my_clos2:
      use_blueprint: 3tier_clos

  adjacency:
    - source: my_clos1/spine
      target: my_clos2/spine
      pattern: one_to_one
      link_count: 4
      link_params:
        capacity: 1
        cost: 1
"""

    scenario = Scenario.from_yaml(scenario_yaml)
    network = scenario.network

    # ECMP on shortest paths, combine mode
    max_flow_ecmp = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        shortest_path=True,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
    )
    assert isinstance(max_flow_ecmp, dict)
    assert len(max_flow_ecmp) == 1
    flow_ecmp = float(next(iter(max_flow_ecmp.values())))
    print("ECMP combine shortest flow:", max_flow_ecmp)
    assert flow_ecmp > 0

    # Compare ECMP vs WCMP (both on shortest paths, combine)
    max_flow_wcmp = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        shortest_path=True,
        flow_placement=FlowPlacement.PROPORTIONAL,
    )
    flow_wcmp = float(next(iter(max_flow_wcmp.values())))
    print("WCMP combine shortest flow:", max_flow_wcmp)

    # In general WCMP >= ECMP in capacity usage under equal-cost parallelism
    assert flow_wcmp >= flow_ecmp


if __name__ == "__main__":
    main()
