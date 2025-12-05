"""Tests for flow analysis using the AnalysisContext API.

This module tests maximum flow calculations using the new analyze() API.
"""

import pytest

from ngraph import Link, Mode, Network, Node, analyze


class TestMaxFlow:
    """Tests for maximum flow calculations."""

    def test_max_flow_simple(self):
        """Test max flow on a simple bottleneck scenario."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=3))

        flow_value = analyze(net).max_flow("^A$", "^C$", mode=Mode.COMBINE)
        assert flow_value == {("^A$", "^C$"): 3.0}

    def test_max_flow_multi_parallel(self):
        """Test max flow with parallel paths."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))

        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=5))
        net.add_link(Link("A", "D", capacity=5))
        net.add_link(Link("D", "C", capacity=5))

        flow_value = analyze(net).max_flow("^A$", "^C$", mode=Mode.COMBINE)
        assert flow_value == {("^A$", "^C$"): 10.0}

    def test_max_flow_no_source(self):
        """Test max flow when no source nodes match the pattern."""
        net = Network()
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("B", "C", capacity=10))

        with pytest.raises(ValueError, match="No source nodes found matching"):
            analyze(net).max_flow("^A$", "^C$")

    def test_max_flow_no_sink(self):
        """Test max flow when no sink nodes match the pattern."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError, match="No sink nodes found matching"):
            analyze(net).max_flow("^A$", "^C$")

    def test_max_flow_with_attribute_grouping_combine(self):
        """Test max flow when grouping sources/sinks by attribute directive."""
        net = Network()
        # Sources group: src_group=src
        net.add_node(Node("S1", attrs={"src_group": "src"}))
        net.add_node(Node("S2", attrs={"src_group": "src"}))
        # Sink group: dst_group=dst
        net.add_node(Node("T1", attrs={"dst_group": "dst"}))

        net.add_link(Link("S1", "T1", capacity=5.0))
        net.add_link(Link("S2", "T1", capacity=3.0))

        flow = analyze(net).max_flow(
            "attr:src_group", "attr:dst_group", mode=Mode.COMBINE
        )
        assert flow == {("src", "dst"): 8.0}

    def test_max_flow_with_mixed_attr_and_regex(self):
        """Mix attribute directive with regex path selection."""
        net = Network()
        net.add_node(Node("S1", attrs={"role": "edge"}))
        net.add_node(Node("S2", attrs={"role": "edge"}))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "T1", capacity=2.0))
        net.add_link(Link("S2", "T2", capacity=3.0))

        flow = analyze(net).max_flow("attr:role", r"^T\d$", mode=Mode.PAIRWISE)
        # Groups: sources -> {"edge": [S1, S2]}, sinks -> {"T1": [T1], "T2": [T2]}
        # In pairwise mode with attr:role, we get (edge, T1), (edge, T2)
        # The sink pattern r"^T\d$" creates individual labels per node
        assert len(flow) >= 1
        # Total flow for pairwise is computed per pair entries
        for _key, val in flow.items():
            assert isinstance(val, (int, float))
            assert val >= 0.0

    def test_max_flow_overlap_detection_coverage(self):
        """Test specific overlap detection logic in max_flow combine mode for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("B", "C", capacity=3.0))

        # Create a scenario where there are valid groups but they overlap
        flow_result = analyze(net).max_flow(
            r"^(A|B)$",  # Matches A and B
            r"^(B|C)$",  # Matches B and C (B overlaps!)
            mode=Mode.COMBINE,
        )

        # Should return 0 flow due to B being in both source and sink groups
        assert len(flow_result) == 1
        assert list(flow_result.values())[0] == 0.0

    def test_max_flow_disabled_nodes_coverage(self):
        """Test max_flow with disabled source nodes for coverage."""
        net = Network()
        net.add_node(Node("A", disabled=True))  # Disabled source
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=10))
        net.add_link(Link("B", "C", capacity=10))

        # Source A is disabled, so no flow should be possible
        flow = analyze(net).max_flow("^A$", "^C$", mode=Mode.COMBINE)
        assert flow[("^A$", "^C$")] == 0.0

    def test_max_flow_disabled_link_coverage(self):
        """Test max_flow with disabled links for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=10, disabled=True))  # Disabled link
        net.add_link(Link("B", "C", capacity=10))

        # Link A->B is disabled, so no flow should be possible
        flow = analyze(net).max_flow("^A$", "^C$", mode=Mode.COMBINE)
        assert flow[("^A$", "^C$")] == 0.0


class TestMaxFlowPairwise:
    """Tests for pairwise mode max flow."""

    def test_pairwise_mode_basic(self):
        """Test pairwise mode returns flows per pair."""
        net = Network()
        net.add_node(Node("S1"))
        net.add_node(Node("S2"))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "T1", capacity=5.0))
        net.add_link(Link("S2", "T2", capacity=3.0))

        # Use capturing groups to get individual node labels
        flow = analyze(net).max_flow(r"^(S\d)$", r"^(T\d)$", mode=Mode.PAIRWISE)

        # Should have flows for S1->T1 and S2->T2
        assert ("S1", "T1") in flow
        assert ("S2", "T2") in flow
        assert flow[("S1", "T1")] == 5.0
        assert flow[("S2", "T2")] == 3.0

    def test_pairwise_with_shared_intermediate(self):
        """Test pairwise mode with shared intermediate node."""
        net = Network()
        net.add_node(Node("S1"))
        net.add_node(Node("S2"))
        net.add_node(Node("X"))  # Shared intermediate
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "X", capacity=10.0))
        net.add_link(Link("S2", "X", capacity=10.0))
        net.add_link(Link("X", "T1", capacity=5.0))
        net.add_link(Link("X", "T2", capacity=5.0))

        # Use capturing groups to get individual node labels
        flow = analyze(net).max_flow(r"^(S\d)$", r"^(T\d)$", mode=Mode.PAIRWISE)

        # In pairwise, each pair is independent
        assert ("S1", "T1") in flow
        assert ("S1", "T2") in flow
        assert ("S2", "T1") in flow
        assert ("S2", "T2") in flow


class TestMaxFlowCombine:
    """Tests for combine mode max flow."""

    def test_combine_mode_aggregates(self):
        """Test combine mode aggregates sources and sinks."""
        net = Network()
        net.add_node(Node("S1"))
        net.add_node(Node("S2"))
        net.add_node(Node("X"))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "X", capacity=5.0))
        net.add_link(Link("S2", "X", capacity=5.0))
        net.add_link(Link("X", "T1", capacity=5.0))
        net.add_link(Link("X", "T2", capacity=5.0))

        # Use capturing groups - labels become captured values joined with |
        flow = analyze(net).max_flow(r"^(S\d)$", r"^(T\d)$", mode=Mode.COMBINE)

        # Should have single combined result (labels are S1|S2 and T1|T2)
        assert len(flow) == 1
        key = list(flow.keys())[0]
        # Combined flow limited by middle node X: 10 in, 10 out
        assert flow[key] == 10.0


class TestExclusions:
    """Tests for node and link exclusions."""

    def test_exclude_node(self):
        """Test excluding a node reduces flow."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))

        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "D", capacity=5))
        net.add_link(Link("A", "C", capacity=3))
        net.add_link(Link("C", "D", capacity=3))

        # Full flow through both paths
        full_flow = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)
        assert full_flow[("^A$", "^D$")] == 8.0

        # Exclude B, only C path available
        reduced_flow = analyze(net).max_flow(
            "^A$", "^D$", mode=Mode.COMBINE, excluded_nodes={"B"}
        )
        assert reduced_flow[("^A$", "^D$")] == 3.0

    def test_exclude_link(self):
        """Test excluding a link reduces flow."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))

        link_ab = Link("A", "B", capacity=5)
        link_bd = Link("B", "D", capacity=5)
        link_ac = Link("A", "C", capacity=3)
        link_cd = Link("C", "D", capacity=3)

        net.add_link(link_ab)
        net.add_link(link_bd)
        net.add_link(link_ac)
        net.add_link(link_cd)

        # Get the A->B link ID
        ab_link_id = None
        for link_id, link in net.links.items():
            if link.source == "A" and link.target == "B":
                ab_link_id = link_id
                break

        # Exclude A->B link
        reduced_flow = analyze(net).max_flow(
            "^A$", "^D$", mode=Mode.COMBINE, excluded_links={ab_link_id}
        )
        assert reduced_flow[("^A$", "^D$")] == 3.0


class TestBoundContext:
    """Tests for bound AnalysisContext."""

    def test_bound_context_basic(self):
        """Test bound context for repeated analysis."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))

        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "D", capacity=5))
        net.add_link(Link("A", "C", capacity=3))
        net.add_link(Link("C", "D", capacity=3))

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)

        # Multiple calls should work
        flow1 = ctx.max_flow()
        flow2 = ctx.max_flow(excluded_nodes={"B"})
        flow3 = ctx.max_flow(excluded_nodes={"C"})

        assert flow1[("^A$", "^D$")] == 8.0
        assert flow2[("^A$", "^D$")] == 3.0
        assert flow3[("^A$", "^D$")] == 5.0

    def test_bound_context_rejects_source_sink(self):
        """Test that bound context rejects source/sink arguments."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        ctx = analyze(net, source="^A$", sink="^B$", mode=Mode.COMBINE)

        with pytest.raises(ValueError, match="Bound context"):
            ctx.max_flow(source="^X$", sink="^Y$")
