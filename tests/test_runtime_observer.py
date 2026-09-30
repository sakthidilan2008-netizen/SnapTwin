"""
tests/test_runtime_observer.py

Tests the RuntimeObserver orchestration.
"""
import sys
from backend.runtime.runtime_observer import RuntimeObserver
from backend.runtime.runtime_models import EventType, TerminationReason

def test_runtime_observer_successful_run():
    obs = RuntimeObserver()
    # Simple sleep allows time for the polling thread to catch modules
    report = obs.run_and_observe(sys.executable, ["-c", "import time; time.sleep(0.5)"])
    
    assert report.execution.success is True
    assert report.execution.termination_reason == TerminationReason.COMPLETED
    assert report.system_snapshot is not None
    
    event_types = {e.event_type for e in report.events}
    assert EventType.PROCESS_STARTED in event_types
    assert EventType.PROCESS_EXITED in event_types
    assert EventType.SYSTEM_SNAPSHOT in event_types
    # MODULE_LOADED might or might not fire in 0.5s but usually does
    
def test_runtime_observer_timeout():
    obs = RuntimeObserver(timeout_seconds=1)
    report = obs.run_and_observe(sys.executable, ["-c", "import time; time.sleep(3)"])
    
    assert report.execution.timed_out is True
    event_types = {e.event_type for e in report.events}
    assert EventType.TIMEOUT in event_types
    assert EventType.PROCESS_EXITED in event_types
