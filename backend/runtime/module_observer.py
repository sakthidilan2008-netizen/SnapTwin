"""
backend/runtime/module_observer.py

Observes modules loaded by the target process at runtime.
For MVP, this relies on non-privileged access (e.g., via psutil if the process
is alive, or by observing loading behavior).
"""
import psutil
from typing import Optional

from backend.runtime.runtime_models import RuntimeModule, Architecture, utc_now
from backend.analyzers.pe_analyzer import PEAnalyzer


class ModuleObserver:
    def __init__(self):
        self._pe = PEAnalyzer()

    def observe_running_process(self, pid: int) -> list[RuntimeModule]:
        """
        Polls the loaded modules of a live process.
        Note: Because short-lived processes may exit before we can poll,
        this method is best effort in the MVP.
        """
        modules = []
        try:
            proc = psutil.Process(pid)
            # memory_maps() on Windows returns loaded DLLs
            for mmap in proc.memory_maps():
                path = mmap.path
                if not path or path.startswith("["):
                    continue
                    
                name = path.split("\\")[-1].split("/")[-1]
                arch = Architecture.UNKNOWN
                
                # Best-effort PE analysis to determine architecture
                pe_analysis = self._pe.analyze(path)
                if pe_analysis.analysis_complete:
                    arch = pe_analysis.identity.architecture
                    
                modules.append(RuntimeModule(
                    name=name,
                    absolute_path=path,
                    load_status="LOADED",
                    timestamp=utc_now(),
                    architecture=arch
                ))
        except (psutil.NoSuchProcess, psutil.AccessDenied, NotImplementedError, AttributeError):
            pass
            
        return modules
