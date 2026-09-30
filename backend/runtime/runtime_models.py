"""
backend/runtime/runtime_models.py

Typed models for Stage 4: RUNTIME OBSERVATION ENGINE.

Includes the event model, execution state, and static/runtime join results.
No causal claims are encoded in these models.
"""
from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator

from backend.models.common import EvidenceType, Architecture, SnapTwinBaseModel, utc_now
from backend.models.telemetry import SystemSnapshot


class TerminationReason(str, Enum):
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    TERMINATED = "TERMINATED"
    CRASHED = "CRASHED"
    UNAVAILABLE = "UNAVAILABLE"


class RuntimeExecution(BaseModel):
    """Controlled process execution state."""
    run_id: str
    process_id: Optional[int] = None
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    exit_code: Optional[int] = None
    termination_reason: TerminationReason = TerminationReason.UNAVAILABLE
    timed_out: bool = False
    success: bool = False
    working_directory: str
    arguments: list[str] = Field(default_factory=list)


class RuntimeModule(BaseModel):
    """A module loaded by the target process at runtime."""
    name: str
    absolute_path: Optional[str] = None
    load_status: str = "LOADED"
    timestamp: Optional[datetime.datetime] = None
    architecture: Architecture = Architecture.UNKNOWN


class EventType(str, Enum):
    PROCESS_STARTED = "PROCESS_STARTED"
    PROCESS_EXITED = "PROCESS_EXITED"
    MODULE_LOADED = "MODULE_LOADED"
    MODULE_UNAVAILABLE = "MODULE_UNAVAILABLE"
    CRASH_OBSERVED = "CRASH_OBSERVED"
    SYSTEM_SNAPSHOT = "SYSTEM_SNAPSHOT"
    TIMEOUT = "TIMEOUT"
    OBSERVATION_UNAVAILABLE = "OBSERVATION_UNAVAILABLE"


class RuntimeEvent(BaseModel):
    """A typed runtime event."""
    event_id: str
    timestamp: datetime.datetime = Field(default_factory=utc_now)
    event_type: EventType
    source: str
    evidence_type: EvidenceType
    confidence: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("evidence_type")
    def serialize_evidence_type(self, value: EvidenceType) -> str:
        """Keep the Stage 4 wire format compatible with existing consumers."""
        return value.name

    @field_validator("evidence_type", mode="before")
    @classmethod
    def accept_evidence_type_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return EvidenceType[value]
            except KeyError:
                pass
        return value


class JoinResult(str, Enum):
    STATIC_AND_RUNTIME_CONFIRMED = "STATIC_AND_RUNTIME_CONFIRMED"
    STATIC_ONLY = "STATIC_ONLY"
    RUNTIME_ONLY = "RUNTIME_ONLY"
    UNRESOLVED = "UNRESOLVED"


class StaticRuntimeJoinNode(BaseModel):
    """
    Intersection of Stage 3 dependency graph and Stage 4 module observations.
    Never claims causality.
    """
    module_name: str
    static_path: Optional[str] = None
    runtime_path: Optional[str] = None
    join_result: JoinResult
    notes: list[str] = Field(default_factory=list)


class RuntimeObservationReport(SnapTwinBaseModel):
    """
    Complete output of Stage 4.
    """
    run_id: str
    execution: RuntimeExecution
    events: list[RuntimeEvent] = Field(default_factory=list)
    modules: list[RuntimeModule] = Field(default_factory=list)
    system_snapshot: Optional[SystemSnapshot] = None
    joins: list[StaticRuntimeJoinNode] = Field(default_factory=list)
