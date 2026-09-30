from backend.benchmark.architecture_models import BuildStatus, CorrectnessStatus
from backend.benchmark.comparison import compare_benchmarks
from backend.benchmark.workload_builder import WorkloadBuilder
from backend.models.common import Architecture


def test_unavailable_architecture_is_not_fabricated():
    artifact = WorkloadBuilder().build(
        "backend/benchmark/workloads/vector_reduce", Architecture.UNKNOWN, "unused-build"
    )
    assert artifact.status == BuildStatus.UNAVAILABLE
    assert artifact.executable_path is None
    assert artifact.correctness_status == CorrectnessStatus.UNAVAILABLE


def test_comparison_reports_observed_median_difference():
    from backend.benchmark.benchmark_models import BenchmarkConfig, BenchmarkResult, BenchmarkRun, RunValidity
    from backend.models.execution_profile import ExecutionProfile
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    def result(name, values):
        runs = []
        for i, value in enumerate(values):
            profile = ExecutionProfile(id=f"p{i}{name}", run_id=f"r{i}{name}", application_path=name, start_time=now, end_time=now, wall_time_seconds=value)
            runs.append(BenchmarkRun(id=f"run{i}{name}", benchmark_id=name, configuration_id=name, sequence_number=i, execution_profile=profile, validity=RunValidity.VALID, success=True))
        return BenchmarkResult(id=name, configuration=BenchmarkConfig(id=f"cfg{name}", workload=name), runs=runs)

    comparison = compare_benchmarks("vector_reduce", "x64", "ARM64", result("b", [2.0, 4.0]), result("t", [1.0, 3.0]))
    assert comparison.baseline_median == 3.0
    assert comparison.treatment_median == 2.0
    assert comparison.absolute_difference == -1.0
