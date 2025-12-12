"""Tests for demand expansion and TrafficDemand round-trip serialization."""

import pytest

from ngraph.exec.demand.expand import expand_demands
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.network import Link, Network, Node


@pytest.fixture
def simple_network() -> Network:
    """Create a simple 4-node network for testing."""
    network = Network()
    for name in ["A", "B", "C", "D"]:
        network.add_node(Node(name))
    network.add_link(Link("A", "B", capacity=100.0, cost=1.0))
    network.add_link(Link("B", "C", capacity=100.0, cost=1.0))
    network.add_link(Link("C", "D", capacity=100.0, cost=1.0))
    return network


class TestTrafficDemandIdRoundTrip:
    """Test TrafficDemand ID preservation through serialization."""

    def test_explicit_id_preserved(self) -> None:
        """TrafficDemand with explicit ID preserves it."""
        td = TrafficDemand(
            id="my-stable-id",
            source_path="A",
            sink_path="B",
            demand=100.0,
        )
        assert td.id == "my-stable-id"

    def test_auto_generated_id_when_none(self) -> None:
        """TrafficDemand without explicit ID auto-generates one."""
        td = TrafficDemand(source_path="A", sink_path="B", demand=100.0)
        assert td.id is not None
        assert "|" in td.id  # Format: source|sink|uuid

    def test_id_round_trip_through_dict(self) -> None:
        """TrafficDemand ID survives dict serialization round-trip."""
        original = TrafficDemand(
            source_path="A",
            sink_path="B",
            demand=100.0,
            mode="combine",
            priority=1,
        )
        original_id = original.id

        # Serialize to dict (as done in workflow steps)
        config = {
            "id": original.id,
            "source_path": original.source_path,
            "sink_path": original.sink_path,
            "demand": original.demand,
            "mode": original.mode,
            "priority": original.priority,
        }

        # Reconstruct (as done in flow.py)
        reconstructed = TrafficDemand(
            id=config.get("id"),
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
            mode=config.get("mode", "pairwise"),
            priority=config.get("priority", 0),
        )

        assert reconstructed.id == original_id

    def test_id_mismatch_without_explicit_id(self) -> None:
        """Two TrafficDemands from same config get different IDs if id not passed."""
        config = {
            "source_path": "A",
            "sink_path": "B",
            "demand": 100.0,
        }

        td1 = TrafficDemand(
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
        )
        td2 = TrafficDemand(
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
        )

        # Without explicit ID, each gets a different auto-generated ID
        assert td1.id != td2.id


class TestExpandDemandsPairwise:
    """Test expand_demands with pairwise mode."""

    def test_pairwise_single_pair(self, simple_network: Network) -> None:
        """Pairwise mode with single source-sink creates one demand."""
        td = TrafficDemand(
            source_path="A", sink_path="D", demand=100.0, mode="pairwise"
        )
        expansion = expand_demands(simple_network, [td])

        assert len(expansion.demands) == 1
        assert len(expansion.augmentations) == 0  # No pseudo nodes for pairwise

        demand = expansion.demands[0]
        assert demand.src_name == "A"
        assert demand.dst_name == "D"
        assert demand.volume == 100.0

    def test_pairwise_multiple_sources(self, simple_network: Network) -> None:
        """Pairwise mode with regex creates demand per (src, dst) pair."""
        td = TrafficDemand(
            source_path="[AB]",  # A and B
            sink_path="[CD]",  # C and D
            demand=100.0,
            mode="pairwise",
        )
        expansion = expand_demands(simple_network, [td])

        # 2 sources x 2 sinks = 4 pairs
        assert len(expansion.demands) == 4
        assert len(expansion.augmentations) == 0

        # Volume distributed evenly
        for demand in expansion.demands:
            assert demand.volume == 25.0  # 100 / 4

    def test_pairwise_no_self_loops(self, simple_network: Network) -> None:
        """Pairwise mode excludes self-loops."""
        td = TrafficDemand(
            source_path="[AB]",
            sink_path="[AB]",  # Same as sources
            demand=100.0,
            mode="pairwise",
        )
        expansion = expand_demands(simple_network, [td])

        # A->B and B->A only (no A->A or B->B)
        assert len(expansion.demands) == 2
        for demand in expansion.demands:
            assert demand.src_name != demand.dst_name


class TestExpandDemandsCombine:
    """Test expand_demands with combine mode."""

    def test_combine_creates_pseudo_nodes(self, simple_network: Network) -> None:
        """Combine mode creates pseudo source and sink nodes."""
        td = TrafficDemand(
            source_path="[AB]",
            sink_path="[CD]",
            demand=100.0,
            mode="combine",
        )
        expansion = expand_demands(simple_network, [td])

        # One aggregated demand
        assert len(expansion.demands) == 1

        # Augmentations: pseudo_src->A, pseudo_src->B, C->pseudo_snk, D->pseudo_snk
        assert len(expansion.augmentations) == 4

        demand = expansion.demands[0]
        assert demand.src_name.startswith("_src_")
        assert demand.dst_name.startswith("_snk_")
        assert demand.volume == 100.0

    def test_combine_pseudo_node_names_use_id(self, simple_network: Network) -> None:
        """Combine mode pseudo node names include TrafficDemand.id."""
        td = TrafficDemand(
            id="stable-id-123",
            source_path="A",
            sink_path="D",
            demand=100.0,
            mode="combine",
        )
        expansion = expand_demands(simple_network, [td])

        demand = expansion.demands[0]
        assert demand.src_name == "_src_stable-id-123"
        assert demand.dst_name == "_snk_stable-id-123"

    def test_combine_augmentations_structure(self, simple_network: Network) -> None:
        """Combine mode augmentations connect pseudo nodes to real nodes."""
        td = TrafficDemand(
            id="test-id",
            source_path="[AB]",
            sink_path="[CD]",
            demand=100.0,
            mode="combine",
        )
        expansion = expand_demands(simple_network, [td])

        # Check augmentation edges
        aug_edges = [(a.source, a.target) for a in expansion.augmentations]

        # Pseudo source -> real sources
        assert ("_src_test-id", "A") in aug_edges
        assert ("_src_test-id", "B") in aug_edges

        # Real sinks -> pseudo sink
        assert ("C", "_snk_test-id") in aug_edges
        assert ("D", "_snk_test-id") in aug_edges


class TestExpandDemandsIdConsistency:
    """Test that expansion uses consistent IDs for pseudo node naming."""

    def test_same_id_produces_same_pseudo_nodes(self, simple_network: Network) -> None:
        """Same TrafficDemand ID produces identical pseudo node names."""
        td1 = TrafficDemand(
            id="shared-id",
            source_path="A",
            sink_path="D",
            demand=100.0,
            mode="combine",
        )
        td2 = TrafficDemand(
            id="shared-id",
            source_path="A",
            sink_path="D",
            demand=200.0,  # Different demand
            mode="combine",
        )

        exp1 = expand_demands(simple_network, [td1])
        exp2 = expand_demands(simple_network, [td2])

        # Same pseudo node names
        assert exp1.demands[0].src_name == exp2.demands[0].src_name
        assert exp1.demands[0].dst_name == exp2.demands[0].dst_name

    def test_different_ids_produce_different_pseudo_nodes(
        self, simple_network: Network
    ) -> None:
        """Different TrafficDemand IDs produce different pseudo node names."""
        td1 = TrafficDemand(
            id="id-alpha",
            source_path="A",
            sink_path="D",
            demand=100.0,
            mode="combine",
        )
        td2 = TrafficDemand(
            id="id-beta",
            source_path="A",
            sink_path="D",
            demand=100.0,
            mode="combine",
        )

        exp1 = expand_demands(simple_network, [td1])
        exp2 = expand_demands(simple_network, [td2])

        # Different pseudo node names
        assert exp1.demands[0].src_name != exp2.demands[0].src_name
        assert exp1.demands[0].dst_name != exp2.demands[0].dst_name


class TestExpandDemandsEdgeCases:
    """Test edge cases for expand_demands."""

    def test_empty_demands_raises(self, simple_network: Network) -> None:
        """Empty demands list raises ValueError."""
        with pytest.raises(ValueError, match="No demands could be expanded"):
            expand_demands(simple_network, [])

    def test_no_matching_nodes_raises(self, simple_network: Network) -> None:
        """Demand with no matching nodes raises ValueError."""
        td = TrafficDemand(
            source_path="nonexistent",
            sink_path="also_nonexistent",
            demand=100.0,
        )
        with pytest.raises(ValueError, match="No demands could be expanded"):
            expand_demands(simple_network, [td])

    def test_multiple_demands_mixed_modes(self, simple_network: Network) -> None:
        """Multiple demands with different modes expand correctly."""
        td_pairwise = TrafficDemand(
            source_path="A",
            sink_path="B",
            demand=50.0,
            mode="pairwise",
        )
        td_combine = TrafficDemand(
            source_path="[CD]",
            sink_path="[AB]",
            demand=100.0,
            mode="combine",
        )

        expansion = expand_demands(simple_network, [td_pairwise, td_combine])

        # 1 pairwise + 1 combined = 2 demands
        assert len(expansion.demands) == 2

        # Only combine mode creates augmentations
        assert len(expansion.augmentations) == 4  # 2 sources + 2 sinks
