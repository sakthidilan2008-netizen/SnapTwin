"""Measured execution profile for one controlled process run."""
from __future__ import annotations

import datetime
from typing import Optional
from pydantic import Field
from .common import Provenance, SnapTwinBaseModel
from .telemetry import SystemSnapshot


class ExecutionProfile(SnapTwinBaseModel):
    run_id: str
    application_path: str
    process_architecture: Optional[str] = None
    native_system_architecture: Optional[str] = None
    start_time: datetime.datetime
    end_time: datetime.datetime
    wall_time_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    timed_out: bool = False
    termination_reason: Optional[str] = None
    cpu_user_time_seconds: Optional[float] = None
    cpu_kernel_time_seconds: Optional[float] = None
    cpu_total_time_seconds: Optional[float] = None
    cpu_cycle_count: Optional[int] = None
    peak_working_set_bytes: Optional[int] = None
    average_working_set_bytes: Optional[int] = None
    thread_count: Optional[int] = None
    context_switches: Optional[int] = None
    page_faults: Optional[int] = None
    io_read_bytes: Optional[int] = None
    io_write_bytes: Optional[int] = None
    runtime_module_count: Optional[int] = None
    static_dependency_count: Optional[int] = None
    runtime_modules: list[str] = Field(default_factory=list)
    system_snapshot: Optional[SystemSnapshot] = None
    provenance: list[Provenance] = Field(default_factory=list)
