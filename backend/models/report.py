"""
InvestigationReport = the final artifact that ties an entire OBSERVE ->
HYPOTHESIZE -> INTERVENE -> EXECUTE -> MEASURE -> LOCALIZE -> REMEDIATE ->
VERIFY -> LEARN loop together for one application investigation. This is
what api/reports.py serializes and what the frontend's Report.tsx renders.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import SnapTwinBaseModel
from .remediation import RemediationRecommendation, VerificationResult


class InvestigationReport(SnapTwinBaseModel):
    application_id: str
    application_name: str

    system_snapshot_id: Optional[str] = None

    hypothesis_ids: list[str] = Field(default_factory=list)
    experiment_ids: list[str] = Field(default_factory=list)

    root_cause_hypothesis_id: Optional[str] = None
    root_cause_confidence: Optional[float] = None
    root_cause_summary: Optional[str] = None

    remediation: Optional[RemediationRecommendation] = None
    verification: Optional[VerificationResult] = None

    narrative: list[str] = Field(
        default_factory=list,
        description="Ordered plain-language account of the investigation, suitable for the LLM to expand on "
        "but generated primarily from structured state, not free generation.",
    )

    contains_demo_data: bool = Field(
        default=False, description="True if any part of this report used controlled demo/simulated data."
    )
