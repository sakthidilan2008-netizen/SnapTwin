"""
Represents the application under investigation: what it is, where it lives
on disk, and the top-level facts PEAnalyzer will fill in during Phase 2.
This model intentionally does NOT contain dependency or runtime data —
those live in dependency.py and execution.py / telemetry.py respectively,
so each model stays focused and serializable on its own.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import Architecture, Provenance, SnapTwinBaseModel


class ApplicationIdentity(SnapTwinBaseModel):
    """Static identity of the application, established before any execution."""

    display_name: str
    exe_path: str
    exe_sha256: Optional[str] = Field(
        default=None, description="Hash computed at analysis time for reproducibility/audit."
    )
    file_size_bytes: Optional[int] = None
    architecture: Architecture = Architecture.UNKNOWN
    architecture_provenance: Optional[Provenance] = None

    subsystem: Optional[str] = None
    machine_type_raw: Optional[str] = Field(
        default=None, description="Raw PE machine type field, e.g. 'IMAGE_FILE_MACHINE_ARM64'."
    )
    pe_timestamp: Optional[str] = Field(
        default=None, description="PE header build timestamp, if present and not zeroed."
    )
    manifest_present: bool = False
    manifest_summary: Optional[str] = None

    is_signed: Optional[bool] = Field(
        default=None, description="Authenticode signature presence, where checkable."
    )

    notes: list[str] = Field(default_factory=list)


class ApplicationAnalysis(SnapTwinBaseModel):
    """
    Aggregate container produced at the end of Phase 2/3 static analysis,
    consumed as input to TwinBuilder (Phase 5) alongside SystemSnapshot and
    RuntimeTelemetry.
    """

    identity: ApplicationIdentity
    analysis_complete: bool = False
    analyzer_warnings: list[str] = Field(default_factory=list)
    analyzer_errors: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    delay_imports: list[str] = Field(default_factory=list)
