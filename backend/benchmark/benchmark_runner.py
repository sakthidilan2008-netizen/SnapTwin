from __future__ import annotations

import datetime
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import psutil

from backend.benchmark.benchmark_models import (
    BenchmarkConfig, BenchmarkResult, BenchmarkRun, BenchmarkSummary,
    NumericSummary, RunValidity,
)
from backend.collectors.system_collector import SystemCollector
from backend.models.common import EvidenceType, Provenance, SourceMechanism, utc_now
from backend.models.execution_profile import ExecutionProfile


class BenchmarkRunner:
    def __init__(self, system_collector=None):
        self.system_collector = system_collector or SystemCollector()

    @staticmethod
    def _architecture() -> str:
        machine = platform.machine().lower()
        return {"amd64": "x64", "x86_64": "x64", "arm64": "ARM64", "aarch64": "ARM64"}.get(machine, "unknown")

    def _run_once(self, config: BenchmarkConfig, benchmark_id: str, sequence: int) -> BenchmarkRun:
        run_id = str(uuid.uuid4())
        start = utc_now()
        command = ([sys.executable, config.workload, *config.arguments]
                   if Path(config.workload).suffix.lower() == ".py"
                   else [config.workload, *config.arguments])
        env = os.environ.copy(); env.update(config.environment)
        proc = None
        validity = RunValidity.UNAVAILABLE
        failure_reason = None
        samples: list[int] = []
        monotonic_start = time.monotonic()
        try:
            proc = psutil.Popen(command, cwd=config.working_directory, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while proc.poll() is None:
                try:
                    samples.append(proc.memory_info().rss)
                except (psutil.Error, OSError):
                    pass
                if time.monotonic() - monotonic_start > config.timeout_seconds:
                    proc.kill(); validity = RunValidity.TIMEOUT; failure_reason = "timeout"
                    break
                time.sleep(0.01)
            if validity != RunValidity.TIMEOUT:
                proc.wait()
                validity = RunValidity.VALID if proc.returncode == 0 else RunValidity.FAILED
                failure_reason = None if proc.returncode == 0 else f"exit_code={proc.returncode}"
        except (OSError, psutil.Error) as exc:
            failure_reason = str(exc)
        end = utc_now()
        cpu_user = cpu_kernel = io_read = io_write = threads = faults = None
        if proc is not None:
            try:
                times = proc.cpu_times(); cpu_user, cpu_kernel = times.user, times.system
                io = proc.io_counters(); io_read, io_write = io.read_bytes, io.write_bytes
                threads = proc.num_threads(); faults = getattr(proc.memory_info(), "num_page_faults", None)
            except (psutil.Error, OSError):
                pass
        snapshot = self.system_collector.collect()
        profile = ExecutionProfile(
            id=f"PROFILE-{run_id[:8]}", run_id=run_id, application_path=config.workload,
            process_architecture=self._architecture(), native_system_architecture=self._architecture(),
            start_time=start, end_time=end, wall_time_seconds=(end-start).total_seconds(),
            exit_code=proc.returncode if proc is not None and proc.poll() is not None else None,
            timed_out=validity == RunValidity.TIMEOUT,
            termination_reason=validity.value, cpu_user_time_seconds=cpu_user,
            cpu_kernel_time_seconds=cpu_kernel,
            cpu_total_time_seconds=(cpu_user + cpu_kernel) if cpu_user is not None and cpu_kernel is not None else None,
            peak_working_set_bytes=max(samples) if samples else None,
            average_working_set_bytes=int(sum(samples)/len(samples)) if samples else None,
            thread_count=threads, page_faults=faults, io_read_bytes=io_read, io_write_bytes=io_write,
            system_snapshot=snapshot,
            provenance=[Provenance(source=SourceMechanism.PROCESS_INFO, evidence_type=EvidenceType.OBSERVED, confidence=1.0, detail="Collected from psutil process observation.")],
        )
        return BenchmarkRun(
            id=f"RUN-{run_id[:8]}", benchmark_id=benchmark_id, configuration_id="default",
            sequence_number=sequence, architecture=self._architecture(), execution_profile=profile,
            system_snapshot=snapshot, validity=validity, success=validity == RunValidity.VALID,
            failure_reason=failure_reason, provenance=profile.provenance,
        )

    def run(self, config: BenchmarkConfig) -> BenchmarkResult:
        benchmark_id = str(uuid.uuid4())
        for _ in range(config.warmup_runs):
            self._run_once(config, benchmark_id, 0)
        runs = [self._run_once(config, benchmark_id, i + 1) for i in range(config.measured_runs)]
        valid = [r for r in runs if r.validity == RunValidity.VALID]
        exclusions: dict[str, int] = {}
        for run in runs:
            if run.validity != RunValidity.VALID:
                exclusions[run.validity.value] = exclusions.get(run.validity.value, 0) + 1
        def values(attr):
            return [v for r in valid if (v := getattr(r.execution_profile, attr)) is not None]
        summary = BenchmarkSummary(
            id=f"SUMMARY-{benchmark_id[:8]}", total_runs=len(runs), valid_runs=len(valid),
            excluded_runs=len(runs)-len(valid), exclusions=exclusions,
            wall_time_seconds=NumericSummary.from_values(values("wall_time_seconds")),
            cpu_time_seconds=NumericSummary.from_values(values("cpu_total_time_seconds")),
            peak_working_set_bytes=NumericSummary.from_values(values("peak_working_set_bytes")),
        )
        return BenchmarkResult(id=benchmark_id, configuration=config, runs=runs, summary=summary,
                               system_context=valid[0].system_snapshot if valid else None,
                               provenance=valid[0].provenance if valid else [])
