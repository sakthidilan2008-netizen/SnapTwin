"""
Runtime/system telemetry snapshot — the output of the collectors/ package
(system_collector, process_collector, eventlog_collector, wer_collector,
etw_collector, runtime_collector). Kept separate from execution.py: an
ExecutionRecord is "what happened when we ran the app"; a RuntimeTelemetry
snapshot is "what the OS/host looked like", which may be collected even
without running the target app (e.g. plain SystemCollector.collect()).
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import Provenance, SnapTwinBaseModel

# Keep legacy ``models.telemetry`` imports and canonical ``backend.models``
# imports pointed at the same module object when both package paths exist.
import sys
sys.modules.setdefault("models.telemetry", sys.modules[__name__])


class OSInfo(SnapTwinBaseModel):
    name: str
    version: str
    build: Optional[str] = None
    architecture: str  # ARM64 / x64 / x86 / unknown — host OS architecture


class CPUInfo(SnapTwinBaseModel):
    architecture: str
    model: Optional[str] = None
    logical_cores: Optional[int] = None
    physical_cores: Optional[int] = None
    is_snapdragon: Optional[bool] = Field(
        default=None, description="True/False when determinable from CPU model string; never hardcoded."
    )


class GPUInfo(SnapTwinBaseModel):
    vendor: Optional[str] = None
    name: Optional[str] = None
    driver_version: Optional[str] = None


class NPUInfo(SnapTwinBaseModel):
    available: Optional[bool] = None
    provider: Optional[str] = None
    detection_method: Optional[str] = None


class MemoryInfo(SnapTwinBaseModel):
    total_bytes: Optional[int] = None
    available_bytes: Optional[int] = None


class EventLogEntry(SnapTwinBaseModel):
    channel: str
    level: str
    source: str
    event_id: Optional[int] = None
    message: Optional[str] = None
    timestamp: Optional[str] = None


class WERReport(SnapTwinBaseModel):
    application: str
    fault_module: Optional[str] = None
    exception_code: Optional[str] = None
    report_id: Optional[str] = None


class SystemSnapshot(SnapTwinBaseModel):
    os: OSInfo
    cpu: CPUInfo
    gpu: Optional[GPUInfo] = None
    npu: Optional[NPUInfo] = None
    memory: Optional[MemoryInfo] = None
    collected_via: Provenance
    collector_warnings: list[str] = Field(default_factory=list)


class RuntimeTelemetry(SnapTwinBaseModel):
    application_id: Optional[str] = None
    system_snapshot: Optional[SystemSnapshot] = None
    event_log_entries: list[EventLogEntry] = Field(default_factory=list)
    wer_reports: list[WERReport] = Field(default_factory=list)
    etw_available: bool = False
    etw_note: Optional[str] = None
