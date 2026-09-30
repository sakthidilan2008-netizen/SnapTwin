"""
backend/analyzers/dependency_analyzer.py

DependencyAnalyzer – Stage 3 recursive dependency traversal.

Given an ApplicationAnalysis (from Stage 2 PEAnalyzer), this module:

1.  Builds an initial graph node for the root EXE/DLL.
2.  Iterates over its PE-declared imports and delay-imports.
3.  Resolves each DLL name using a DLLResolver.
4.  For each resolved DLL that passes the policy filter, runs PEAnalyzer
    on that DLL to obtain its own imports and architecture.
5.  Recurses depth-first, respecting max_depth and visited-set guards.
6.  Classifies the architecture relationship on every edge using
    ArchitectureCompatibilityAnalyzer.
7.  Returns a DependencyAnalysis with flat node/edge lists.

Key design rules
----------------
- STATIC_DEPENDENCY (PE import table) is labelled as such; it does NOT mean
  the DLL was actually loaded or that it caused any failure.
- System DLLs are recorded as graph nodes but not recursively analysed when
  analyze_system_dlls=False (configurable).
- Circular imports are detected via a visited set and represented as a
  DEPENDS_ON edge back to the already-visited node, with a note.
- max_depth protects against pathologically deep chains.
- The resolver is injectable for testing.
"""

from __future__ import annotations

import uuid
from typing import Optional

from backend.analyzers.arch_compat import ArchitectureCompatibilityAnalyzer
from backend.analyzers.dll_resolver import AbstractDLLResolver, DLLResolver
from backend.analyzers.pe_analyzer import PEAnalyzer
from backend.models.application import ApplicationAnalysis
from backend.models.common import (
    Architecture,
    ArchitectureClassification,
    EvidenceType,
    Provenance,
    SourceMechanism,
    utc_now,
)
from backend.models.graph import (
    DependencyAnalysis,
    DependencyEdge,
    DependencyNode,
    DependencyKind,
    EdgeKind,
    NodeKind,
    ResolutionStatus,
)


def _node_id(path_or_name: str) -> str:
    """Stable, collision-resistant node ID based on normalised path/name."""
    import hashlib
    return hashlib.sha256(path_or_name.lower().encode()).hexdigest()[:16]


def _new_edge(
    source_id: str,
    target_id: str,
    edge_kind: EdgeKind,
    dep_kind: DependencyKind,
    evidence_type: EvidenceType,
    confidence: float,
    notes: Optional[list[str]] = None,
) -> DependencyEdge:
    return DependencyEdge(
        edge_id=str(uuid.uuid4()),
        source_id=source_id,
        target_id=target_id,
        edge_kind=edge_kind,
        dependency_kind=dep_kind,
        evidence_type=evidence_type,
        confidence=confidence,
        provenance=Provenance(
            source=SourceMechanism.PE_STATIC_ANALYSIS,
            evidence_type=evidence_type,
            confidence=confidence,
            detail=f"{edge_kind.value} ({dep_kind.value})",
            timestamp=utc_now(),
        ),
        notes=notes or [],
    )


class DependencyAnalyzer:
    """
    Orchestrates recursive dependency discovery for a single EXE or DLL.

    Parameters
    ----------
    resolver:
        DLL resolver implementation.  Defaults to the Windows-aware
        DLLResolver.  Override in tests with a mock.
    pe_analyzer:
        PEAnalyzer instance.  Defaults to PEAnalyzer().  Override in tests.
    max_depth:
        Maximum recursion depth.  0 = analyse root only (no recursion).
    analyze_system_dlls:
        When False (default), system DLLs are recorded but not recursed.
    extra_search_paths:
        Prepended to the resolver's search order.
    """

    def __init__(
        self,
        resolver: Optional[AbstractDLLResolver] = None,
        pe_analyzer: Optional[PEAnalyzer] = None,
        max_depth: int = 32,
        analyze_system_dlls: bool = False,
        extra_search_paths: Optional[list[str]] = None,
    ) -> None:
        self._resolver = resolver or DLLResolver()
        self._pe = pe_analyzer or PEAnalyzer()
        self._max_depth = max_depth
        self._analyze_system_dlls = analyze_system_dlls
        self._extra_search_paths = extra_search_paths or []
        self._arch_compat = ArchitectureCompatibilityAnalyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, root_analysis: ApplicationAnalysis) -> DependencyAnalysis:
        """
        Build the dependency graph rooted at the already-analysed EXE/DLL.

        Parameters
        ----------
        root_analysis:
            Result of PEAnalyzer().analyze(path).  Must have
            analysis_complete=True for full results (errors are tolerated
            but will produce an incomplete graph).
        """
        dep_analysis = DependencyAnalysis(
            id=str(uuid.uuid4()),
            application_id=root_analysis.identity.id,
            root_path=root_analysis.identity.exe_path,
            config_max_depth=self._max_depth,
            config_analyze_system_dlls=self._analyze_system_dlls,
        )

        if not root_analysis.analysis_complete:
            dep_analysis.analyzer_errors.append(
                "Root ApplicationAnalysis is not complete; dependency graph will be empty."
            )
            return dep_analysis

        # Build the root node
        root_path = root_analysis.identity.exe_path
        root_id = _node_id(root_path)
        root_node = DependencyNode(
            node_id=root_id,
            kind=NodeKind.EXE,
            name=root_analysis.identity.display_name,
            resolved_path=root_path,
            architecture=root_analysis.identity.architecture,
            arch_provenance=root_analysis.identity.architecture_provenance,
            depth=0,
        )
        dep_analysis.nodes.append(root_node)

        visited: set[str] = {root_id}

        self._traverse(
            parent_id=root_id,
            parent_arch=root_analysis.identity.architecture,
            parent_arch_class=self._arch_class(root_analysis),
            parent_path=root_path,
            imports=root_analysis.imports,
            delay_imports=root_analysis.delay_imports,
            depth=0,
            visited=visited,
            dep_analysis=dep_analysis,
        )

        # Populate summary counters
        dep_analysis.total_dependencies = len(dep_analysis.nodes) - 1  # exclude root
        dep_analysis.resolved_count = sum(
            1 for n in dep_analysis.nodes[1:]
            if n.resolution and n.resolution.status == ResolutionStatus.RESOLVED
        )
        dep_analysis.missing_count = sum(
            1 for n in dep_analysis.nodes[1:]
            if n.resolution and n.resolution.status == ResolutionStatus.MISSING
        )
        dep_analysis.skipped_count = sum(
            1 for n in dep_analysis.nodes[1:]
            if n.analysis_skipped
        )
        dep_analysis.analysis_complete = True
        return dep_analysis

    # ------------------------------------------------------------------
    # Recursive traversal
    # ------------------------------------------------------------------

    def _traverse(
        self,
        parent_id: str,
        parent_arch: Architecture,
        parent_arch_class: ArchitectureClassification,
        parent_path: str,
        imports: list[str],
        delay_imports: list[str],
        depth: int,
        visited: set[str],
        dep_analysis: DependencyAnalysis,
    ) -> None:
        next_depth = depth + 1
        dep_analysis.max_depth_reached = max(dep_analysis.max_depth_reached, depth)

        all_imports = [
            (name, EdgeKind.IMPORTS, DependencyKind.STATIC_DEPENDENCY)
            for name in imports
        ] + [
            (name, EdgeKind.DELAY_IMPORTS, DependencyKind.STATIC_DEPENDENCY)
            for name in delay_imports
        ]

        for dll_name, edge_kind, dep_kind in all_imports:
            self._process_import(
                dll_name=dll_name,
                edge_kind=edge_kind,
                dep_kind=dep_kind,
                parent_id=parent_id,
                parent_arch=parent_arch,
                parent_arch_class=parent_arch_class,
                parent_path=parent_path,
                next_depth=next_depth,
                visited=visited,
                dep_analysis=dep_analysis,
            )

    def _process_import(
        self,
        dll_name: str,
        edge_kind: EdgeKind,
        dep_kind: DependencyKind,
        parent_id: str,
        parent_arch: Architecture,
        parent_arch_class: ArchitectureClassification,
        parent_path: str,
        next_depth: int,
        visited: set[str],
        dep_analysis: DependencyAnalysis,
    ) -> None:

        # Resolve the DLL
        resolution = self._resolver.resolve(
            name=dll_name,
            importing_binary_path=parent_path,
            extra_search_paths=self._extra_search_paths,
        )

        # Determine the canonical node key
        if resolution.resolved_path:
            node_key = _node_id(resolution.resolved_path)
        else:
            node_key = _node_id(dll_name)

        # Circular dependency detected
        if node_key in visited:
            # Add a back-edge but do not recurse
            dep_analysis.edges.append(_new_edge(
                source_id=parent_id,
                target_id=node_key,
                edge_kind=EdgeKind.DEPENDS_ON,
                dep_kind=dep_kind,
                evidence_type=EvidenceType.OBSERVED,
                confidence=1.0,
                notes=[f"Circular dependency detected: '{dll_name}' already visited."],
            ))
            return

        # Determine if this is a system DLL that should be skipped for recursion
        is_system = resolution.is_system_dll

        # Build the node
        node = DependencyNode(
            node_id=node_key,
            kind=NodeKind.SYSTEM_COMPONENT if is_system else NodeKind.DLL,
            name=dll_name,
            resolved_path=resolution.resolved_path,
            is_system_dll=is_system,
            resolution=resolution,
            depth=next_depth,
        )
        visited.add(node_key)

        # If resolved and not skipped by policy, PE-analyse the DLL
        child_imports: list[str] = []
        child_delay_imports: list[str] = []
        child_arch = Architecture.UNKNOWN
        child_arch_class = ArchitectureClassification.UNCERTAIN

        should_recurse = (
            resolution.status == ResolutionStatus.RESOLVED
            and (not is_system or self._analyze_system_dlls)
            and next_depth <= self._max_depth
        )

        if resolution.status == ResolutionStatus.RESOLVED:
            if should_recurse:
                child_analysis = self._pe.analyze(resolution.resolved_path)
                if child_analysis.analysis_complete:
                    child_arch = child_analysis.identity.architecture
                    child_arch_class = self._arch_class(child_analysis)
                    child_imports = child_analysis.imports
                    child_delay_imports = child_analysis.delay_imports
                    node.architecture = child_arch
                    node.arch_provenance = child_analysis.identity.architecture_provenance
                else:
                    for err in child_analysis.analyzer_errors:
                        node.notes.append(f"PE analysis error: {err}")
                    dep_analysis.analyzer_warnings.append(
                        f"Could not PE-analyse resolved DLL '{dll_name}': "
                        + "; ".join(child_analysis.analyzer_errors)
                    )
            else:
                node.analysis_skipped = True
                if is_system and not self._analyze_system_dlls:
                    node.notes.append(
                        "System DLL: recorded but not recursively analysed "
                        "(analyze_system_dlls=False)."
                    )
                elif next_depth > self._max_depth:
                    node.notes.append(
                        f"Maximum traversal depth ({self._max_depth}) reached; "
                        "subtree not analysed."
                    )
        else:
            node.notes.append(
                f"Resolution status: {resolution.status.value}. "
                "Architecture is UNKNOWN without the binary."
            )

        dep_analysis.nodes.append(node)

        # Add the import edge
        dep_analysis.edges.append(_new_edge(
            source_id=parent_id,
            target_id=node_key,
            edge_kind=edge_kind,
            dep_kind=dep_kind,
            evidence_type=EvidenceType.OBSERVED,
            confidence=1.0,
        ))

        # Add the RESOLVES_TO edge if we have a path
        if resolution.resolved_path:
            dep_analysis.edges.append(_new_edge(
                source_id=node_key,
                target_id=node_key,   # self-pointing resolution annotation
                edge_kind=EdgeKind.RESOLVES_TO,
                dep_kind=dep_kind,
                evidence_type=EvidenceType.OBSERVED,
                confidence=resolution.provenance.confidence if resolution.provenance else 1.0,
                notes=[f"Resolved to: {resolution.resolved_path}"],
            ))

        # Architecture relationship analysis
        if child_arch != Architecture.UNKNOWN or node.resolution:
            arch_rel = self._arch_compat.analyze(
                source_id=parent_id,
                target_id=node_key,
                source_arch=parent_arch,
                target_arch=child_arch,
                source_classification=parent_arch_class,
                target_classification=child_arch_class,
            )
            dep_analysis.architecture_relationships.append(arch_rel)

        # Recurse if appropriate
        if should_recurse and (child_imports or child_delay_imports) and next_depth < self._max_depth:
            self._traverse(
                parent_id=node_key,
                parent_arch=child_arch,
                parent_arch_class=child_arch_class,
                parent_path=resolution.resolved_path,
                imports=child_imports,
                delay_imports=child_delay_imports,
                depth=next_depth,
                visited=visited,
                dep_analysis=dep_analysis,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _arch_class(analysis: ApplicationAnalysis) -> ArchitectureClassification:
        """Extract ArchitectureClassification from stored Provenance.raw."""
        if analysis.identity.architecture_provenance:
            raw = analysis.identity.architecture_provenance.raw or {}
            cls_str = raw.get("classification", "")
            try:
                return ArchitectureClassification(cls_str)
            except ValueError:
                pass
        return ArchitectureClassification.UNCERTAIN
