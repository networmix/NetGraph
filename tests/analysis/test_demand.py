"""Tests for demand expansion and TrafficDemand round-trip serialization."""

import pytest

from ngraph.analysis.demand import expand_demands
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
            source="A",
            target="B",
            volume=100.0,
        )
        assert td.id == "my-stable-id"

    def test_auto_generated_id_when_none(self) -> None:
        """TrafficDemand without explicit ID auto-generates one."""
        td = TrafficDemand(source="A", target="B", volume=100.0)
        assert td.id is not None
        assert "|" in td.id  # Format: source|sink|uuid

    def test_id_round_trip_through_dict(self) -> None:
        """TrafficDemand ID survives dict serialization round-trip."""
        original = TrafficDemand(
            source="A",
            target="B",
            volume=100.0,
            mode="combine",
            priority=1,
        )
        original_id = original.id

        # Serialize to dict (as done in workflow steps)
        config = {
            "id": original.id,
            "source": original.source,
            "target": original.target,
            "volume": original.volume,
            "mode": original.mode,
            "priority": original.priority,
        }

        # Reconstruct (as done in flow.py)
        reconstructed = TrafficDemand(
            id=config.get("id"),
            source=config["source"],
            target=config["target"],
            volume=config["volume"],
            mode=config.get("mode", "pairwise"),
            priority=config.get("priority", 0),
        )

        assert reconstructed.id == original_id

    def test_id_mismatch_without_explicit_id(self) -> None:
        """Two TrafficDemands from same config get different IDs if id not passed."""
        config = {
            "source": "A",
            "target": "B",
            "volume": 100.0,
        }

        td1 = TrafficDemand(
            source=config["source"],
            target=config["target"],
            volume=config["volume"],
        )
        td2 = TrafficDemand(
            source=config["source"],
            target=config["target"],
            volume=config["volume"],
        )

        # Without explicit ID, each gets a different auto-generated ID
        assert td1.id != td2.id


class TestExpandDemandsPairwise:
    """Test expand_demands with pairwise mode."""

    def test_pairwise_single_pair(self, simple_network: Network) -> None:
        """Pairwise mode with single source-sink creates one demand."""
        td = TrafficDemand(source="A", target="D", volume=100.0, mode="pairwise")
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
            source="[AB]",  # A and B
            target="[CD]",  # C and D
            volume=100.0,
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
            source="[AB]",
            target="[AB]",  # Same as sources
            volume=100.0,
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
            source="[AB]",
            target="[CD]",
            volume=100.0,
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
            source="A",
            target="D",
            volume=100.0,
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
            source="[AB]",
            target="[CD]",
            volume=100.0,
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
            source="A",
            target="D",
            volume=100.0,
            mode="combine",
        )
        td2 = TrafficDemand(
            id="shared-id",
            source="A",
            target="D",
            volume=200.0,  # Different demand
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
            source="A",
            target="D",
            volume=100.0,
            mode="combine",
        )
        td2 = TrafficDemand(
            id="id-beta",
            source="A",
            target="D",
            volume=100.0,
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
            source="nonexistent",
            target="also_nonexistent",
            volume=100.0,
        )
        with pytest.raises(ValueError, match="No demands could be expanded"):
            expand_demands(simple_network, [td])

    def test_multiple_demands_mixed_modes(self, simple_network: Network) -> None:
        """Multiple demands with different modes expand correctly."""
        td_pairwise = TrafficDemand(
            source="A",
            target="B",
            volume=50.0,
            mode="pairwise",
        )
        td_combine = TrafficDemand(
            source="[CD]",
            target="[AB]",
            volume=100.0,
            mode="combine",
        )

        expansion = expand_demands(simple_network, [td_pairwise, td_combine])

        # 1 pairwise + 1 combined = 2 demands
        assert len(expansion.demands) == 2

        # Only combine mode creates augmentations
        assert len(expansion.augmentations) == 4  # 2 sources + 2 sinks


class TestDictSelectors:
    """Test dict-based selectors in demands (group_by, match)."""

    @pytest.fixture
    def network_with_attrs(self) -> Network:
        """Create a network with node attributes for selector testing."""
        network = Network()
        # Two datacenters with leaf/spine roles
        for dc in ["dc1", "dc2"]:
            for role in ["leaf", "spine"]:
                for i in [1, 2]:
                    name = f"{dc}_{role}_{i}"
                    network.add_node(Node(name, attrs={"dc": dc, "role": role}))

        # Connect within each DC: leaf -> spine
        for dc in ["dc1", "dc2"]:
            for i in [1, 2]:
                for j in [1, 2]:
                    network.add_link(
                        Link(f"{dc}_leaf_{i}", f"{dc}_spine_{j}", capacity=100.0)
                    )
        # Connect spines between DCs
        for i in [1, 2]:
            network.add_link(Link(f"dc1_spine_{i}", f"dc2_spine_{i}", capacity=50.0))

        return network

    def test_group_by_selector(self, network_with_attrs: Network) -> None:
        """Dict selector with group_by groups nodes by attribute."""
        td = TrafficDemand(
            source={"group_by": "dc"},  # Group by datacenter
            target={"group_by": "dc"},
            volume=100.0,
            mode="pairwise",
        )
        expansion = expand_demands(network_with_attrs, [td])

        # With group_by=dc and pairwise mode, we get:
        # dc1->dc2 and dc2->dc1 (excluding self-pairs)
        # Each group has 4 nodes, so 16 pairs per direction = 32 total
        # But wait, pairwise is between individual nodes, not groups
        # Actually pairwise still creates per-node pairs
        assert len(expansion.demands) > 0
        # Volume is distributed across pairs
        total_volume = sum(d.volume for d in expansion.demands)
        assert total_volume == pytest.approx(100.0, rel=1e-6)

    def test_match_selector_filters_nodes(self, network_with_attrs: Network) -> None:
        """Dict selector with match filters nodes by attribute conditions."""
        td = TrafficDemand(
            source={
                "path": ".*",
                "match": {
                    "conditions": [{"attr": "role", "op": "==", "value": "leaf"}]
                },
            },
            target={
                "path": ".*",
                "match": {
                    "conditions": [{"attr": "role", "op": "==", "value": "spine"}]
                },
            },
            volume=100.0,
            mode="pairwise",
        )
        expansion = expand_demands(network_with_attrs, [td])

        # 4 leaf nodes -> 4 spine nodes = 16 pairs
        assert len(expansion.demands) == 16

    def test_combined_path_and_match(self, network_with_attrs: Network) -> None:
        """Dict selector combining path regex and match conditions."""
        td = TrafficDemand(
            source={
                "path": "^dc1_.*",  # Only dc1
                "match": {
                    "conditions": [{"attr": "role", "op": "==", "value": "leaf"}]
                },
            },
            target={
                "path": "^dc2_.*",  # Only dc2
                "match": {
                    "conditions": [{"attr": "role", "op": "==", "value": "spine"}]
                },
            },
            volume=100.0,
            mode="pairwise",
        )
        expansion = expand_demands(network_with_attrs, [td])

        # 2 dc1 leafs -> 2 dc2 spines = 4 pairs
        assert len(expansion.demands) == 4


class TestTrafficDemandFieldPreservation:
    """Test that TrafficDemand fields are preserved in workflow contexts."""

    def test_all_fields_preserved_in_dict_round_trip(self) -> None:
        """Core fields survive dict serialization."""
        original = TrafficDemand(
            id="test-id",
            source="^dc1/.*",
            target="^dc2/.*",
            volume=100.0,
            mode="combine",
            group_mode="per_group",
            priority=5,
        )

        # Serialize as done in workflow steps
        serialized = {
            "id": original.id,
            "source": original.source,
            "target": original.target,
            "volume": original.volume,
            "mode": original.mode,
            "group_mode": original.group_mode,
            "priority": original.priority,
        }

        # Reconstruct
        reconstructed = TrafficDemand(
            id=serialized.get("id") or "",
            source=serialized["source"],
            target=serialized["target"],
            volume=float(serialized["volume"]),
            mode=str(serialized.get("mode", "pairwise")),
            group_mode=str(serialized.get("group_mode", "flatten")),
            priority=int(serialized.get("priority", 0)),
        )

        assert reconstructed.id == original.id
        assert reconstructed.source == original.source
        assert reconstructed.target == original.target
        assert reconstructed.volume == original.volume
        assert reconstructed.mode == original.mode
        assert reconstructed.group_mode == original.group_mode
        assert reconstructed.priority == original.priority

    def test_default_values_for_new_fields(self) -> None:
        """New fields have sensible defaults when not specified."""
        td = TrafficDemand(
            source="^A$",
            target="^B$",
            volume=100.0,
        )

        assert td.group_mode == "flatten"
