"""
tests/test_dependency_analyzer.py

Stage 3 dependency analyzer tests.

Testing strategy
----------------
The DependencyAnalyzer has two injectable seams: the DLLResolver and the
PEAnalyzer.  All tests below inject mock implementations so:

  (a) no real filesystem access is required beyond what is explicitly set up,
  (b) ARM64 / ARM64EC graph logic can be tested without real ARM binaries,
  (c) mock results are clearly labelled as MODEL-LEVEL tests (they exercise
      the graph logic, not the PE parser or the resolver's disk search).

Only tests that use a real Windows binary (test_x64_real_*) exercise the
full stack against the actual filesystem.

IMPORTANT: mock ApplicationAnalysis objects represent model-level graph
logic tests.  They are NOT claimed to be real system observations.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.analyzers.dependency_analyzer import DependencyAnalyzer, _node_id
from backend.analyzers.dll_resolver import AbstractDLLResolver
from backend.models.application import ApplicationAnalysis, ApplicationIdentity
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
    DependencyKind,
    EdgeKind,
    NodeKind,
    ResolutionMethod,
    ResolutionStatus,
    DependencyResolution,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_provenance(arch: Architecture, cls: ArchitectureClassification) -> Provenance:
    return Provenance(
        source=SourceMechanism.PE_STATIC_ANALYSIS,
        evidence_type=EvidenceType.OBSERVED,
        confidence=1.0,
        raw={
            "architecture": arch.value,
            "classification": cls.value,
            "evidence": [],
            "confidence": 1.0,
            "warnings": [],
        },
    )


def _make_root(
    path: str = "C:/App/app.exe",
    arch: Architecture = Architecture.X64,
    imports: list[str] | None = None,
    delay_imports: list[str] | None = None,
) -> ApplicationAnalysis:
    """Build a minimal ApplicationAnalysis for use as DependencyAnalyzer input."""
    identity = ApplicationIdentity(
        id=str(uuid.uuid4()),
        display_name="app.exe",
        exe_path=path,
        architecture=arch,
        architecture_provenance=_make_provenance(arch, ArchitectureClassification.DETECTED),
    )
    analysis = ApplicationAnalysis(
        id=str(uuid.uuid4()),
        identity=identity,
        analysis_complete=True,
        imports=imports or [],
        delay_imports=delay_imports or [],
    )
    return analysis


def _make_pe_result(
    path: str,
    arch: Architecture,
    imports: list[str] | None = None,
    delay_imports: list[str] | None = None,
    complete: bool = True,
) -> ApplicationAnalysis:
    """Build a mock PEAnalyzer result for a dependency DLL."""
    name = path.split("/")[-1].split("\\")[-1]
    identity = ApplicationIdentity(
        id=str(uuid.uuid4()),
        display_name=name,
        exe_path=path,
        architecture=arch,
        architecture_provenance=_make_provenance(arch, ArchitectureClassification.DETECTED),
    )
    return ApplicationAnalysis(
        id=str(uuid.uuid4()),
        identity=identity,
        analysis_complete=complete,
        imports=imports or [],
        delay_imports=delay_imports or [],
    )


class MockResolver(AbstractDLLResolver):
    """
    Configurable mock resolver.

    resolve_map: dict mapping lowercase DLL name → resolved_path (str) or None.
    """

    def __init__(self, resolve_map: dict[str, str | None] | None = None) -> None:
        self._map = {k.lower(): v for k, v in (resolve_map or {}).items()}

    def resolve(
        self,
        name: str,
        importing_binary_path: str,
        extra_search_paths=None,
    ) -> DependencyResolution:
        from backend.analyzers.dll_resolver import _is_known_system_dll
        is_sys = _is_known_system_dll(name)
        key = name.lower()
        path = self._map.get(key)
        if path is not None:
            return DependencyResolution(
                requested_name=name,
                resolved_path=path,
                status=ResolutionStatus.RESOLVED,
                method=ResolutionMethod.APPLICATION_DIR,
                is_system_dll=is_sys,
                provenance=Provenance(
                    source=SourceMechanism.PE_STATIC_ANALYSIS,
                    evidence_type=EvidenceType.OBSERVED,
                    confidence=1.0,
                    timestamp=utc_now(),
                ),
            )
        return DependencyResolution(
            requested_name=name,
            resolved_path=None,
            status=ResolutionStatus.MISSING,
            method=ResolutionMethod.UNKNOWN,
            is_system_dll=is_sys,
            provenance=Provenance(
                source=SourceMechanism.PE_STATIC_ANALYSIS,
                evidence_type=EvidenceType.OBSERVED,
                confidence=1.0,
                timestamp=utc_now(),
            ),
        )


class MockPEAnalyzer:
    """Returns pre-configured ApplicationAnalysis by path."""

    def __init__(self, result_map: dict[str, ApplicationAnalysis] | None = None) -> None:
        self._map = result_map or {}

    def analyze(self, path: str) -> ApplicationAnalysis:
        if path in self._map:
            return self._map[path]
        # Default: incomplete analysis
        identity = ApplicationIdentity(
            id=str(uuid.uuid4()),
            display_name=path.split("/")[-1],
            exe_path=path,
        )
        return ApplicationAnalysis(id=str(uuid.uuid4()), identity=identity)


# ---------------------------------------------------------------------------
# 1. Direct dependency
# ---------------------------------------------------------------------------

def test_direct_dependency_appears_as_node():
    """MODEL-LEVEL: A directly imported DLL appears as a child node."""
    root = _make_root(imports=["foo.dll"])
    resolver = MockResolver({"foo.dll": "C:/App/foo.dll"})
    pe = MockPEAnalyzer({"C:/App/foo.dll": _make_pe_result("C:/App/foo.dll", Architecture.X64)})

    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    names = [n.name for n in result.nodes]
    assert "foo.dll" in names


def test_direct_dependency_edge_is_static():
    """MODEL-LEVEL: The edge from root to direct dep is STATIC_DEPENDENCY."""
    root = _make_root(imports=["foo.dll"])
    resolver = MockResolver({"foo.dll": "C:/App/foo.dll"})
    pe = MockPEAnalyzer({"C:/App/foo.dll": _make_pe_result("C:/App/foo.dll", Architecture.X64)})

    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    import_edges = [e for e in result.edges if e.edge_kind == EdgeKind.IMPORTS]
    assert import_edges, "Expected at least one IMPORTS edge"
    assert all(e.dependency_kind == DependencyKind.STATIC_DEPENDENCY for e in import_edges)


# ---------------------------------------------------------------------------
# 2. Recursive dependency
# ---------------------------------------------------------------------------

def test_recursive_dependency_two_levels():
    """MODEL-LEVEL: app→A→B produces 3 nodes (root, A, B)."""
    root = _make_root(imports=["A.dll"])
    resolver = MockResolver({
        "a.dll": "C:/App/A.dll",
        "b.dll": "C:/App/B.dll",
    })
    pe = MockPEAnalyzer({
        "C:/App/A.dll": _make_pe_result("C:/App/A.dll", Architecture.X64, imports=["B.dll"]),
        "C:/App/B.dll": _make_pe_result("C:/App/B.dll", Architecture.X64),
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    node_names = {n.name for n in result.nodes}
    assert "A.dll" in node_names
    assert "B.dll" in node_names
    assert len(result.nodes) == 3  # root + A + B


# ---------------------------------------------------------------------------
# 3. Duplicate dependency (diamond)
# ---------------------------------------------------------------------------

def test_diamond_dependency_no_duplicate_nodes():
    """MODEL-LEVEL: app→A→C and app→B→C should produce C once, not twice."""
    root = _make_root(imports=["A.dll", "B.dll"])
    resolver = MockResolver({
        "a.dll": "C:/App/A.dll",
        "b.dll": "C:/App/B.dll",
        "c.dll": "C:/App/C.dll",
    })
    pe = MockPEAnalyzer({
        "C:/App/A.dll": _make_pe_result("C:/App/A.dll", Architecture.X64, imports=["C.dll"]),
        "C:/App/B.dll": _make_pe_result("C:/App/B.dll", Architecture.X64, imports=["C.dll"]),
        "C:/App/C.dll": _make_pe_result("C:/App/C.dll", Architecture.X64),
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    node_ids = [n.node_id for n in result.nodes]
    assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs found"
    c_nodes = [n for n in result.nodes if n.name == "C.dll"]
    assert len(c_nodes) == 1, f"Expected 1 node for C.dll, got {len(c_nodes)}"


# ---------------------------------------------------------------------------
# 4. Circular dependency
# ---------------------------------------------------------------------------

def test_circular_dependency_no_infinite_loop():
    """MODEL-LEVEL: A→B→A must not loop infinitely; cycle detected via visited set."""
    root = _make_root(imports=["A.dll"])
    resolver = MockResolver({
        "a.dll": "C:/App/A.dll",
        "b.dll": "C:/App/B.dll",
    })
    pe = MockPEAnalyzer({
        "C:/App/A.dll": _make_pe_result("C:/App/A.dll", Architecture.X64, imports=["B.dll"]),
        "C:/App/B.dll": _make_pe_result("C:/App/B.dll", Architecture.X64, imports=["A.dll"]),
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)  # must return without hanging

    # Circular back-edge should be recorded with a note
    back_edges = [
        e for e in result.edges
        if any("Circular" in note for note in e.notes)
    ]
    assert back_edges, "Expected a circular-dependency back-edge with a note"


# ---------------------------------------------------------------------------
# 5. Missing DLL
# ---------------------------------------------------------------------------

def test_missing_dll_recorded_as_node():
    """MODEL-LEVEL: An unresolvable import is still a graph node."""
    root = _make_root(imports=["ghost.dll"])
    resolver = MockResolver({})  # resolves nothing
    da = DependencyAnalyzer(resolver=resolver, analyze_system_dlls=True)
    result = da.analyze(root)

    ghost_nodes = [n for n in result.nodes if n.name == "ghost.dll"]
    assert ghost_nodes, "MISSING DLL should still appear as a node"
    assert ghost_nodes[0].resolution.status == ResolutionStatus.MISSING


def test_missing_dll_increments_counter():
    """MODEL-LEVEL: missing_count is incremented for unresolved imports."""
    root = _make_root(imports=["ghost.dll"])
    resolver = MockResolver({})
    da = DependencyAnalyzer(resolver=resolver)
    result = da.analyze(root)
    assert result.missing_count >= 1


# ---------------------------------------------------------------------------
# 6. Inaccessible DLL (resolver returns INACCESSIBLE)
# ---------------------------------------------------------------------------

def test_inaccessible_dll_is_recorded():
    """MODEL-LEVEL: A resolver returning INACCESSIBLE is preserved in the graph."""

    class InaccessibleResolver(AbstractDLLResolver):
        def resolve(self, name, importing_binary_path, extra_search_paths=None):
            return DependencyResolution(
                requested_name=name,
                resolved_path="C:/Protected/secret.dll",
                status=ResolutionStatus.INACCESSIBLE,
                method=ResolutionMethod.SYSTEM32,
                is_system_dll=False,
                provenance=Provenance(
                    source=SourceMechanism.PE_STATIC_ANALYSIS,
                    evidence_type=EvidenceType.OBSERVED,
                    confidence=1.0,
                    timestamp=utc_now(),
                ),
                notes=["Access denied by OS."],
            )

    root = _make_root(imports=["secret.dll"])
    da = DependencyAnalyzer(resolver=InaccessibleResolver())
    result = da.analyze(root)

    sec_nodes = [n for n in result.nodes if n.name == "secret.dll"]
    assert sec_nodes
    assert sec_nodes[0].resolution.status == ResolutionStatus.INACCESSIBLE


# ---------------------------------------------------------------------------
# 7. x64 dependency — architecture relationship
# ---------------------------------------------------------------------------

def test_x64_to_x64_is_native_match():
    """MODEL-LEVEL: x64 → x64 produces NATIVE_MATCH relationship."""
    root = _make_root(arch=Architecture.X64, imports=["dep.dll"])
    resolver = MockResolver({"dep.dll": "C:/App/dep.dll"})
    pe = MockPEAnalyzer({"C:/App/dep.dll": _make_pe_result("C:/App/dep.dll", Architecture.X64)})
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    rels = result.architecture_relationships
    assert rels, "Expected at least one architecture relationship"
    assert any(r.static_relationship == ArchRelationship.NATIVE_MATCH for r in rels)


# ---------------------------------------------------------------------------
# 8. ARM64 dependency (model-level — no real ARM binary)
# ---------------------------------------------------------------------------

def test_x64_to_arm64_is_potential_conflict():
    """
    MODEL-LEVEL: x64 source importing an ARM64-only DLL is POTENTIAL_CONFLICT.
    This does NOT claim the application will crash; it records a candidate
    architecture boundary for runtime verification.
    """
    root = _make_root(arch=Architecture.X64, imports=["arm_only.dll"])
    resolver = MockResolver({"arm_only.dll": "C:/App/arm_only.dll"})
    pe = MockPEAnalyzer({
        "C:/App/arm_only.dll": _make_pe_result("C:/App/arm_only.dll", Architecture.ARM64)
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    rels = result.architecture_relationships
    conflict_rels = [r for r in rels if r.static_relationship == ArchRelationship.POTENTIAL_CONFLICT]
    assert conflict_rels, "Expected POTENTIAL_CONFLICT for x64 → ARM64"
    assert conflict_rels[0].severity.value == "HIGH"


def test_arm64ec_to_arm64_is_mixed_architecture():
    """
    MODEL-LEVEL: ARM64EC importing ARM64 is MIXED_ARCHITECTURE (supported hybrid).
    """
    root = _make_root(arch=Architecture.ARM64EC, imports=["native.dll"])
    resolver = MockResolver({"native.dll": "C:/App/native.dll"})
    pe = MockPEAnalyzer({
        "C:/App/native.dll": _make_pe_result("C:/App/native.dll", Architecture.ARM64)
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    rels = result.architecture_relationships
    mixed = [r for r in rels if r.static_relationship == ArchRelationship.MIXED_ARCHITECTURE]
    assert mixed, "Expected MIXED_ARCHITECTURE for ARM64EC → ARM64"
    # MIXED_ARCHITECTURE is INFO, not HIGH — no failure verdict
    assert mixed[0].severity.value == "INFO"


# ---------------------------------------------------------------------------
# 9. Architecture uncertainty
# ---------------------------------------------------------------------------

def test_unknown_target_arch_produces_unknown_relationship():
    """MODEL-LEVEL: When target arch is UNKNOWN, relationship is UNKNOWN."""
    root = _make_root(arch=Architecture.X64, imports=["mystery.dll"])
    resolver = MockResolver({"mystery.dll": "C:/App/mystery.dll"})
    # PE analysis incomplete → architecture stays UNKNOWN
    pe = MockPEAnalyzer({
        "C:/App/mystery.dll": _make_pe_result(
            "C:/App/mystery.dll", Architecture.UNKNOWN, complete=False
        )
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    # The node should exist
    mystery = [n for n in result.nodes if n.name == "mystery.dll"]
    assert mystery
    # Architecture relationship (if present) should be UNKNOWN
    rels = result.architecture_relationships
    if rels:
        assert any(r.static_relationship == ArchRelationship.UNKNOWN for r in rels)


# ---------------------------------------------------------------------------
# 10. System DLL policy
# ---------------------------------------------------------------------------

def test_system_dll_not_recursed_by_default():
    """kernel32.dll is known-system; it should be recorded but not recursed."""
    root = _make_root(imports=["kernel32.dll"])
    resolver = MockResolver({"kernel32.dll": r"C:\Windows\System32\kernel32.dll"})
    pe = MockPEAnalyzer()  # should never be called for kernel32

    da = DependencyAnalyzer(
        resolver=resolver,
        pe_analyzer=pe,
        analyze_system_dlls=False,  # default
    )
    result = da.analyze(root)

    k32 = [n for n in result.nodes if n.name.lower() == "kernel32.dll"]
    assert k32, "kernel32.dll should appear as a node"
    assert k32[0].analysis_skipped, "System DLL should be marked analysis_skipped"
    assert k32[0].is_system_dll


def test_system_dll_recursed_when_policy_enabled():
    """When analyze_system_dlls=True, system DLLs are PE-analysed."""
    root = _make_root(imports=["kernel32.dll"])
    resolver = MockResolver({"kernel32.dll": r"C:\Windows\System32\kernel32.dll"})
    # Provide a known PE result so we can verify recursion happened
    pe = MockPEAnalyzer({
        r"C:\Windows\System32\kernel32.dll": _make_pe_result(
            r"C:\Windows\System32\kernel32.dll", Architecture.X64
        )
    })
    da = DependencyAnalyzer(
        resolver=resolver,
        pe_analyzer=pe,
        analyze_system_dlls=True,
    )
    result = da.analyze(root)

    k32 = [n for n in result.nodes if n.name.lower() == "kernel32.dll"]
    assert k32
    assert not k32[0].analysis_skipped


# ---------------------------------------------------------------------------
# 11. Delay import
# ---------------------------------------------------------------------------

def test_delay_import_edge_kind():
    """MODEL-LEVEL: Delay-imported DLL produces a DELAY_IMPORTS edge."""
    root = _make_root(delay_imports=["deferred.dll"])
    resolver = MockResolver({"deferred.dll": "C:/App/deferred.dll"})
    pe = MockPEAnalyzer({"C:/App/deferred.dll": _make_pe_result("C:/App/deferred.dll", Architecture.X64)})
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    delay_edges = [e for e in result.edges if e.edge_kind == EdgeKind.DELAY_IMPORTS]
    assert delay_edges, "Expected a DELAY_IMPORTS edge"
    assert delay_edges[0].dependency_kind == DependencyKind.STATIC_DEPENDENCY


# ---------------------------------------------------------------------------
# 12. Maximum recursion depth
# ---------------------------------------------------------------------------

def test_max_depth_limits_traversal():
    """MODEL-LEVEL: Traversal stops at max_depth=1; depth-2 nodes are not added."""
    root = _make_root(imports=["level1.dll"])
    resolver = MockResolver({
        "level1.dll": "C:/App/level1.dll",
        "level2.dll": "C:/App/level2.dll",
    })
    pe = MockPEAnalyzer({
        "C:/App/level1.dll": _make_pe_result(
            "C:/App/level1.dll", Architecture.X64, imports=["level2.dll"]
        ),
        "C:/App/level2.dll": _make_pe_result("C:/App/level2.dll", Architecture.X64),
    })
    da = DependencyAnalyzer(
        resolver=resolver,
        pe_analyzer=pe,
        analyze_system_dlls=True,
        max_depth=1,   # recurse only 1 level beyond root
    )
    result = da.analyze(root)

    node_names = {n.name for n in result.nodes}
    # level1.dll is at depth 1 — should be resolved (depth==max_depth is still traversed
    # but its children at depth 2 should be skipped)
    assert "level1.dll" in node_names
    # level2.dll would be at depth 2 — should NOT appear as a node
    assert "level2.dll" not in node_names, (
        "level2.dll at depth 2 should not be traversed when max_depth=1"
    )


# ---------------------------------------------------------------------------
# 13. Malformed dependency (PE analysis fails on a resolved DLL)
# ---------------------------------------------------------------------------

def test_malformed_dependency_dll_is_warned():
    """MODEL-LEVEL: If PE analysis of a resolved DLL fails, a warning is recorded."""
    root = _make_root(imports=["bad.dll"])
    resolver = MockResolver({"bad.dll": "C:/App/bad.dll"})
    pe = MockPEAnalyzer({
        "C:/App/bad.dll": _make_pe_result(
            "C:/App/bad.dll", Architecture.UNKNOWN, complete=False
        )
    })
    # Inject an error into the incomplete result
    pe._map["C:/App/bad.dll"].analyzer_errors.append("Malformed PE file: test error")

    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    assert any("bad.dll" in w for w in result.analyzer_warnings), (
        "Expected a warning about bad.dll PE analysis failure"
    )


# ---------------------------------------------------------------------------
# 14. Duplicate graph nodes prevented
# ---------------------------------------------------------------------------

def test_no_duplicate_node_ids_in_large_graph():
    """MODEL-LEVEL: Multi-diamond import tree produces no duplicate node IDs."""
    # app → [A, B, C]; A → D; B → D; C → D  (D is shared three ways)
    root = _make_root(imports=["A.dll", "B.dll", "C.dll"])
    resolver = MockResolver({
        "a.dll": "C:/App/A.dll",
        "b.dll": "C:/App/B.dll",
        "c.dll": "C:/App/C.dll",
        "d.dll": "C:/App/D.dll",
    })
    pe = MockPEAnalyzer({
        "C:/App/A.dll": _make_pe_result("C:/App/A.dll", Architecture.X64, imports=["D.dll"]),
        "C:/App/B.dll": _make_pe_result("C:/App/B.dll", Architecture.X64, imports=["D.dll"]),
        "C:/App/C.dll": _make_pe_result("C:/App/C.dll", Architecture.X64, imports=["D.dll"]),
        "C:/App/D.dll": _make_pe_result("C:/App/D.dll", Architecture.X64),
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    ids = [n.node_id for n in result.nodes]
    assert len(ids) == len(set(ids)), "Duplicate node IDs found in multi-diamond graph"


# ---------------------------------------------------------------------------
# 15. Provenance preservation
# ---------------------------------------------------------------------------

def test_provenance_on_edges():
    """MODEL-LEVEL: Every non-self edge must carry a non-None provenance."""
    root = _make_root(imports=["foo.dll"], delay_imports=["bar.dll"])
    resolver = MockResolver({
        "foo.dll": "C:/App/foo.dll",
        "bar.dll": "C:/App/bar.dll",
    })
    pe = MockPEAnalyzer({
        "C:/App/foo.dll": _make_pe_result("C:/App/foo.dll", Architecture.X64),
        "C:/App/bar.dll": _make_pe_result("C:/App/bar.dll", Architecture.X64),
    })
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    for edge in result.edges:
        if edge.source_id != edge.target_id:  # skip self-referential RESOLVES_TO
            assert edge.provenance is not None, (
                f"Edge {edge.edge_id} ({edge.edge_kind}) is missing provenance"
            )


def test_architecture_relationship_provenance():
    """MODEL-LEVEL: Every architecture relationship must carry provenance."""
    root = _make_root(arch=Architecture.X64, imports=["dep.dll"])
    resolver = MockResolver({"dep.dll": "C:/App/dep.dll"})
    pe = MockPEAnalyzer({"C:/App/dep.dll": _make_pe_result("C:/App/dep.dll", Architecture.X64)})
    da = DependencyAnalyzer(resolver=resolver, pe_analyzer=pe, analyze_system_dlls=True)
    result = da.analyze(root)

    for rel in result.architecture_relationships:
        assert rel.provenance is not None, (
            f"ArchitectureRelationship {rel.source_id}→{rel.target_id} missing provenance"
        )
        assert rel.provenance.evidence_type == EvidenceType.INFERRED, (
            "Architecture relationships are INFERRED (combination of observed arch values)"
        )


def test_analysis_complete_flag():
    """MODEL-LEVEL: analysis_complete is True when root analysis_complete is True."""
    root = _make_root(imports=[])
    da = DependencyAnalyzer()
    result = da.analyze(root)
    assert result.analysis_complete


def test_incomplete_root_produces_error():
    """If root analysis is incomplete, DependencyAnalysis records an error."""
    root = _make_root()
    root.analysis_complete = False
    da = DependencyAnalyzer()
    result = da.analyze(root)
    assert not result.analysis_complete
    assert result.analyzer_errors
