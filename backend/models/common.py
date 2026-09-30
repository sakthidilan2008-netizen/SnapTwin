"""
Shared primitives used across every SnapTwin model.

Design rule (per project constitution): every important result must carry
provenance — where it came from, when, how confident we are, and whether it
was *observed* directly or *inferred*. This module defines that vocabulary
once so every other model reuses it instead of re-inventing ad hoc fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceType(str, Enum):
    """Was this fact directly observed, or inferred from other facts?"""

    OBSERVED = "observed"
    INFERRED = "inferred"
    SIMULATED = "simulated"  # controlled demo data — never real OS evidence
    UNAVAILABLE = "unavailable"  # mechanism exists but could not be reached


class SourceMechanism(str, Enum):
    """The concrete Windows/OS mechanism (or lack thereof) behind a fact."""

    PE_STATIC_ANALYSIS = "pe_static_analysis"
    WINDOWS_EVENT_LOG = "windows_event_log"
    WER = "windows_error_reporting"
    ETW = "etw"
    PROCESS_INFO = "process_info"
    SYSTEM_INFO = "system_info"
    REGISTRY = "registry"
    GRAPHICS_RUNTIME = "graphics_runtime"
    AI_RUNTIME = "ai_execution_provider"
    CONTROLLED_EXPERIMENT = "controlled_experiment"
    DEMO_SCENARIO = "demo_scenario"
    LLM_INFERENCE = "llm_inference"
    HEURISTIC = "heuristic"
    PLATFORM_UNAVAILABLE = "platform_unavailable"


class Provenance(BaseModel):
    """Attach this to any fact/claim/edge that matters."""

    source: SourceMechanism
    evidence_type: EvidenceType
    timestamp: datetime = Field(default_factory=utc_now)
    confidence: float = Field(
        ge=0.0, le=1.0, description="Calibrated confidence in this specific fact, not a hypothesis score."
    )
    detail: Optional[str] = Field(
        default=None, description="Human-readable note on how this was derived, e.g. which API/log query."
    )
    raw: Optional[dict[str, Any]] = Field(
        default=None, description="Optional raw evidence payload for auditability."
    )


class Architecture(str, Enum):
    ARM64 = "ARM64"
    ARM64EC = "ARM64EC"
    X64 = "x64"
    X86 = "x86"
    UNKNOWN = "unknown"


class ArchitectureClassification(str, Enum):
    """How firmly did we establish the architecture claim?

    DETECTED  – read directly from a single authoritative PE header field
                with no inference chain.  Confidence == 1.0 is appropriate.
    INFERRED  – derived from a combination of fields (e.g. CHPEMetadataPointer
                on top of a AMD64 Machine field).  Confidence < 1.0.
    UNCERTAIN – the available metadata is insufficient or contradictory;
                the returned Architecture value is the safest guess and must
                be treated as provisional.  Consumers MUST surface the warnings.
    """

    DETECTED = "DETECTED"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"


class ArchitectureEvidenceItem(BaseModel):
    """One atomic piece of PE evidence that contributed to the architecture result."""

    model_config = {"extra": "forbid"}

    source: str = Field(description="Which PE structure this came from, e.g. 'COFF_FILE_HEADER'.")
    field: str = Field(description="The specific header field name, e.g. 'Machine'.")
    value: str = Field(description="The human-readable value observed, e.g. 'IMAGE_FILE_MACHINE_AMD64'.")
    evidence_type: EvidenceType = EvidenceType.OBSERVED


class ArchitectureResult(BaseModel):
    """Structured output from architecture_detector.detect_architecture()."""

    model_config = {"extra": "forbid"}

    architecture: Architecture
    classification: ArchitectureClassification
    evidence: list[ArchitectureEvidenceItem] = Field(default_factory=list)
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Calibrated confidence in the architecture claim."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable caveats; non-empty whenever classification != DETECTED."
    )


class SnapTwinBaseModel(BaseModel):
    """Base class giving every top-level model a stable id and creation time."""

    id: str
    created_at: datetime = Field(default_factory=utc_now)

    model_config = {"extra": "forbid"}
