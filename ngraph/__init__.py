"""NetGraph: Network modeling and analysis library.

NetGraph provides interfaces for network topology modeling, traffic analysis, and
capacity planning using a hybrid Python+C++ architecture.

Primary API:
    analyze() - Create an analysis context for network queries
    AnalysisContext - Prepared state for efficient repeated analysis
    Network, Node, Link - Network topology model
    from_networkx() - Convert NetworkX graph to internal format
    to_networkx() - Convert internal format back to NetworkX

Example:
    from ngraph import Network, Node, Link, analyze

    # Build network
    net = Network()
    net.add_node(Node(name="A"))
    net.add_node(Node(name="B"))
    net.add_link(Link(source="A", target="B", capacity=100.0))

    # One-off analysis
    flow = analyze(net).max_flow("^A$", "^B$")

    # Efficient repeated analysis
    ctx = analyze(net, source="^A$", sink="^B$")
    baseline = ctx.max_flow()
    degraded = ctx.max_flow(excluded_links=failed_links)
"""

from __future__ import annotations

from ngraph import cli, logging
from ngraph._version import __version__
from ngraph.analysis import AnalysisContext, analyze
from ngraph.exec.failure.manager import FailureManager
from ngraph.lib.nx import EdgeMap, NodeMap, from_networkx, to_networkx
from ngraph.model.demand.matrix import TrafficMatrixSet
from ngraph.model.network import Link, Network, Node, RiskGroup
from ngraph.model.path import Path
from ngraph.results.artifacts import CapacityEnvelope
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.types.base import EdgeSelect, FlowPlacement, Mode
from ngraph.types.dto import EdgeRef, MaxFlowResult

__all__ = [
    # Version
    "__version__",
    # Model
    "Network",
    "Node",
    "Link",
    "RiskGroup",
    "Path",
    "TrafficMatrixSet",
    # Analysis (primary API)
    "analyze",
    "AnalysisContext",
    # Types
    "FlowPlacement",
    "EdgeSelect",
    "Mode",
    "EdgeRef",
    "MaxFlowResult",
    # Results
    "FlowEntry",
    "FlowIterationResult",
    "FlowSummary",
    "CapacityEnvelope",
    # Execution
    "FailureManager",
    # Library integrations (NetworkX)
    "EdgeMap",
    "NodeMap",
    "from_networkx",
    "to_networkx",
    # Utilities
    "cli",
    "logging",
]
