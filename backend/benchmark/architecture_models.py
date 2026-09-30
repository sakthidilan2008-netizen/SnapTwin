from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import Field
from backend.models.common import Architecture, Provenance, SnapTwinBaseModel


class BuildStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    BUILT = "BUILT"
    NOT_TESTED = "NOT_TESTED"


class CorrectnessStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class BuildArtifact(SnapTwinBaseModel):
    workload: str
    target: Architecture
    compiler: Optional[str] = None
    linker: Optional[str] = None
    sdk: Optional[str] = None
    command: list[str] = Field(default_factory=list)
    status: BuildStatus
    executable_path: Optional[str] = None
    detected_architecture: Optional[Architecture] = None
    correctness_status: CorrectnessStatus = CorrectnessStatus.UNAVAILABLE
    expected_output: Optional[str] = None
    observed_output: Optional[str] = None
    provenance: list[Provenance] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ArchitectureComparison(SnapTwinBaseModel):
    workload: str
    baseline_configuration: str
    treatment_configuration: str
    baseline_runs: list[str] = Field(default_factory=list)
    treatment_runs: list[str] = Field(default_factory=list)
    baseline_median: Optional[float] = None
    treatment_median: Optional[float] = None
    absolute_difference: Optional[float] = None
    relative_difference_percent: Optional[float] = None
    correctness_status: CorrectnessStatus = CorrectnessStatus.UNAVAILABLE
    metric_name: str = "wall_time_seconds"
    provenance: list[Provenance] = Field(default_factory=list)
