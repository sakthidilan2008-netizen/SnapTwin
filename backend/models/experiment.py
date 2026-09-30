"""
Experiment = a controlled, reversible intervention designed to discriminate
between competing hypotheses. Enforces the Phase 8 safety contract at the
type level: every experiment must declare risk, rollback, and both possible
expected outcomes *before* it runs — a bare intervention with no rollback
plan should fail validation upstream in experiments/safe_interventions.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .common import SnapTwinBaseModel


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"  # requires explicit user confirmation before ExperimentEngine will run it


class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ExperimentConclusion(str, Enum):
    SUPPORTS_TARGET = "supports_target"
    REFUTES_TARGET = "refutes_target"
    INCONCLUSIVE = "inconclusive"


class Experiment(SnapTwinBaseModel):
    target_hypothesis_id: str
    intervention: str = Field(description="Precise description of the documented, reversible change made.")

    risk: RiskLevel
    rollback_method: str = Field(description="Exact steps/command to undo the intervention.")

    expected_if_true: str
    expected_if_false: str

    status: ExperimentStatus = ExperimentStatus.PLANNED

    baseline_execution_id: Optional[str] = None
    intervention_execution_id: Optional[str] = None

    actual_outcome: Optional[str] = None
    evidence_collected: list[str] = Field(default_factory=list)
    conclusion: Optional[ExperimentConclusion] = None
    conclusion_rationale: Optional[str] = None

    requires_user_confirmation: bool = False
    user_confirmed: bool = False

    is_demo_scenario: bool = False
