"""
Remediation = a recommended fix, plus the mandatory post-fix verification
record. Per Phase 12, a remediation is never marked successful because a
model said so — `VerificationResult` must be produced by re-running the
workload and comparing baseline vs. after_remediation execution records.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .common import SnapTwinBaseModel


class RemediationAction(str, Enum):
    INSTALL_ARM64_VERSION = "install_arm64_version"
    REPLACE_INCOMPATIBLE_DEPENDENCY = "replace_incompatible_dependency"
    UPDATE_DRIVER = "update_driver"
    UPDATE_RUNTIME = "update_runtime"
    USE_ARM64EC_COMPATIBLE_DEPENDENCY = "use_arm64ec_compatible_dependency"
    CHANGE_COMPATIBILITY_SETTING = "change_compatibility_setting"
    USE_COMPATIBLE_APPLICATION_VERSION = "use_compatible_application_version"
    INVESTIGATE_GRAPHICS_PATH = "investigate_graphics_path"
    INVESTIGATE_AI_EXECUTION_PROVIDER = "investigate_ai_execution_provider"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    NOT_VERIFIED = "not_verified"
    INCONCLUSIVE = "inconclusive"


class RemediationRecommendation(SnapTwinBaseModel):
    hypothesis_id: str
    action: RemediationAction
    reason: str
    evidence: list[str] = Field(default_factory=list)
    risk: str
    verification_method: str


class VerificationMetricDelta(SnapTwinBaseModel):
    metric: str
    baseline_value: Optional[str] = None
    after_value: Optional[str] = None
    improved: Optional[bool] = None


class VerificationResult(SnapTwinBaseModel):
    remediation_id: str
    baseline_execution_id: str
    after_execution_id: str

    status: VerificationStatus
    metric_deltas: list[VerificationMetricDelta] = Field(default_factory=list)
    summary: str
