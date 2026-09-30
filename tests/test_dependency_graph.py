"""
tests/test_dependency_graph.py

Tests for ExecutionTwinGraph (backend/twin/graph.py) and the graph models.

These tests exercise:
  - graph construction from DependencyAnalysis
  - node / edge queries (has_node, has_edge, successors, predecessors)
  - cycle detection (find_cycles)
  - path finding (paths_to)
  - summary statistics
  - ArchitectureCompatibilityAnalyzer classification rules (all combinations)
  - DependencyAnalysis serialization round-trip
"""

from __future__ import annotations

import uuid

import pytest

from backend.analyzers.arch_compat import ArchitectureCompatibilityAnalyzer
from backend.models.common import (
    Architecture,
    ArchitectureClassification,
    EvidenceType,
    Provenance,
    SourceMechanism,
    utc_now,
)
from backend.models.graph import (
    ArchRelationship,
    ArchRelationshipSeverity,
    DependencyAnalysis,
    DependencyEdge,
    DependencyKind,
    DependencyNode,
    EdgeKind,
    NodeKind,
    ResolutionStatus,
)
from backend.twin.graph import ExecutionTwinGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nid() -> str:
    return str(uuid.uuid4())[:16]


def _node(node_id: str, name: str, arch: Architecture = Architecture.X64, depth: int = 0) -> DependencyNode:
    return DependencyNode(
        node_id=node_id,
        kind=NodeKind.DLL,
        name=name,
        architecture=arch,
        depth=depth,
    )


def _edge(src: str, tgt: str, kind: EdgeKind = EdgeKind.IMPORTS) -> DependencyEdge:
    return DependencyEdge(
        edge_id=str(uuid.uuid4()),
        source_id=src,
        target_id=tgt,
        edge_kind=kind,
        dependency_kind=DependencyKind.STATIC_DEPENDENCY,
        evidence_type=EvidenceType.OBSERVED,
        confidence=1.0,
    )


def _empty_analysis() -> DependencyAnalysis:
    return DependencyAnalysis(
        id=str(uuid.uuid4()),
        application_id=str(uuid.uuid4()),
        root_path="C:/App/app.exe",
    )


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def test_graph_builds_from_analysis():
    """ExecutionTwinGraph builds without error from a minimal DependencyAnalysis."""
    a = _empty_analysis()
    root_id = _nid()
    a.nodes.append(_node(root_id, "app.exe", depth=0))
    g = ExecutionTwinGraph.from_analysis(a)
    assert g.has_node(root_id)


def test_graph_has_expected_edges():
    a = _empty_analysis()
    root_id, dep_id = _nid(), _nid()
    a.nodes += [_node(root_id, "app.exe", depth=0), _node(dep_id, "dep.dll", depth=1)]
    a.edges.append(_edge(root_id, dep_id))
    g = ExecutionTwinGraph.from_analysis(a)
    assert g.has_edge(root_id, dep_id)


def test_self_referential_resolves_to_edge_excluded_from_traversal():
    """RESOLVES_TO self-edges must not appear in graph traversal."""
    a = _empty_analysis()
    n_id = _nid()
    a.nodes.append(_node(n_id, "dep.dll", depth=1))
    # Self-referential RESOLVES_TO edge
    a.edges.append(DependencyEdge(
        edge_id=str(uuid.uuid4()),
        source_id=n_id,
        target_id=n_id,
        edge_kind=EdgeKind.RESOLVES_TO,
        dependency_kind=DependencyKind.STATIC_DEPENDENCY,
        evidence_type=EvidenceType.OBSERVED,
        confidence=1.0,
    ))
    g = ExecutionTwinGraph.from_analysis(a)
    # Should NOT appear as a real edge in the traversal graph
    assert not g.has_edge(n_id, n_id)


# ---------------------------------------------------------------------------
# Node / edge queries
# ---------------------------------------------------------------------------

def test_successors_returns_direct_children():
    a = _empty_analysis()
    r, c1, c2 = _nid(), _nid(), _nid()
    a.nodes += [_node(r, "root", depth=0), _node(c1, "child1", depth=1), _node(c2, "child2", depth=1)]
    a.edges += [_edge(r, c1), _edge(r, c2)]
    g = ExecutionTwinGraph.from_analysis(a)
    assert set(g.successors(r)) == {c1, c2}


def test_predecessors_returns_parents():
    a = _empty_analysis()
    r, c = _nid(), _nid()
    a.nodes += [_node(r, "root", depth=0), _node(c, "child", depth=1)]
    a.edges.append(_edge(r, c))
    g = ExecutionTwinGraph.from_analysis(a)
    assert g.predecessors(c) == [r]


def test_unknown_node_queries_return_empty():
    g = ExecutionTwinGraph.from_analysis(_empty_analysis())
    assert g.successors("nonexistent") == []
    assert g.predecessors("nonexistent") == []
    assert g.paths_to("nonexistent") == []


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

def test_no_cycles_in_acyclic_graph():
    a = _empty_analysis()
    r, c = _nid(), _nid()
    a.nodes += [_node(r, "root"), _node(c, "child")]
    a.edges.append(_edge(r, c))
    g = ExecutionTwinGraph.from_analysis(a)
    assert g.find_cycles() == []


def test_cycle_detected():
    """A → B → A cycle is detected by find_cycles()."""
    a = _empty_analysis()
    id_a, id_b = _nid(), _nid()
    a.nodes += [_node(id_a, "A.dll"), _node(id_b, "B.dll")]
    a.edges += [_edge(id_a, id_b), _edge(id_b, id_a)]
    g = ExecutionTwinGraph.from_analysis(a)
    cycles = g.find_cycles()
    assert len(cycles) > 0


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def test_paths_to_direct_child():
    a = _empty_analysis()
    r, c = _nid(), _nid()
    a.nodes += [_node(r, "root", depth=0), _node(c, "leaf", depth=1)]
    a.edges.append(_edge(r, c))
    g = ExecutionTwinGraph.from_analysis(a)
    paths = g.paths_to(c)
    assert paths == [[r, c]]


def test_paths_to_deep_node():
    """root → mid → leaf: exactly one path to leaf."""
    a = _empty_analysis()
    r, m, l = _nid(), _nid(), _nid()
    a.nodes += [_node(r, "root", depth=0), _node(m, "mid", depth=1), _node(l, "leaf", depth=2)]
    a.edges += [_edge(r, m), _edge(m, l)]
    g = ExecutionTwinGraph.from_analysis(a)
    paths = g.paths_to(l)
    assert [r, m, l] in paths


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_counts():
    a = _empty_analysis()
    r, c = _nid(), _nid()
    a.nodes += [_node(r, "root", depth=0), _node(c, "dep", depth=1)]
    a.edges.append(_edge(r, c))
    a.total_dependencies = 1
    a.resolved_count = 1
    g = ExecutionTwinGraph.from_analysis(a)
    s = g.summary()
    assert s["total_nodes"] == 2
    assert s["total_edges"] == 1
    assert s["resolved"] == 1


# ---------------------------------------------------------------------------
# node_data
# ---------------------------------------------------------------------------

def test_node_data_returns_correct_node():
    a = _empty_analysis()
    nid = _nid()
    a.nodes.append(_node(nid, "mylib.dll", Architecture.X86))
    g = ExecutionTwinGraph.from_analysis(a)
    nd = g.node_data(nid)
    assert nd is not None
    assert nd.name == "mylib.dll"
    assert nd.architecture == Architecture.X86


def test_node_data_missing_returns_none():
    g = ExecutionTwinGraph.from_analysis(_empty_analysis())
    assert g.node_data("does-not-exist") is None


# ---------------------------------------------------------------------------
# ArchitectureCompatibilityAnalyzer — classification rules
# ---------------------------------------------------------------------------

_compat = ArchitectureCompatibilityAnalyzer()


def _rel(src: Architecture, tgt: Architecture) -> ArchRelationship:
    r = _compat.analyze("src", "tgt", src, tgt)
    return r.static_relationship


def _sev(src: Architecture, tgt: Architecture) -> ArchRelationshipSeverity:
    r = _compat.analyze("src", "tgt", src, tgt)
    return r.severity


def test_compat_x64_x64_native_match():
    assert _rel(Architecture.X64, Architecture.X64) == ArchRelationship.NATIVE_MATCH


def test_compat_x86_x86_native_match():
    assert _rel(Architecture.X86, Architecture.X86) == ArchRelationship.NATIVE_MATCH


def test_compat_arm64_arm64_native_match():
    assert _rel(Architecture.ARM64, Architecture.ARM64) == ArchRelationship.NATIVE_MATCH


def test_compat_arm64ec_arm64ec_native_match():
    assert _rel(Architecture.ARM64EC, Architecture.ARM64EC) == ArchRelationship.NATIVE_MATCH


def test_compat_x64_arm64_potential_conflict_high():
    assert _rel(Architecture.X64, Architecture.ARM64) == ArchRelationship.POTENTIAL_CONFLICT
    assert _sev(Architecture.X64, Architecture.ARM64) == ArchRelationshipSeverity.HIGH


def test_compat_x64_arm64ec_mixed_architecture():
    assert _rel(Architecture.X64, Architecture.ARM64EC) == ArchRelationship.MIXED_ARCHITECTURE


def test_compat_x64_x86_potential_conflict():
    assert _rel(Architecture.X64, Architecture.X86) == ArchRelationship.POTENTIAL_CONFLICT


def test_compat_arm64ec_arm64_mixed_architecture():
    assert _rel(Architecture.ARM64EC, Architecture.ARM64) == ArchRelationship.MIXED_ARCHITECTURE


def test_compat_arm64ec_x64_mixed_architecture():
    assert _rel(Architecture.ARM64EC, Architecture.X64) == ArchRelationship.MIXED_ARCHITECTURE


def test_compat_arm64_x64_potential_conflict():
    assert _rel(Architecture.ARM64, Architecture.X64) == ArchRelationship.POTENTIAL_CONFLICT


def test_compat_unknown_produces_unknown():
    assert _rel(Architecture.UNKNOWN, Architecture.X64) == ArchRelationship.UNKNOWN
    assert _rel(Architecture.X64, Architecture.UNKNOWN) == ArchRelationship.UNKNOWN
    assert _rel(Architecture.UNKNOWN, Architecture.UNKNOWN) == ArchRelationship.UNKNOWN


def test_compat_uncertain_classification_lowers_confidence():
    """UNCERTAIN arch classification on either side reduces confidence below 1.0."""
    result = _compat.analyze(
        "src", "tgt",
        Architecture.X64, Architecture.X64,
        source_classification=ArchitectureClassification.UNCERTAIN,
    )
    assert result.confidence < 1.0


def test_compat_result_carries_provenance():
    result = _compat.analyze("src", "tgt", Architecture.X64, Architecture.ARM64)
    assert result.provenance is not None
    assert result.provenance.evidence_type == EvidenceType.INFERRED


def test_compat_result_reason_is_nonempty():
    result = _compat.analyze("src", "tgt", Architecture.X64, Architecture.ARM64)
    assert result.reason, "Reason string must not be empty"


def test_runtime_status_is_not_observed():
    result = _compat.analyze("src", "tgt", Architecture.X64, Architecture.ARM64)
    from backend.models.graph import RuntimeExecutionStatus, RuntimeExecutionMechanism
    assert result.runtime_status == RuntimeExecutionStatus.NOT_OBSERVED
    assert result.runtime_mechanism == RuntimeExecutionMechanism.UNKNOWN


def test_potential_conflict_is_not_a_failure_verdict():
    """
    POTENTIAL_CONFLICT must NOT claim the application will crash.
    Verify the reason string does not contain absolute failure language.
    """
    result = _compat.analyze("src", "tgt", Architecture.X64, Architecture.ARM64)
    reason_lower = result.reason.lower()
    for forbidden in ["incompatible", "will fail", "crash", "guaranteed"]:
        assert forbidden not in reason_lower, (
            f"Reason contains forbidden verdict language: '{forbidden}'"
        )


# ---------------------------------------------------------------------------
# DependencyAnalysis serialization round-trip
# ---------------------------------------------------------------------------

def test_dependency_analysis_json_round_trip():
    """DependencyAnalysis must serialize and deserialize cleanly via Pydantic."""
    a = _empty_analysis()
    nid = _nid()
    a.nodes.append(_node(nid, "lib.dll", Architecture.X64, depth=1))
    a.analysis_complete = True

    json_str = a.model_dump_json()
    restored = DependencyAnalysis.model_validate_json(json_str)

    assert restored.id == a.id
    assert len(restored.nodes) == 1
    assert restored.nodes[0].name == "lib.dll"
    assert restored.analysis_complete
