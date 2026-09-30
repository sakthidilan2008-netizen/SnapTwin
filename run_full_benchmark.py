#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from backend.benchmark.workload_builder import WorkloadBuilder
from backend.benchmark.benchmark_runner import BenchmarkRunner
from backend.benchmark.benchmark_models import BenchmarkConfig
from backend.benchmark.comparison import compare_benchmarks
from backend.models.common import Architecture
from pathlib import Path
import json

print('=== SNAPDRAGON ARM64 BENCHMARK: SCALAR VS NEON ===')
print()

# Build both variants
builder = WorkloadBuilder()
scalar_artifact = builder.build(
    source_dir='backend/benchmark/workloads/vector_reduce',
    target=Architecture.ARM64,
    output_dir='build_benchmark_scalar'
)

# Verify both were built
debug_dir = Path('build_benchmark_scalar') / 'Debug'
scalar_exe = str(debug_dir / 'vector_reduce.exe')
neon_exe = str(debug_dir / 'vector_reduce_neon.exe')

if not Path(scalar_exe).exists() or not Path(neon_exe).exists():
    print('ERROR: One or both executables not found!')
    print(f'  Scalar: {Path(scalar_exe).exists()} - {scalar_exe}')
    print(f'  NEON: {Path(neon_exe).exists()} - {neon_exe}')
    sys.exit(1)

print(f'Scalar executable: {scalar_exe}')
print(f'NEON executable: {neon_exe}')
print()

# Run benchmarks
runner = BenchmarkRunner()

print('Running scalar benchmark (1 warmup, 10 measured runs)...')
scalar_config = BenchmarkConfig(
    id='vector_reduce_scalar',
    workload=scalar_exe,
    arguments=[],
    warmup_runs=1,
    measured_runs=10,
    timeout_seconds=30.0
)
scalar_result = runner.run(scalar_config)

print('Running NEON benchmark (1 warmup, 10 measured runs)...')
neon_config = BenchmarkConfig(
    id='vector_reduce_neon',
    workload=neon_exe,
    arguments=[],
    warmup_runs=1,
    measured_runs=10,
    timeout_seconds=30.0
)
neon_result = runner.run(neon_config)

print()
print('=== BENCHMARK RESULTS ===')
print()

# Extract timing data
def get_timings(result):
    timings = []
    for run in result.runs:
        if run.success and run.execution_profile and run.execution_profile.wall_time_seconds:
            timings.append(run.execution_profile.wall_time_seconds)
    return timings

scalar_timings = get_timings(scalar_result)
neon_timings = get_timings(neon_result)

print(f'Scalar runs: {len(scalar_timings)} valid')
print(f'  Wall-clock times (seconds): {[f"{t:.6f}" for t in scalar_timings]}')
if scalar_timings:
    import statistics
    print(f'  Median: {statistics.median(scalar_timings):.6f}s')
    print(f'  Min: {min(scalar_timings):.6f}s, Max: {max(scalar_timings):.6f}s')
print()

print(f'NEON runs: {len(neon_timings)} valid')
print(f'  Wall-clock times (seconds): {[f"{t:.6f}" for t in neon_timings]}')
if neon_timings:
    import statistics
    print(f'  Median: {statistics.median(neon_timings):.6f}s')
    print(f'  Min: {min(neon_timings):.6f}s, Max: {max(neon_timings):.6f}s')
print()

# Compare
print('=== COMPARISON ===')
comparison = compare_benchmarks(
    workload='vector_reduce',
    baseline_name='ARM64_Scalar',
    treatment_name='ARM64_NEON',
    baseline=scalar_result,
    treatment=neon_result,
    metric='wall_time_seconds'
)

print(f'Baseline (Scalar) Median: {comparison.baseline_median:.6f}s')
print(f'Treatment (NEON) Median: {comparison.treatment_median:.6f}s')
print(f'Absolute Difference: {comparison.absolute_difference:.6f}s' if comparison.absolute_difference else 'N/A')
print(f'Relative Difference: {comparison.relative_difference_percent:.2f}%' if comparison.relative_difference_percent else 'N/A')

if comparison.relative_difference_percent:
    direction = 'faster' if comparison.relative_difference_percent < 0 else 'slower'
    magnitude = abs(comparison.relative_difference_percent)
    print()
    print(f'On this Snapdragon ARM64 system, under the recorded conditions,')
    print(f'the NEON implementation was {magnitude:.2f}% {direction} than the scalar implementation.')
    print()
    print('This measurement reflects the observed performance on this specific machine.')
    print('No causal inference or generalization should be made without further investigation.')
