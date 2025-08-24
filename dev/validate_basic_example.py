"""Validate docs/examples/basic.md code and expected outputs.

Runs the example scenario, checks flow values and cost distribution, and
verifies sensitivity helpers return sensible structures. Exits non-zero on
assertion failure.
"""

from __future__ import annotations

from ngraph.algorithms.base import FlowPlacement
from ngraph.algorithms.max_flow import run_sensitivity, saturated_edges
from ngraph.scenario import Scenario


def main() -> None:
    scenario_yaml = """
seed: 1234

network:
  name: "fundamentals_example"

  nodes:
    A: {}
    B: {}
    C: {}
    D: {}

  links:
    - source: A
      target: B
      link_params:
        capacity: 1
        cost: 1
    - source: A
      target: B
      link_params:
        capacity: 2
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 1
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 2
        cost: 1
    - source: A
      target: D
      link_params:
        capacity: 3
        cost: 2
    - source: D
      target: C
      link_params:
        capacity: 3
        cost: 2
"""

    scenario = Scenario.from_yaml(scenario_yaml)
    network = scenario.network

    # 1) True maximum flow (all paths)
    max_flow_all = network.max_flow(source_path="A", sink_path="C")
    assert isinstance(max_flow_all, dict)
    assert len(max_flow_all) == 1
    value_all = float(next(iter(max_flow_all.values())))
    print("Maximum flow (all paths):", max_flow_all)
    assert value_all == 6.0

    # 2) Shortest paths only
    max_flow_shortest = network.max_flow(
        source_path="A", sink_path="C", shortest_path=True
    )
    assert isinstance(max_flow_shortest, dict)
    value_shortest = float(next(iter(max_flow_shortest.values())))
    print("Flow on shortest paths:", max_flow_shortest)
    assert value_shortest == 3.0

    # 3) Equal-balanced on shortest paths
    max_flow_balanced = network.max_flow(
        source_path="A",
        sink_path="C",
        shortest_path=True,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
    )
    assert isinstance(max_flow_balanced, dict)
    value_balanced = float(next(iter(max_flow_balanced.values())))
    print("Equal-balanced flow:", max_flow_balanced)
    # Equal-split over two parallel edges limited by the smallest edge (1+1)
    assert value_balanced == 2.0
    assert value_balanced <= value_shortest

    # 4) Cost distribution under combine mode
    with_summary = network.max_flow_with_summary(
        source_path="A", sink_path="C", mode="combine"
    )
    ((_, _), (flow_value, summary)) = next(iter(with_summary.items()))
    assert abs(flow_value - value_all) < 1e-9
    cd = {float(k): float(v) for k, v in summary.cost_distribution.items()}
    print("Cost distribution:", cd)
    # Expect 3.0 at cost 2 (A-B-C), and 3.0 at cost 4 (A-D-C)
    assert cd == {2.0: 3.0, 4.0: 3.0}

    # 5) Sensitivity helpers
    graph = network.to_strict_multidigraph()
    bottlenecks = saturated_edges(graph, "A", "C")
    assert isinstance(bottlenecks, list)
    assert len(bottlenecks) > 0

    s_inc = run_sensitivity(graph, "A", "C", change_amount=1.0)
    s_dec = run_sensitivity(graph, "A", "C", change_amount=-1.0)
    assert isinstance(s_inc, dict) and isinstance(s_dec, dict)
    assert s_inc and s_dec
    # Increasing capacity should not reduce flow; decreasing should not increase
    assert all(v >= 0 for v in s_inc.values())
    assert all(v <= 0 for v in s_dec.values())


if __name__ == "__main__":
    main()
