"""API endpoints for controlled MVP-2 benchmark runs."""
from fastapi import APIRouter, HTTPException
from backend.benchmark.benchmark_models import BenchmarkConfig, BenchmarkResult
from backend.benchmark.benchmark_runner import BenchmarkRunner

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])
_results: dict[str, BenchmarkResult] = {}


@router.post("/run", response_model=BenchmarkResult)
def run_benchmark(config: BenchmarkConfig) -> BenchmarkResult:
    result = BenchmarkRunner().run(config)
    _results[result.id] = result
    return result


@router.get("/{benchmark_id}", response_model=BenchmarkResult)
def get_benchmark(benchmark_id: str) -> BenchmarkResult:
    result = _results.get(benchmark_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return result
