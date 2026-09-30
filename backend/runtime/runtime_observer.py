"""
backend/runtime/runtime_observer.py

Orchestrates the entire Stage 4 process:
1. Snapshots the system
2. Launches target process
3. Observes runtime events and modules
4. Constructs the RuntimeObservationReport
"""
import uuid
import threading
import time
from typing import Optional

from backend.runtime.runtime_models import (
    RuntimeObservationReport,
    RuntimeEvent,
    EventType,
)
from backend.models.common import EvidenceType, utc_now
from backend.runtime.process_observer import ProcessObserver
from backend.runtime.module_observer import ModuleObserver
from backend.collectors.system_collector import SystemCollector


class RuntimeObserver:
    def __init__(self, timeout_seconds: int = 30):
        self._process_observer = ProcessObserver(timeout_seconds)
        self._module_observer = ModuleObserver()
        self._system_collector = SystemCollector()

    def run_and_observe(
        self, 
        path: str, 
        arguments: Optional[list[str]] = None,
        working_directory: Optional[str] = None
    ) -> RuntimeObservationReport:
        
        events = []
        modules = []
        
        # 1. System Snapshot
        system_snapshot = self._system_collector.collect()
        events.append(RuntimeEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_SNAPSHOT,
            source="runtime_observer",
            evidence_type=EvidenceType.OBSERVED,
            confidence=1.0,
            payload={"os_architecture": system_snapshot.os.architecture}
        ))
        
        # We need to launch the process and simultaneously try to observe its modules
        # This is best-effort in MVP. We use a simple thread to poll modules while the process runs.
        
        exec_state = None
        stop_polling = threading.Event()
        
        def _poll_modules(pid: int):
            while not stop_polling.is_set():
                observed_mods = self._module_observer.observe_running_process(pid)
                # Naive merge: keep new modules
                existing = {m.name.lower() for m in modules}
                for m in observed_mods:
                    if m.name.lower() not in existing:
                        modules.append(m)
                        events.append(RuntimeEvent(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.MODULE_LOADED,
                            source="module_observer",
                            evidence_type=EvidenceType.OBSERVED,
                            confidence=1.0,
                            payload={"module_name": m.name}
                        ))
                time.sleep(0.1)
                
        # 2. Launch Process
        # We can't poll easily with psutil.Popen.wait() blocking, so we'll wrap the launch
        import subprocess
        import psutil
        
        cwd = working_directory or __import__('os').path.dirname(__import__('os').path.abspath(path))
        args = arguments or []
        run_id = str(uuid.uuid4())
        
        from backend.runtime.runtime_models import RuntimeExecution, TerminationReason
        exec_state = RuntimeExecution(
            run_id=run_id,
            working_directory=cwd,
            arguments=args,
            start_time=utc_now()
        )
        
        events.append(RuntimeEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.PROCESS_STARTED,
            source="process_observer",
            evidence_type=EvidenceType.OBSERVED,
            confidence=1.0,
            payload={"path": path}
        ))
        
        poll_thread = None
        try:
            cmd = [path] + args
            proc = psutil.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            exec_state.process_id = proc.pid
            
            poll_thread = threading.Thread(target=_poll_modules, args=(proc.pid,))
            poll_thread.start()
            
            try:
                proc.wait(timeout=self._process_observer.timeout_seconds)
                exec_state.end_time = utc_now()
                exec_state.exit_code = proc.returncode
                
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
                events.append(RuntimeEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.TIMEOUT,
                    source="process_observer",
                    evidence_type=EvidenceType.OBSERVED,
                    confidence=1.0,
                    payload={"timeout_seconds": self._process_observer.timeout_seconds}
                ))
        except Exception as e:
            exec_state.end_time = utc_now()
            exec_state.termination_reason = TerminationReason.UNAVAILABLE
            exec_state.success = False
            events.append(RuntimeEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.OBSERVATION_UNAVAILABLE,
                source="process_observer",
                evidence_type=EvidenceType.OBSERVED,
                confidence=1.0,
                payload={"error": str(e)}
            ))
        finally:
            stop_polling.set()
            if poll_thread:
                poll_thread.join(timeout=1.0)
                
        events.append(RuntimeEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.PROCESS_EXITED,
            source="process_observer",
            evidence_type=EvidenceType.OBSERVED,
            confidence=1.0,
            payload={
                "exit_code": exec_state.exit_code,
                "termination_reason": exec_state.termination_reason.value
            }
        ))
        
        if exec_state.termination_reason == TerminationReason.CRASHED:
            events.append(RuntimeEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.CRASH_OBSERVED,
                source="process_observer",
                evidence_type=EvidenceType.OBSERVED,
                confidence=1.0,
                payload={"exit_code": exec_state.exit_code}
            ))

        return RuntimeObservationReport(
            id=run_id,
            run_id=run_id,
            execution=exec_state,
            events=events,
            modules=modules,
            system_snapshot=system_snapshot
        )
