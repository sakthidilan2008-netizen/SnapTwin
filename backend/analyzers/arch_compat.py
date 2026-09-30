"""
backend/analyzers/arch_compat.py

ArchitectureCompatibilityAnalyzer

Classifies the *architecture relationship* between two modules within the
Windows execution model.  This is deliberately NOT a boolean pass/fail check.

Key principle (from the SnapTwin research contract):

  An architecture difference is not automatically a failure.

  x64 EXE → x64 DLL → ARM64 Windows emulation  may be entirely valid.
  ARM64EC EXE → ARM64 DLL                        may be valid (hybrid bridge).
  x64 EXE → ARM64-only DLL (no EC shim)          is a POTENTIAL_CONFLICT
                                                  requiring runtime confirmation.

The analyzer returns an ArchitectureRelationship with:
  - relationship  (NATIVE_MATCH / EMULATION_REQUIRED / MIXED_ARCHITECTURE /
                   POTENTIAL_CONFLICT / UNKNOWN)
  - severity      (INFO / WARNING / HIGH) — triage priority, not a verdict
  - confidence    — how sure we are given available static metadata
  - reason        — human-readable scientific language
  - evidence      — list of evidence items

Callers must not promote a POTENTIAL_CONFLICT to "incompatible" without
additional runtime evidence (Stage 4+).
"""

from __future__ import annotations

from typing import Any

from backend.models.common import (
    Architecture,
    ArchitectureClassification,
    EvidenceType,
    Provenance,
    SourceMechanism,
    utc_now,
)
from backend.models.graph import (
    ArchitectureRelationship,
    ArchRelationship,
    ArchRelationshipSeverity,
)


def _ev(label: str, detail: str) -> dict[str, Any]:
    return {
        "label": label,
        "detail": detail,
        "evidence_type": EvidenceType.OBSERVED.value,
    }


def _inferred_ev(label: str, detail: str) -> dict[str, Any]:
    return {
        "label": label,
        "detail": detail,
        "evidence_type": EvidenceType.INFERRED.value,
    }


class ArchitectureCompatibilityAnalyzer:
    """
    Classifies the architecture boundary between a source (importing) module
    and a target (imported) module.

    Parameters
    ----------
    source_id, target_id:
        Graph node IDs (for the returned relationship record).
    source_arch, target_arch:
        Architecture enum values for the two modules.
    source_classification, target_classification:
        How firmly each architecture was established (DETECTED / INFERRED /
        UNCERTAIN).  Used to calibrate confidence.
    """

    def analyze(
        self,
        source_id: str,
        target_id: str,
        source_arch: Architecture,
        target_arch: Architecture,
        source_classification: ArchitectureClassification = ArchitectureClassification.DETECTED,
        target_classification: ArchitectureClassification = ArchitectureClassification.DETECTED,
    ) -> ArchitectureRelationship:

        evidence: list[dict[str, Any]] = [
            _ev("source_architecture", f"{source_arch.value} ({source_classification.value})"),
            _ev("target_architecture", f"{target_arch.value} ({target_classification.value})"),
        ]

        # Base confidence: reduce if either side was UNCERTAIN/INFERRED
        base_conf = 1.0
        if source_classification == ArchitectureClassification.UNCERTAIN:
            base_conf -= 0.25
            evidence.append(_inferred_ev(
                "source_arch_uncertain",
                "Source architecture is UNCERTAIN; relationship may differ with better metadata."
            ))
        elif source_classification == ArchitectureClassification.INFERRED:
            base_conf -= 0.10

        if target_classification == ArchitectureClassification.UNCERTAIN:
            base_conf -= 0.25
            evidence.append(_inferred_ev(
                "target_arch_uncertain",
                "Target architecture is UNCERTAIN; relationship may differ with better metadata."
            ))
        elif target_classification == ArchitectureClassification.INFERRED:
            base_conf -= 0.10

        base_conf = max(0.0, base_conf)

        rel, sev, reason, conf = self._classify(
            source_arch, target_arch, base_conf, evidence
        )

        return ArchitectureRelationship(
            source_id=source_id,
            target_id=target_id,
            source_arch=source_arch,
            target_arch=target_arch,
            static_relationship=rel,
            severity=sev,
            confidence=conf,
            reason=reason,
            evidence=evidence,
            provenance=Provenance(
                source=SourceMechanism.PE_STATIC_ANALYSIS,
                evidence_type=EvidenceType.INFERRED,
                confidence=conf,
                detail=f"{source_arch.value} → {target_arch.value}: {rel.value}",
                timestamp=utc_now(),
            ),
        )

    # ------------------------------------------------------------------
    # Core classification table
    # ------------------------------------------------------------------

    def _classify(
        self,
        src: Architecture,
        tgt: Architecture,
        base_conf: float,
        evidence: list[dict[str, Any]],
    ) -> tuple[ArchRelationship, ArchRelationshipSeverity, str, float]:
        """
        Return (relationship, severity, reason, confidence).

        Rules are documented inline with the Windows execution model in mind.
        This is intentionally verbose so that the reasoning is auditable.
        """

        # Both UNKNOWN → nothing to say
        if src == Architecture.UNKNOWN and tgt == Architecture.UNKNOWN:
            return (
                ArchRelationship.UNKNOWN,
                ArchRelationshipSeverity.WARNING,
                "Architecture is unknown for both modules; relationship cannot be determined.",
                max(0.0, base_conf * 0.5),
            )

        # Either side UNKNOWN → limited confidence
        if src == Architecture.UNKNOWN or tgt == Architecture.UNKNOWN:
            evidence.append(_inferred_ev(
                "one_side_unknown",
                "One module's architecture is unknown; relationship is uncertain.",
            ))
            return (
                ArchRelationship.UNKNOWN,
                ArchRelationshipSeverity.WARNING,
                "Architecture of one module is unknown; relationship cannot be confidently classified.",
                max(0.0, base_conf * 0.6),
            )

        # Exact match — native execution, no boundary
        if src == tgt:
            return (
                ArchRelationship.NATIVE_MATCH,
                ArchRelationshipSeverity.INFO,
                f"Both modules share architecture {src.value}; no architecture boundary detected.",
                base_conf,
            )

        # ARM64EC source — hybrid by design; can call x64 and ARM64
        if src == Architecture.ARM64EC:
            if tgt == Architecture.ARM64:
                return (
                    ArchRelationship.MIXED_ARCHITECTURE,
                    ArchRelationshipSeverity.INFO,
                    "ARM64EC binary importing ARM64 DLL: mixed-architecture execution via "
                    "ARM64EC-to-ARM64 bridge.  This is a supported Windows hybrid pattern; "
                    "no failure is implied by static analysis alone.",
                    base_conf * 0.90,
                )
            if tgt == Architecture.X64:
                return (
                    ArchRelationship.MIXED_ARCHITECTURE,
                    ArchRelationshipSeverity.INFO,
                    "ARM64EC binary importing x64 DLL: both run under the ARM64EC execution "
                    "model.  This is a supported Windows hybrid pattern.",
                    base_conf * 0.90,
                )
            if tgt == Architecture.X86:
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.WARNING,
                    "ARM64EC binary importing x86 DLL: x86-on-ARM64 is supported via SysWOW64 "
                    "emulation, but the direct import path from ARM64EC to x86 is unusual. "
                    "Runtime verification is recommended.",
                    base_conf * 0.70,
                )

        # x64 source
        if src == Architecture.X64:
            if tgt == Architecture.X86:
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.WARNING,
                    "x64 process importing x86 DLL: 64-bit processes cannot directly load "
                    "32-bit DLLs.  This is likely MISSING_DLL or a 64-bit sibling should be "
                    "expected.  Runtime verification required.",
                    base_conf * 0.85,
                )
            if tgt == Architecture.ARM64:
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.HIGH,
                    "Static architecture relationship may require runtime investigation.",
                    base_conf * 0.80,
                )
            if tgt == Architecture.ARM64EC:
                return (
                    ArchRelationship.MIXED_ARCHITECTURE,
                    ArchRelationshipSeverity.INFO,
                    "Static analysis identifies an x64/ARM64EC architecture boundary. Runtime execution mechanism has not yet been observed.",
                    base_conf * 0.85,
                )

        # x86 source
        if src == Architecture.X86:
            if tgt == Architecture.X64:
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.WARNING,
                    "x86 process importing x64 DLL: 32-bit processes cannot directly load "
                    "64-bit DLLs.  Runtime verification required.",
                    base_conf * 0.85,
                )
            if tgt in (Architecture.ARM64, Architecture.ARM64EC):
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.HIGH,
                    f"x86 process importing {tgt.value} DLL: 32-bit SysWOW64 processes cannot "
                    "directly load ARM64 or ARM64EC DLLs.  Candidate architecture conflict.",
                    base_conf * 0.85,
                )
            # x86 → x86: already handled above (exact match)

        # ARM64 source (pure native, not ARM64EC)
        if src == Architecture.ARM64:
            if tgt == Architecture.ARM64EC:
                return (
                    ArchRelationship.MIXED_ARCHITECTURE,
                    ArchRelationshipSeverity.INFO,
                    "ARM64 binary importing ARM64EC DLL: ARM64EC DLLs export ARM64-compatible "
                    "entry points.  This is a supported hybrid pattern on Windows.",
                    base_conf * 0.85,
                )
            if tgt == Architecture.X64:
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.WARNING,
                    "Static architecture relationship may require runtime investigation.",
                    base_conf * 0.75,
                )
            if tgt == Architecture.X86:
                return (
                    ArchRelationship.POTENTIAL_CONFLICT,
                    ArchRelationshipSeverity.HIGH,
                    "ARM64 process importing x86 DLL: ARM64 processes do not run x86 code "
                    "directly.  Candidate architecture conflict.",
                    base_conf * 0.85,
                )

        # Fallback — should not be reached for known architecture combinations
        return (
            ArchRelationship.UNKNOWN,
            ArchRelationshipSeverity.WARNING,
            f"Unhandled architecture combination: {src.value} → {tgt.value}.",
            max(0.0, base_conf * 0.5),
        )
