"""
backend/api/runtime.py

API router for Stage 4 Runtime Observation Engine.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.runtime.runtime_observer import RuntimeObserver
from backend.runtime.runtime_models import RuntimeObservationReport

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


class RunRequest(BaseModel):
    path: str = Field(description="Absolute path to the executable.")
    arguments: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=300)


# In a real app we'd store reports in a DB. For MVP, keep in memory.
_reports: dict[str, RuntimeObservationReport] = {}


@router.post("/run", response_model=RuntimeObservationReport)
def run_target(req: RunRequest) -> RuntimeObservationReport:
    observer = RuntimeObserver(timeout_seconds=req.timeout_seconds)
    report = observer.run_and_observe(
        path=req.path,
        arguments=req.arguments
    )
    _reports[report.run_id] = report
    return report


@router.get("/{run_id}", response_model=RuntimeObservationReport)
def get_run(run_id: str) -> RuntimeObservationReport:
    report = _reports.get(run_id)
    if not report:
        raise HTTPException(status_code=404, detail="Run not found")
    return report
