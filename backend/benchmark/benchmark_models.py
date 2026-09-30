from __future__ import annotations

import statistics
from enum import Enum
from typing import Optional
from pydantic import Field
from backend.models.common import Provenance, SnapTwinBaseModel
from backend.models.execution_profile import ExecutionProfile
from backend.models.telemetry import SystemSnapshot


class RunOrder(str, Enum):
    ALTERNATING = "alternating"
    CONTROL_THEN_TREATMENT = "control_then_treatment"


class RunValidity(str, Enum):
    VALID = "VALID"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class BenchmarkConfig(SnapTwinBaseModel):
    workload: str
    arguments: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    working_directory: Optional[str] = None
    timeout_seconds: int = 30
    warmup_runs: int = 0
    measured_runs: int = 1
    run_order: RunOrder = RunOrder.ALTERNATING


class BenchmarkRun(SnapTwinBaseModel):
    benchmark_id: str
    configuration_id: str
    sequence_number: int
    architecture: Optional[str] = None
    execution_profile: ExecutionProfile
    system_snapshot: Optional[SystemSnapshot] = None
    validity: RunValidity
    success: bool
    failure_reason: Optional[str] = None
    provenance: list[Provenance] = Field(default_factory=list)


class NumericSummary(SnapTwinBaseModel):
    count: int
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    median: Optional[float] = None
    mean: Optional[float] = None
    standard_deviation: Optional[float] = None

    @classmethod
    def from_values(cls, values: list[float]) -> "NumericSummary":
        return cls(
            id="SUMMARY",
            count=len(values),
            minimum=min(values) if values else None,
            maximum=max(values) if values else None,
            median=statistics.median(values) if values else None,
            mean=statistics.mean(values) if values else None,
            standard_deviation=statistics.stdev(values) if len(values) > 1 else None,
        )


class BenchmarkSummary(SnapTwinBaseModel):
    total_runs: int
    valid_runs: int
    excluded_runs: int
    exclusions: dict[str, int] = Field(default_factory=dict)
    wall_time_seconds: NumericSummary
    cpu_time_seconds: NumericSummary
    peak_working_set_bytes: NumericSummary


class BenchmarkResult(SnapTwinBaseModel):
    configuration: BenchmarkConfig
    runs: list[BenchmarkRun] = Field(default_factory=list)
    summary: Optional[BenchmarkSummary] = None
    system_context: Optional[SystemSnapshot] = None
    provenance: list[Provenance] = Field(default_factory=list)
