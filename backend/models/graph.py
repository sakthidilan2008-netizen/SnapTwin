"""
backend/models/graph.py

Strongly-typed graph models for Stage 3 dependency / execution twin analysis.

Design principles
-----------------
1.  Every relationship carries provenance: evidence_type (OBSERVED / INFERRED /
    UNKNOWN), source mechanism, confidence, and a timestamp.

2.  Architecture relationships are NOT a binary compatible/incompatible flag.
    They express the *relationship category* between two modules (e.g.
    EMULATION_REQUIRED when x64 imports from an ARM64-native DLL under
    Windows-on-ARM).  Severity is a *signal priority* for human review,
    not a crash verdict.

3.  Static PE-import facts are labelled STATIC_DEPENDENCY.  Runtime-loaded
    facts (Stage 4+) will be labelled RUNTIME_LOADED / RUNTIME_EXECUTED.
    The two must never be conflated.

4.  Circular/unresolvable dependencies are represented explicitly as nodes
    with appropriate ResolutionStatus, not silently dropped.

These models are consumed by:
  - DependencyAnalyzer (backend/analyzers/dependency_analyzer.py)
  - ExecutionTwinGraph  (backend/twin/graph.py)
  - FastAPI routes      (backend/api/dependencies.py)
"""

from __future__ import annotations

from enum import Enum
from uuid import uuid4
from typing import Any, Optional

from pydantic import BaseModel, Field

from .common import Architecture, EvidenceType, Provenance, SnapTwinBaseModel, utc_now


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------

class NodeKind(str, Enum):
    APPLICATION   = "APPLICATION"    # the root subject under investigation
    EXE           = "EXE"            # a PE executable
    DLL           = "DLL"            # a PE dynamic-link library
    DRIVER        = "DRIVER"         # a kernel-mode driver (.sys)
    RUNTIME       = "RUNTIME"        # a language / framework runtime (e.g. VCRuntime)
    SYSTEM_COMPONENT = "SYSTEM_COMPONENT"  # OS-provided component (kernel32.dll, etc.)
    UNKNOWN       = "UNKNOWN"


# ---------------------------------------------------------------------------
# Edge / relationship types
# ---------------------------------------------------------------------------

class EdgeKind(str, Enum):
    """The directed relationship between two nodes."""

    # Static, PE-derived
    IMPORTS        = "IMPORTS"         # declared in PE import table
    DELAY_IMPORTS  = "DELAY_IMPORTS"   # declared in delay-import table
    RESOLVES_TO    = "RESOLVES_TO"     # name → disk path (resolver decision)
    DEPENDS_ON     = "DEPENDS_ON"      # generic static dependency

    # Runtime (Stage 4+) — defined here for graph schema completeness;
    # no Stage 3 code emits these.
    LOADS          = "LOADS"           # observed loaded at runtime
    EXECUTES       = "EXECUTES"        # code execution observed


class DependencyKind(str, Enum):
    """Whether this edge came from a static import table or runtime observation."""

    STATIC_DEPENDENCY  = "STATIC_DEPENDENCY"   # PE import table (Stage 3)
    RUNTIME_LOADED     = "RUNTIME_LOADED"      # runtime module list (Stage 4+)
    RUNTIME_EXECUTED   = "RUNTIME_EXECUTED"    # confirmed execution (Stage 5+)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

class ResolutionStatus(str, Enum):
    RESOLVED     = "RESOLVED"      # full disk path found and readable
    MISSING      = "MISSING"       # not found in any search location
    AMBIGUOUS    = "AMBIGUOUS"     # found in more than one location
    INACCESSIBLE = "INACCESSIBLE"  # found but could not be opened / hashed
    UNSUPPORTED  = "UNSUPPORTED"   # found but format not supported for further analysis
    SKIPPED      = "SKIPPED"       # explicitly not analysed (e.g. system DLL policy)


class ResolutionMethod(str, Enum):
    """Which step of the Windows DLL search order located the file."""

    KNOWN_DLL      = "KNOWN_DLL"        # in KnownDLLs registry / system snapshot
    APPLICATION_DIR = "APPLICATION_DIR"  # same directory as the importing binary
    SYSTEM32        = "SYSTEM32"         # %SystemRoot%\System32
    SYSWOW64        = "SYSWOW64"         # %SystemRoot%\SysWOW64
    WINDOWS_DIR     = "WINDOWS_DIR"      # %SystemRoot%
    PATH_ENV        = "PATH_ENV"         # found via PATH environment variable
    EXTRA_SEARCH    = "EXTRA_SEARCH"     # caller-supplied extra_search_paths
    UNKNOWN         = "UNKNOWN"


class DependencyResolution(BaseModel):
    """Resolution result for a single requested DLL name."""

    model_config = {"extra": "forbid"}

    requested_name:   str
    resolved_path:    Optional[str]           = None
    status:           ResolutionStatus        = ResolutionStatus.MISSING
    method:           ResolutionMethod        = ResolutionMethod.UNKNOWN
    is_system_dll:    bool                    = False
    provenance:       Optional[Provenance]    = None
    notes:            list[str]               = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Architecture relationship
# ---------------------------------------------------------------------------

class ArchRelationship(str, Enum):
    """
    How the architectures of two modules relate *statically*.

    NATIVE_MATCH      – both modules share the same architecture; no boundary.
    MIXED_ARCHITECTURE – boundary involves ARM64EC or hybrid binary; both
                         native and emulated code may execute.
    POTENTIAL_CONFLICT – the architectures suggest a load-time or execution-
                         time problem. Requires runtime evidence before
                         claiming failure.
    UNKNOWN           – insufficient architecture metadata on one or both sides.
    """
    NATIVE_MATCH        = "NATIVE_MATCH"
    MIXED_ARCHITECTURE  = "MIXED_ARCHITECTURE"
    POTENTIAL_CONFLICT  = "POTENTIAL_CONFLICT"
    UNKNOWN             = "UNKNOWN"


class RuntimeExecutionStatus(str, Enum):
    NOT_OBSERVED     = "NOT_OBSERVED"
    OBSERVED_NATIVE  = "OBSERVED_NATIVE"
    OBSERVED_EMULATED = "OBSERVED_EMULATED"
    OBSERVED_MIXED   = "OBSERVED_MIXED"
    OBSERVED_FAILURE = "OBSERVED_FAILURE"
    UNKNOWN          = "UNKNOWN"


class RuntimeExecutionMechanism(str, Enum):
    UNKNOWN = "UNKNOWN"
    PRISM   = "PRISM"
    NATIVE  = "NATIVE"
    WOW64   = "WOW64"


class ArchRelationshipSeverity(str, Enum):
    """
    Triage priority for human review — NOT a crash verdict.

    INFO    – noteworthy but expected (e.g. x64 DLL on ARM64 Windows via Prism).
    WARNING – warrants investigation; may surface in hypothesis ranking.
    HIGH    – strong static signal of a problematic boundary; high priority for
              runtime verification.
    """

    INFO    = "INFO"
    WARNING = "WARNING"
    HIGH    = "HIGH"


class ArchitectureRelationship(BaseModel):
    """
    Describes the architecture relationship between two graph nodes.

    Scientific language rule: this record DOES NOT say the application
    crashed or will fail.  It says there is a detectable architecture
    boundary of a particular category.  Failure claims require Stage 4+
    runtime evidence.
    """

    model_config = {"extra": "forbid"}

    source_id:    str               # node id of the importing module
    target_id:    str               # node id of the imported module
    source_arch:  Architecture
    target_arch:  Architecture
    static_relationship: ArchRelationship
    runtime_status: RuntimeExecutionStatus = RuntimeExecutionStatus.NOT_OBSERVED
    runtime_mechanism: RuntimeExecutionMechanism = RuntimeExecutionMechanism.UNKNOWN
    severity:     ArchRelationshipSeverity
    confidence:   float             = Field(ge=0.0, le=1.0)
    reason:       str               = ""
    evidence:     list[dict[str, Any]] = Field(default_factory=list)
    provenance:   Optional[Provenance] = None


# ---------------------------------------------------------------------------
# Graph nodes and edges
# ---------------------------------------------------------------------------

class DependencyNode(BaseModel):
    """A module (EXE, DLL, …) as a vertex in the dependency graph."""

    model_config = {"extra": "forbid"}

    node_id:          str
    kind:             NodeKind
    name:             str                       # basename, e.g. "kernel32.dll"
    resolved_path:    Optional[str]   = None
    architecture:     Architecture    = Architecture.UNKNOWN
    arch_provenance:  Optional[Provenance] = None
    resolution:       Optional[DependencyResolution] = None
    is_system_dll:    bool            = False
    analysis_skipped: bool            = False   # True when policy says don't recurse
    depth:            int             = 0       # traversal depth from root
    notes:            list[str]       = Field(default_factory=list)


class DependencyEdge(BaseModel):
    """A directed relationship between two nodes in the dependency graph."""

    model_config = {"extra": "forbid"}

    edge_id:         str
    source_id:       str
    target_id:       str
    edge_kind:       EdgeKind
    dependency_kind: DependencyKind
    evidence_type:   EvidenceType
    confidence:      float          = Field(ge=0.0, le=1.0)
    provenance:      Optional[Provenance] = None
    notes:           list[str]      = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level analysis container
# ---------------------------------------------------------------------------

class DependencyAnalysis(SnapTwinBaseModel):
    """
    Complete output of DependencyAnalyzer.analyze().

    Contains the flat node/edge lists that represent the dependency graph,
    plus all architecture relationships and any warnings or errors
    encountered during traversal.

    The graph structure itself (for algorithms, rendering) is built from
    these lists by ExecutionTwinGraph (backend/twin/graph.py).
    """

    id: str = Field(default_factory=lambda: f"DEP-{uuid4().hex[:8]}")
    application_id: str
    root_path:      str

    nodes:                    list[DependencyNode]          = Field(default_factory=list)
    edges:                    list[DependencyEdge]          = Field(default_factory=list)
    architecture_relationships: list[ArchitectureRelationship] = Field(default_factory=list)

    # Summary counters
    total_dependencies:  int = 0
    resolved_count:      int = 0
    missing_count:       int = 0
    skipped_count:       int = 0

    # Maximum depth actually reached during traversal
    max_depth_reached:   int = 0

    # Config snapshot (so results are reproducible from the stored object)
    config_max_depth:          int  = 32
    config_analyze_system_dlls: bool = False

    analysis_complete: bool       = False
    analyzer_warnings: list[str]  = Field(default_factory=list)
    analyzer_errors:   list[str]  = Field(default_factory=list)
