"""Tests for flow policy preset configurations."""

import pytest

try:
    import netgraph_core
except ImportError:
    pytest.skip("netgraph_core not available", allow_module_level=True)

from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy


@pytest.fixture
def simple_graph():
    """Create a simple test graph."""
    import numpy as np

    backend = netgraph_core.Backend.cpu()
    algs = netgraph_core.Algorithms(backend)

    # Build a simple graph with 3 nodes and 2 edges using from_arrays
    num_nodes = 3
    src = np.array([0, 1], dtype=np.int32)
    dst = np.array([1, 2], dtype=np.int32)
    capacity = np.array([10.0, 10.0], dtype=np.float64)
    cost = np.array([1, 1], dtype=np.int64)
    ext_edge_ids = np.array([1, 2], dtype=np.int64)

    multidigraph = netgraph_core.StrictMultiDiGraph.from_arrays(
        num_nodes=num_nodes,
        src=src,
        dst=dst,
        capacity=capacity,
        cost=cost,
        ext_edge_ids=ext_edge_ids,
    )

    graph_handle = algs.build_graph(multidigraph)

    return algs, graph_handle, multidigraph


def test_flow_policy_preset_enum_values():
    """Test that FlowPolicyPreset enum has expected values."""
    assert FlowPolicyPreset.SHORTEST_PATHS_ECMP == 1
    assert FlowPolicyPreset.SHORTEST_PATHS_WCMP == 2
    assert FlowPolicyPreset.TE_WCMP_UNLIM == 3
    assert FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP == 4
    assert FlowPolicyPreset.TE_ECMP_16_LSP == 5


def test_create_flow_policy_shortest_paths_ecmp(simple_graph):
    """Test creating SHORTEST_PATHS_ECMP policy."""
    algs, graph_handle, _ = simple_graph

    policy = create_flow_policy(
        algs, graph_handle, FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )

    assert policy is not None
    assert isinstance(policy, netgraph_core.FlowPolicy)


def test_create_flow_policy_shortest_paths_wcmp(simple_graph):
    """Test creating SHORTEST_PATHS_WCMP policy."""
    algs, graph_handle, _ = simple_graph

    policy = create_flow_policy(
        algs, graph_handle, FlowPolicyPreset.SHORTEST_PATHS_WCMP
    )

    assert policy is not None
    assert isinstance(policy, netgraph_core.FlowPolicy)


def test_create_flow_policy_te_wcmp_unlim(simple_graph):
    """Test creating TE_WCMP_UNLIM policy."""
    algs, graph_handle, _ = simple_graph

    policy = create_flow_policy(algs, graph_handle, FlowPolicyPreset.TE_WCMP_UNLIM)

    assert policy is not None
    assert isinstance(policy, netgraph_core.FlowPolicy)


def test_create_flow_policy_te_ecmp_up_to_256_lsp(simple_graph):
    """Test creating TE_ECMP_UP_TO_256_LSP policy."""
    algs, graph_handle, _ = simple_graph

    policy = create_flow_policy(
        algs, graph_handle, FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP
    )

    assert policy is not None
    assert isinstance(policy, netgraph_core.FlowPolicy)


def test_create_flow_policy_te_ecmp_16_lsp(simple_graph):
    """Test creating TE_ECMP_16_LSP policy."""
    algs, graph_handle, _ = simple_graph

    policy = create_flow_policy(algs, graph_handle, FlowPolicyPreset.TE_ECMP_16_LSP)

    assert policy is not None
    assert isinstance(policy, netgraph_core.FlowPolicy)


def test_create_flow_policy_invalid_preset(simple_graph):
    """Test error handling for invalid preset."""
    algs, graph_handle, _ = simple_graph

    # Cast to int to bypass enum validation
    invalid_preset = 999

    with pytest.raises(ValueError, match="Unknown flow policy preset"):
        create_flow_policy(algs, graph_handle, invalid_preset)


def test_create_flow_policy_all_presets(simple_graph):
    """Test that all defined presets can be created."""
    algs, graph_handle, _ = simple_graph

    for preset in FlowPolicyPreset:
        policy = create_flow_policy(algs, graph_handle, preset)
        assert policy is not None
        assert isinstance(policy, netgraph_core.FlowPolicy)


def test_flow_policy_preset_is_int_enum():
    """Test that FlowPolicyPreset is an IntEnum."""
    from enum import IntEnum

    assert issubclass(FlowPolicyPreset, IntEnum)


def test_flow_policy_preset_can_be_used_as_int():
    """Test that FlowPolicyPreset values can be used as integers."""
    preset = FlowPolicyPreset.SHORTEST_PATHS_ECMP
    assert preset == 1
    assert int(preset) == 1
    assert preset + 1 == 2


def test_flow_policy_preset_from_value():
    """Test creating FlowPolicyPreset from integer value."""
    preset = FlowPolicyPreset(1)
    assert preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP

    preset = FlowPolicyPreset(2)
    assert preset == FlowPolicyPreset.SHORTEST_PATHS_WCMP


def test_flow_policy_preset_from_name():
    """Test creating FlowPolicyPreset from name."""
    preset = FlowPolicyPreset["SHORTEST_PATHS_ECMP"]
    assert preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP

    preset = FlowPolicyPreset["TE_ECMP_16_LSP"]
    assert preset == FlowPolicyPreset.TE_ECMP_16_LSP
