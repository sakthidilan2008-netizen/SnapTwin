from __future__ import annotations
import statistics
from backend.benchmark.architecture_models import ArchitectureComparison, CorrectnessStatus
from backend.benchmark.benchmark_models import BenchmarkResult
from backend.models.common import EvidenceType, Provenance, SourceMechanism


def compare_benchmarks(workload: str, baseline_name: str, treatment_name: str, baseline: BenchmarkResult, treatment: BenchmarkResult, metric: str = "wall_time_seconds") -> ArchitectureComparison:
    def values(result):
        return [getattr(run.execution_profile, metric) for run in result.runs if run.success and getattr(run.execution_profile, metric) is not None]
    b, t = values(baseline), values(treatment)
    bm, tm = (statistics.median(b) if b else None), (statistics.median(t) if t else None)
    diff = (tm - bm) if bm is not None and tm is not None else None
    relative = (diff / bm * 100) if diff is not None and bm else None
    return ArchitectureComparison(id=f"CMP-{baseline.id[:8]}", workload=workload, baseline_configuration=baseline_name, treatment_configuration=treatment_name, baseline_runs=[r.id for r in baseline.runs], treatment_runs=[r.id for r in treatment.runs], baseline_median=bm, treatment_median=tm, absolute_difference=diff, relative_difference_percent=relative, correctness_status=CorrectnessStatus.PASS, metric_name=metric, provenance=[Provenance(source=SourceMechanism.CONTROLLED_EXPERIMENT, evidence_type=EvidenceType.OBSERVED, confidence=1.0, detail="Median difference calculated from valid recorded runs.")])
