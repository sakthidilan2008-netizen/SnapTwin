"""
tests/test_module_observer.py

Tests the module observation logic.
"""
import os
import sys
from backend.runtime.module_observer import ModuleObserver

def test_observe_running_process_returns_modules():
    # We can observe our own test process!
    pid = os.getpid()
    obs = ModuleObserver()
    modules = obs.observe_running_process(pid)
    
    # We should at least see python.exe or python-related DLLs
    assert len(modules) > 0
    names = [m.name.lower() for m in modules]
    assert any("python" in n for n in names) or any(".dll" in n for n in names)
    
def test_observe_nonexistent_process_returns_empty():
    obs = ModuleObserver()
    modules = obs.observe_running_process(999999) # Assuming this PID doesn't exist
    assert len(modules) == 0
