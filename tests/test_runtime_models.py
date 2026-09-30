"""
tests/test_runtime_models.py

Tests for Stage 4 Pydantic models.
Ensures we can serialize, deserialize, and instantiate properly.
"""
import pytest
from backend.runtime.runtime_models import (
    RuntimeExecution,
    RuntimeEvent,
    EventType,
    TerminationReason,
    utc_now,
)
from backend.models.common import EvidenceType

def test_runtime_execution_instantiation():
    exec_state = RuntimeExecution(
        run_id="run-123",
        working_directory="C:/App",
        arguments=["--headless"]
    )
    assert exec_state.run_id == "run-123"
    assert exec_state.termination_reason == TerminationReason.UNAVAILABLE
    assert not exec_state.success

def test_runtime_event_serialization():
    evt = RuntimeEvent(
        event_id="evt-1",
        event_type=EventType.PROCESS_STARTED,
        source="test",
        evidence_type=EvidenceType.OBSERVED,
        confidence=1.0,
        payload={"pid": 1234}
    )
    
    json_str = evt.model_dump_json()
    assert "PROCESS_STARTED" in json_str
    assert "OBSERVED" in json_str
    
    restored = RuntimeEvent.model_validate_json(json_str)
    assert restored.event_id == "evt-1"
    assert restored.payload["pid"] == 1234
