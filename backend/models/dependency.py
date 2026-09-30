"""
Dependency-level facts: imported/delay-loaded DLLs and what we can determine
about each one (found vs missing, its own architecture, and whether that
architecture matches the host/process). This is deliberately separate from
twin/graph.py — this module is *data about dependencies*, the twin module is
the *graph structure* (nodes/edges) built from this data plus other sources.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .common import Architecture, Provenance, SnapTwinBaseModel


class DependencyKind(str, Enum):
    IMPORT = "import"
    DELAY_IMPORT = "delay_import"
    RUNTIME_LOADED = "runtime_loaded"  # observed via process/module enumeration, not static imports


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    WRONG_ARCHITECTURE = "wrong_architecture"
    UNKNOWN = "unknown"


class Dependency(SnapTwinBaseModel):
    name: str = Field(description="e.g. 'd3d12.dll'")
    kind: DependencyKind
    declared_by: str = Field(description="The module that imports this, e.g. the main EXE or another DLL.")

    resolved_path: Optional[str] = None
    architecture: Architecture = Architecture.UNKNOWN
    architecture_provenance: Optional[Provenance] = None

    status: ResolutionStatus = ResolutionStatus.UNKNOWN
    status_provenance: Optional[Provenance] = None

    is_system_dll: Optional[bool] = None
    notes: list[str] = Field(default_factory=list)


class DependencyGraph(SnapTwinBaseModel):
    application_id: str
    dependencies: list[Dependency] = Field(default_factory=list)
    unresolved_count: int = 0
    architecture_mismatches: list[str] = Field(
        default_factory=list, description="Dependency ids flagged as ARCH mismatch vs host/process."
    )
