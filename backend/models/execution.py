"""
A single execution attempt of the application under investigation — the
record produced each time SnapTwin (or the user) actually runs the target,
whether as a baseline run, an experiment run, or a post-remediation
verification run. TwinBuilder consumes lists of these to build
execution_paths; ResultComparator (experiments/result_comparator.py) diffs
pairs of these.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .common import Provenance, SnapTwinBaseModel


class ExecutionRole(str, Enum):
    BASELINE = "baseline"
    EXPERIMENT = "experiment"
    VERIFICATION = "verification"
    AD_HOC = "ad_hoc"


class ExecutionOutcome(str, Enum):
    SUCCESS = "success"
    CRASHED = "crashed"
    HUNG = "hung"
    NON_ZERO_EXIT = "non_zero_exit"
    FAILED_TO_START = "failed_to_start"
    UNKNOWN = "unknown"


class ExecutionRecord(SnapTwinBaseModel):
    application_id: str
    role: ExecutionRole

    launched_at: Optional[str] = None
    exit_code: Optional[int] = None
    outcome: ExecutionOutcome = ExecutionOutcome.UNKNOWN
    outcome_provenance: Optional[Provenance] = None

    duration_ms: Optional[int] = None
    pid: Optional[int] = None

    loaded_modules: list[str] = Field(
        default_factory=list, description="Modules observed loaded into the process, if enumerable."
    )
    crash_module: Optional[str] = Field(
        default=None, description="Faulting module reported by WER/Event Log, if any."
    )
    crash_exception_code: Optional[str] = None

    stdout_tail: Optional[str] = None
    stderr_tail: Optional[str] = None

    experiment_id: Optional[str] = Field(
        default=None, description="Set when role == EXPERIMENT or VERIFICATION, links back to Experiment."
    )

    is_demo_data: bool = Field(
        default=False,
        description="True if this record came from the controlled demo scenario rather than a live run.",
    )
