"""
backend/runtime/process_observer.py

Controlled launcher for the target process.
Observes process exit state without requiring kernel drivers.
"""
import os
import subprocess
import time
import uuid
import psutil
from typing import Optional

from backend.runtime.runtime_models import (
    RuntimeExecution,
    TerminationReason,
    utc_now,
)

class ProcessObserver:
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def launch_and_observe(
        self, 
        path: str, 
        arguments: Optional[list[str]] = None,
        working_directory: Optional[str] = None
    ) -> RuntimeExecution:
        if arguments is None:
            arguments = []
            
        cwd = working_directory or os.path.dirname(os.path.abspath(path))
        run_id = str(uuid.uuid4())
        
        exec_state = RuntimeExecution(
            run_id=run_id,
            working_directory=cwd,
            arguments=arguments,
            start_time=utc_now()
        )
        
        try:
            # We use psutil.Popen to get process info easily
            cmd = [path] + arguments
            proc = psutil.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            exec_state.process_id = proc.pid
            
            try:
                proc.wait(timeout=self.timeout_seconds)
                exec_state.end_time = utc_now()
                exec_state.exit_code = proc.returncode
                
                # Check for negative exit codes or large unsigned integers (like 0xC0000005)
                # which typically indicate Windows crashes.
                # However, no causal claims are made here.
                if exec_state.exit_code != 0:
                    exec_state.termination_reason = TerminationReason.CRASHED if abs(exec_state.exit_code) > 255 else TerminationReason.COMPLETED
                    exec_state.success = False
                else:
                    exec_state.termination_reason = TerminationReason.COMPLETED
                    exec_state.success = True
                    
            except (subprocess.TimeoutExpired, psutil.TimeoutExpired):
                proc.kill()
                exec_state.end_time = utc_now()
                exec_state.timed_out = True
                exec_state.termination_reason = TerminationReason.TIMED_OUT
                exec_state.success = False
                
        except Exception as e:
            exec_state.end_time = utc_now()
            exec_state.termination_reason = TerminationReason.UNAVAILABLE
            exec_state.success = False
            
        return exec_state
