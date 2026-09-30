"""
backend/twin/graph.py

ExecutionTwinGraph – Stage 3 graph layer.

Wraps a networkx DiGraph built from the flat node/edge lists produced by
DependencyAnalyzer.  Provides algorithm-level accessors (paths, cycles,
neighbour queries) while keeping the serializable DependencyAnalysis model
as the authoritative data source.

Design choices
--------------
- The networkx graph is built lazily / on-demand and never mutated after
  construction; all mutation goes through DependencyAnalysis.
- networkx is already a declared dependency (pyproject.toml).
- No runtime telemetry data is mixed into this graph in Stage 3; that is
  Stage 4+.

Public methods
--------------
  from_analysis(analysis) -> ExecutionTwinGraph
  has_node(node_id)       -> bool
  has_edge(src, tgt)      -> bool
  successors(node_id)     -> list[str]
  predecessors(node_id)   -> list[str]
  find_cycles()           -> list[list[str]]
  paths_to(target_id)     -> list[list[str]]
  node_data(node_id)      -> DependencyNode | None
  summary()               -> dict
"""

from __future__ import annotations

from typing import Any, Optional

import networkx as nx

from backend.models.graph import DependencyAnalysis, DependencyNode


class ExecutionTwinGraph:
    """
    Algorithm-level wrapper around a DependencyAnalysis result.

    The underlying DiGraph uses node_id strings as keys; node/edge
    metadata is stored as node/edge attributes so networkx algorithms
    can be applied directly.
    """

    def __init__(self, analysis: DependencyAnalysis) -> None:
        self._analysis = analysis
        self._graph: nx.DiGraph = self._build(analysis)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_analysis(cls, analysis: DependencyAnalysis) -> "ExecutionTwinGraph":
        return cls(analysis)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build(self, analysis: DependencyAnalysis) -> nx.DiGraph:
        g: nx.DiGraph = nx.DiGraph()

        for node in analysis.nodes:
            g.add_node(
                node.node_id,
                name=node.name,
                kind=node.kind.value,
                architecture=node.architecture.value,
                resolved_path=node.resolved_path,
                is_system_dll=node.is_system_dll,
                analysis_skipped=node.analysis_skipped,
                depth=node.depth,
            )

        for edge in analysis.edges:
            # Skip self-referential RESOLVES_TO edges for graph traversal
            # (they exist in the analysis model for provenance but add noise
            # to path algorithms).
            if edge.source_id == edge.target_id:
                continue
            g.add_edge(
                edge.source_id,
                edge.target_id,
                edge_id=edge.edge_id,
                edge_kind=edge.edge_kind.value,
                dependency_kind=edge.dependency_kind.value,
                evidence_type=edge.evidence_type.value,
                confidence=edge.confidence,
            )

        return g

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def has_node(self, node_id: str) -> bool:
        return self._graph.has_node(node_id)

    def has_edge(self, source_id: str, target_id: str) -> bool:
        return self._graph.has_edge(source_id, target_id)

    def successors(self, node_id: str) -> list[str]:
        """Direct children (dependencies) of this node."""
        if not self._graph.has_node(node_id):
            return []
        return list(self._graph.successors(node_id))

    def predecessors(self, node_id: str) -> list[str]:
        """Modules that directly depend on this node."""
        if not self._graph.has_node(node_id):
            return []
        return list(self._graph.predecessors(node_id))

    def find_cycles(self) -> list[list[str]]:
        """Return all simple cycles in the graph as lists of node IDs."""
        try:
            return list(nx.simple_cycles(self._graph))
        except nx.NetworkXNoCycle:
            return []

    def paths_to(self, target_id: str) -> list[list[str]]:
        """
        All simple paths from the root node to target_id.
        Root is the first node in analysis.nodes (depth=0).
        """
        if not self._analysis.nodes:
            return []
        root_id = self._analysis.nodes[0].node_id
        if not self._graph.has_node(target_id):
            return []
        try:
            return list(nx.all_simple_paths(self._graph, root_id, target_id))
        except (nx.NodeNotFound, nx.NetworkXError):
            return []

    def node_data(self, node_id: str) -> Optional[DependencyNode]:
        """Return the DependencyNode for a given id, or None."""
        for node in self._analysis.nodes:
            if node.node_id == node_id:
                return node
        return None

    def nodes_at_depth(self, depth: int) -> list[DependencyNode]:
        return [n for n in self._analysis.nodes if n.depth == depth]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self._analysis.nodes),
            "total_edges": len(
                [e for e in self._analysis.edges if e.source_id != e.target_id]
            ),
            "total_dependencies": self._analysis.total_dependencies,
            "resolved": self._analysis.resolved_count,
            "missing": self._analysis.missing_count,
            "skipped": self._analysis.skipped_count,
            "max_depth_reached": self._analysis.max_depth_reached,
            "cycles": len(self.find_cycles()),
            "architecture_relationships": len(self._analysis.architecture_relationships),
            "analysis_complete": self._analysis.analysis_complete,
        }
