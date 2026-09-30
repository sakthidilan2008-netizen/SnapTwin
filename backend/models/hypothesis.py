"""
Hypothesis = a candidate explanation for observed failure/degradation,
scoped to the Phase 6 failure taxonomy (F1..F12). This is the unit the
causal engine (Phase 7) updates beliefs over, and what experiments
(Phase 8) target. Kept deliberately evidence-first: a hypothesis without
supporting_evidence is not allowed to claim high confidence — the causal
engine enforces that, not this model, but the shape reflects the rule.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import Provenance, SnapTwinBaseModel


class FailureClass(str, Enum):
    F1_ARCHITECTURE_MISMATCH = "F1_architecture_mismatch"
    F2_MISSING_DLL = "F2_missing_dll"
    F3_WRONG_DLL_ARCHITECTURE = "F3_wrong_dll_architecture"
    F4_ARM64EC_DEPENDENCY_ISSUE = "F4_arm64ec_dependency_issue"
    F5_X64_X86_EMULATION_ISSUE = "F5_x64_x86_emulation_issue"
    F6_CPU_FEATURE_ISSUE = "F6_cpu_feature_issue"
    F7_DRIVER_ISSUE = "F7_driver_issue"
    F8_GRAPHICS_ISSUE = "F8_graphics_issue"
    F9_RUNTIME_LIBRARY_ISSUE = "F9_runtime_library_issue"
    F10_MEMORY_RESOURCE_PRESSURE = "F10_memory_resource_pressure"
    F11_AI_EXECUTION_PROVIDER_FALLBACK = "F11_ai_execution_provider_fallback"
    F12_UPDATE_REGRESSION = "F12_update_regression"


class EvidenceRef(SnapTwinBaseModel):
    """A pointer to a concrete fact elsewhere in the twin, plus its own provenance."""

    description: str
    provenance: Provenance
    points_to: str = Field(description="e.g. 'dependency:graphics.dll' or 'execution:EXEC-003'")


class Hypothesis(SnapTwinBaseModel):
    failure_class: FailureClass
    claim: str = Field(description="Human-readable statement of what this hypothesis asserts.")

    supporting_evidence: list[EvidenceRef] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceRef] = Field(default_factory=list)

    prior: float = Field(ge=0.0, le=1.0, description="Belief before the most recent intervention.")
    confidence: float = Field(ge=0.0, le=1.0, description="Current belief P(H | E) or P(H | E, do(I), O).")

    next_experiment: str | None = Field(
        default=None, description="experiment_id of the recommended discriminating experiment, if any."
    )

    rationale: list[str] = Field(
        default_factory=list,
        description="Ordered, human-readable reasons the confidence is what it is — the 'show WHY' requirement.",
    )

    active: bool = True
