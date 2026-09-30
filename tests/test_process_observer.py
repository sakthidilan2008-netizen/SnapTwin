"""
tests/test_process_observer.py

Tests controlled process execution.
Uses Python itself as the deterministic fixture.
"""
import sys
import time
from backend.runtime.process_observer import ProcessObserver
from backend.runtime.runtime_models import TerminationReason

def test_successful_process():
    obs = ProcessObserver()
    exec_state = obs.launch_and_observe(sys.executable, ["-c", "print('hello')"])
    
    assert exec_state.exit_code == 0
    assert exec_state.success is True
    assert exec_state.termination_reason == TerminationReason.COMPLETED
    assert exec_state.start_time is not None
    assert exec_state.end_time is not None
    assert exec_state.process_id is not None

def test_non_existent_executable():
    obs = ProcessObserver()
    exec_state = obs.launch_and_observe("does_not_exist_xyz123.exe")
    
    assert exec_state.success is False
    assert exec_state.termination_reason == TerminationReason.UNAVAILABLE
    assert exec_state.exit_code is None

def test_timeout():
    obs = ProcessObserver(timeout_seconds=1)
    # Sleep for 3 seconds, should timeout at 1
    exec_state = obs.launch_and_observe(sys.executable, ["-c", "import time; time.sleep(3)"])
    
    assert exec_state.success is False
    assert exec_state.timed_out is True
    assert exec_state.termination_reason == TerminationReason.TIMED_OUT

def test_non_zero_exit():
    obs = ProcessObserver()
    exec_state = obs.launch_and_observe(sys.executable, ["-c", "import sys; sys.exit(42)"])
    
    assert exec_state.success is False
    assert exec_state.exit_code == 42
    # 42 <= 255 so it's considered COMPLETED but failed
    assert exec_state.termination_reason == TerminationReason.COMPLETED
