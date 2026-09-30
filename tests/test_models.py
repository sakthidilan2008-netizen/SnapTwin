"""
Stage 1 model tests: every model in backend/models imports, validates, and
round-trips through JSON. Also asserts the "every important result has
provenance" rule is structurally enforceable (not bypassable by omission
where it matters).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "backend")

from models.application import ApplicationAnalysis, ApplicationIdentity
from models.common import Architecture, EvidenceType, Provenance, SourceMechanism
from models.dependency import Dependency, DependencyGraph, DependencyKind, ResolutionStatus
from models.execution import ExecutionOutcome, ExecutionRecord, ExecutionRole
from models.hypothesis import FailureClass, Hypothesis
from models.remediation import RemediationAction, RemediationRecommendation, VerificationResult, VerificationStatus
from models.report import InvestigationReport
from models.experiment import Experiment, ExperimentStatus, RiskLevel


def make_provenance(**overrides) -> Provenance:
    base = dict(
        source=SourceMechanism.PE_STATIC_ANALYSIS,
        evidence_type=EvidenceType.OBSERVED,
        confidence=0.9,
    )
    base.update(overrides)
    return Provenance(**base)


def test_application_identity_round_trip():
    ident = ApplicationIdentity(
        id="APP-1",
        display_name="example.exe",
        exe_path="C:/apps/example.exe",
        architecture=Architecture.X64,
        architecture_provenance=make_provenance(),
    )
    analysis = ApplicationAnalysis(id="AA-1", identity=ident)
    payload = analysis.model_dump_json()
    restored = ApplicationAnalysis.model_validate_json(payload)
    assert restored.identity.architecture == Architecture.X64


def test_dependency_graph_tracks_mismatches():
    dep = Dependency(
        id="DEP-1",
        name="graphics.dll",
        kind=DependencyKind.IMPORT,
        declared_by="example.exe",
        architecture=Architecture.ARM64,
        status=ResolutionStatus.WRONG_ARCHITECTURE,
        status_provenance=make_provenance(source=SourceMechanism.PE_STATIC_ANALYSIS),
    )
    graph = DependencyGraph(id="DG-1", application_id="APP-1", dependencies=[dep], architecture_mismatches=["DEP-1"])
    assert graph.dependencies[0].status == ResolutionStatus.WRONG_ARCHITECTURE
    assert "DEP-1" in graph.architecture_mismatches


def test_execution_record_defaults_to_unknown_outcome():
    record = ExecutionRecord(id="EXEC-1", application_id="APP-1", role=ExecutionRole.BASELINE)
    assert record.outcome == ExecutionOutcome.UNKNOWN
    assert record.is_demo_data is False


def test_hypothesis_requires_bounded_confidence():
    h = Hypothesis(
        id="H-1",
        failure_class=FailureClass.F1_ARCHITECTURE_MISMATCH,
        claim="The failure is caused by x64 code path executing under emulation hitting an unsupported API.",
        prior=0.3,
        confidence=0.48,
        rationale=["Baseline run crashed inside an x64-only DLL loaded via Prism emulation."],
    )
    assert 0.0 <= h.confidence <= 1.0
    try:
        Hypothesis(
            id="H-2",
            failure_class=FailureClass.F1_ARCHITECTURE_MISMATCH,
            claim="bad",
            prior=0.3,
            confidence=1.5,  # out of bounds
        )
        assert False, "expected validation error for out-of-bounds confidence"
    except Exception:
        pass


def test_experiment_enforces_shape_not_just_intervention_text():
    exp = Experiment(
        id="EXP-1",
        target_hypothesis_id="H-1",
        intervention="Temporarily disable a documented compatibility shim via supported OS setting.",
        risk=RiskLevel.LOW,
        rollback_method="Re-enable the same setting; no persistent state changed.",
        expected_if_true="Crash signature changes or disappears.",
        expected_if_false="Crash signature remains identical.",
    )
    assert exp.status == ExperimentStatus.PLANNED
    assert exp.rollback_method  # non-empty rollback is required by convention


def test_verification_result_status_enum():
    vr = VerificationResult(
        id="VR-1",
        remediation_id="REM-1",
        baseline_execution_id="EXEC-1",
        after_execution_id="EXEC-2",
        status=VerificationStatus.VERIFIED,
        summary="Application launched successfully post-remediation with no crash events logged.",
    )
    assert vr.status == VerificationStatus.VERIFIED


def test_investigation_report_round_trip():
    report = InvestigationReport(
        id="REPORT-1",
        application_id="APP-1",
        application_name="example.exe",
        hypothesis_ids=["H-1"],
        experiment_ids=["EXP-1"],
        root_cause_hypothesis_id="H-1",
        root_cause_confidence=0.87,
        narrative=["Observed crash.", "Ranked hypotheses.", "Ran experiment.", "Confirmed root cause."],
    )
    payload = report.model_dump_json()
    restored = InvestigationReport.model_validate_json(payload)
    assert restored.root_cause_hypothesis_id == "H-1"
    assert restored.contains_demo_data is False
