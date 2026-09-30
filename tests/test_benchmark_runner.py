import sys
from pathlib import Path
from backend.benchmark.benchmark_models import BenchmarkConfig, RunValidity
from backend.benchmark.benchmark_runner import BenchmarkRunner


def test_benchmark_runner_warmup_and_measured_runs(tmp_path):
    workload = tmp_path / "workload.py"
    workload.write_text("print('deterministic')", encoding="utf-8")
    result = BenchmarkRunner().run(BenchmarkConfig(
        id="cfg", workload=str(workload), warmup_runs=1, measured_runs=3,
    ))
    assert len(result.runs) == 3
    assert all(run.validity == RunValidity.VALID for run in result.runs)
    assert result.summary.valid_runs == 3
    assert result.summary.wall_time_seconds.median is not None


def test_benchmark_runner_timeout(tmp_path):
    workload = tmp_path / "sleep.py"
    workload.write_text("import time; time.sleep(2)", encoding="utf-8")
    result = BenchmarkRunner().run(BenchmarkConfig(
        id="cfg", workload=str(workload), timeout_seconds=1, measured_runs=1,
    ))
    assert result.runs[0].validity == RunValidity.TIMEOUT
    assert result.runs[0].execution_profile.timed_out is True
