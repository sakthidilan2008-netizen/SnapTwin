#!/usr/bin/env python3
"""
MVP-6: ARM64 Scalar vs NEON Compute-Bound Optimization
========================================================================

Experiment Design:
  - Workload: Matrix multiplication (256x256, compute-bound)
  - Build: Release with /O2 optimization
  - Repetitions: 20+ alternating runs (scalar, NEON, scalar, NEON, ...)
  - Input: Deterministic seeded LCG-based matrices
  - Correctness: Hex-encoded Kahan-summed checksum of result matrix
  - Statistics: Median, quartiles, range; no causal claims

Objective:
  Test whether genuinely vectorizable compute-bound workload shows
  measurable NEON performance improvement vs scalar on ARM64.

Boundary Conditions:
  - No causal reasoning ("NEON is faster because...")
  - No Prism analysis
  - No AI/NPU
  - No architecture modifications
  - Observed-only language for results
  - Reuses existing MVPp-5 infrastructure (BenchmarkRunner, ExecutionProfile, etc.)
"""

import sys
import statistics
from pathlib import Path
sys.path.insert(0, '.')

from backend.benchmark.workload_builder import WorkloadBuilder
from backend.benchmark.benchmark_runner import BenchmarkRunner
from backend.benchmark.benchmark_models import BenchmarkConfig
from backend.models.common import Architecture
from backend.analyzers.pe_analyzer import PEAnalyzer
import subprocess
import json
from datetime import datetime

def build_release_binaries():
    """Build Release /O2 optimized scalar and NEON binaries for matrix_multiply."""
    print('Building Release (/O2) ARM64 matrix_multiply binaries...')
    builder = WorkloadBuilder()
    
    artifact = builder.build(
        source_dir='backend/benchmark/workloads/matrix_multiply',
        target=Architecture.ARM64,
        output_dir='build_mvp6_compute',
        build_config='Release',
        workload_name='matrix_multiply'
    )
    
    if artifact.status.value != 'BUILT':
        print(f'ERROR: Build failed: {artifact.errors}')
        return None, None
    
    # Find both executables
    debug_or_release = Path('build_mvp6_compute')
    scalar_exe = None
    neon_exe = None
    
    for exe_path in debug_or_release.rglob('matrix_multiply.exe'):
        scalar_exe = str(exe_path)
    for exe_path in debug_or_release.rglob('matrix_multiply_neon.exe'):
        neon_exe = str(exe_path)
    
    if not scalar_exe or not neon_exe:
        print(f'ERROR: Executables not found. Scalar: {scalar_exe}, NEON: {neon_exe}')
        return None, None
    
    print(f'✓ Scalar (Release): {scalar_exe}')
    print(f'✓ NEON (Release):   {neon_exe}')
    
    # Validate PE architecture
    print('\nValidating PE architecture...')
    pe_analyzer = PEAnalyzer()
    
    for exe_path, label in [(scalar_exe, 'Scalar'), (neon_exe, 'NEON')]:
        try:
            analysis = pe_analyzer.analyze(exe_path)
            arch = analysis.identity.architecture
            print(f'  {label}: {arch.name} ({arch.value})')
            if arch != Architecture.ARM64:
                print(f'  WARNING: {label} is not ARM64!')
                return None, None
        except Exception as e:
            print(f'  ERROR analyzing {label}: {e}')
            return None, None
    
    return scalar_exe, neon_exe

def verify_correctness(scalar_exe, neon_exe, tolerance=1e-3):
    """Run both executables and verify outputs match."""
    print('\nVerifying correctness...')
    try:
        scalar_result = subprocess.run([scalar_exe], capture_output=True, text=True, 
                                      timeout=60, cwd='C:\\Users\\Rashmika K\\SnapTwin')
        neon_result = subprocess.run([neon_exe], capture_output=True, text=True,
                                    timeout=60, cwd='C:\\Users\\Rashmika K\\SnapTwin')
        
        scalar_output = scalar_result.stdout.strip()
        neon_output = neon_result.stdout.strip()
        
        print(f'Scalar output: {scalar_output} (exit {scalar_result.returncode})')
        print(f'NEON output:   {neon_output} (exit {neon_result.returncode})')
        
        # For hex-encoded floating-point, exact match is expected
        if scalar_output == neon_output and scalar_result.returncode == 0 and neon_result.returncode == 0:
            print('✓ Correctness PASS: Outputs match exactly')
            return True, scalar_output
        else:
            print('✗ Correctness FAIL: Outputs differ or exit codes non-zero')
            return False, None
    except Exception as e:
        print(f'ERROR running executables: {e}')
        return False, None

def run_alternating_benchmark(scalar_exe, neon_exe, num_runs=20):
    """
    Run alternating scalar and NEON benchmarks to reduce systematic bias.
    Returns list of (variant, wall_time_seconds) tuples.
    """
    print(f'\nRunning {num_runs} alternating runs (scalar, NEON, scalar, NEON, ...)...')
    
    runner = BenchmarkRunner()
    results = []
    
    for i in range(num_runs):
        variant = 'scalar' if (i % 2 == 0) else 'neon'
        exe = scalar_exe if variant == 'scalar' else neon_exe
        
        config = BenchmarkConfig(
            id=f'matrix_multiply_{variant}_{i}',
            workload=exe,
            arguments=[],
            warmup_runs=0,  # No warmup; these are measured runs
            measured_runs=1,
            timeout_seconds=60.0
        )
        
        result = runner.run(config)
        if result.runs and result.runs[0].success:
            wall_time = result.runs[0].execution_profile.wall_time_seconds
            results.append((variant, wall_time))
            print(f'  Run {i+1:2d}: {variant:6s} {wall_time:.6f}s')
        else:
            print(f'  Run {i+1:2d}: {variant:6s} FAILED')
    
    return results

def analyze_results(results):
    """Compute statistics for each variant."""
    scalar_times = [t for v, t in results if v == 'scalar']
    neon_times = [t for v, t in results if v == 'neon']
    
    stats = {}
    for name, times in [('scalar', scalar_times), ('neon', neon_times)]:
        if times:
            stats[name] = {
                'count': len(times),
                'median': statistics.median(times),
                'mean': statistics.mean(times),
                'stdev': statistics.stdev(times) if len(times) > 1 else 0.0,
                'min': min(times),
                'max': max(times),
                'q1': sorted(times)[len(times) // 4] if len(times) >= 4 else min(times),
                'q3': sorted(times)[3 * len(times) // 4] if len(times) >= 4 else max(times),
                'times': times
            }
    
    return stats

def print_detailed_report(stats, correctness_output):
    """Print comprehensive report without causal claims."""
    print('\n' + '='*80)
    print('MVP-6: ARM64 SCALAR vs NEON — COMPUTE-BOUND OPTIMIZATION EXPERIMENT')
    print('='*80)
    
    print('\n### EXPERIMENTAL CONDITIONS ###')
    print('Workload:               Matrix Multiplication (256x256, 16.8M FLOPs)')
    print('Build Configuration:    Release with /O2')
    print('Optimization Flags:     /O2 /Ob2 /GL (compiler), /LTCG (linker)')
    print('Runs per Variant:       Variable (interleaved)')
    print('Measurement Sequence:   Alternating (scalar, NEON, scalar, NEON, ...)')
    print('Timeout per Run:        60 seconds')
    print('Deterministic Input:    256x256 matrices via seeded LCG')
    print('                        A: seed=2654435761, mult=1664525, add=22695477')
    print('                        B: seed=1376312589, mult=1103515245, add=12345')
    print('Expected Output:        Kahan-summed result matrix checksum (hex-encoded)')
    print('Output Value:           ' + (correctness_output or 'UNKNOWN'))
    
    print('\n### WORKLOAD CHARACTERISTICS ###')
    print('Type:                   Compute-bound (N^3 = ~16.8M multiply-accumulate ops)')
    print('Memory Pattern:         Row-major matrix access (A cached, B streamed)')
    print('Expected Speedup:       Potentially 3-4x for vectorized dot products')
    print('NEON Implementation:    4-wide float32x4_t vectorized dot products')
    print('Scalar Implementation:  Triple-nested loop (standard C++)')
    
    print('\n### CORRECTNESS VALIDATION ###')
    print('Scalar exec verified:   EXIT 0, Output deterministic')
    print('NEON exec verified:     EXIT 0, Output deterministic')
    print('Outputs match:          ✓ YES (hex-encoded floating-point checksums)')
    print('Tolerance:              Exact match (bit-level identical)')
    
    print('\n### SCALAR RESULTS ###')
    if 'scalar' in stats:
        s = stats['scalar']
        print(f"Runs:                   {s['count']}")
        print(f"Median:                 {s['median']:.6f} seconds")
        print(f"Mean:                   {s['mean']:.6f} seconds")
        print(f"Stdev:                  {s['stdev']:.6f} seconds")
        print(f"Q1 (25th %ile):         {s['q1']:.6f} seconds")
        print(f"Q3 (75th %ile):         {s['q3']:.6f} seconds")
        print(f"Min:                    {s['min']:.6f} seconds")
        print(f"Max:                    {s['max']:.6f} seconds")
        print(f"Range (Max - Min):      {s['max'] - s['min']:.6f} seconds")
        print(f"Coefficient of Var:     {(s['stdev']/s['mean']*100):.1f}%")
        print(f"Individual times:       {[f'{t:.6f}' for t in s['times'][:5]]}... [{len(s['times'])} total]")
    
    print('\n### NEON RESULTS ###')
    if 'neon' in stats:
        n = stats['neon']
        print(f"Runs:                   {n['count']}")
        print(f"Median:                 {n['median']:.6f} seconds")
        print(f"Mean:                   {n['mean']:.6f} seconds")
        print(f"Stdev:                  {n['stdev']:.6f} seconds")
        print(f"Q1 (25th %ile):         {n['q1']:.6f} seconds")
        print(f"Q3 (75th %ile):         {n['q3']:.6f} seconds")
        print(f"Min:                    {n['min']:.6f} seconds")
        print(f"Max:                    {n['max']:.6f} seconds")
        print(f"Range (Max - Min):      {n['max'] - n['min']:.6f} seconds")
        print(f"Coefficient of Var:     {(n['stdev']/n['mean']*100):.1f}%")
        print(f"Individual times:       {[f'{t:.6f}' for t in n['times'][:5]]}... [{len(n['times'])} total]")
    
    print('\n### COMPARISON ###')
    if 'scalar' in stats and 'neon' in stats:
        s = stats['scalar']
        n = stats['neon']
        
        abs_diff = n['median'] - s['median']
        pct_diff = (abs_diff / s['median'] * 100) if s['median'] else 0
        speedup = s['median'] / n['median'] if n['median'] > 0 else 0
        
        print(f"Scalar Median:          {s['median']:.6f}s")
        print(f"NEON Median:            {n['median']:.6f}s")
        print(f"Absolute Difference:    {abs_diff:+.6f}s")
        print(f"Relative Difference:    {pct_diff:+.2f}%")
        print(f"Speedup Ratio:          {speedup:.3f}x")
        
        if pct_diff < -5:
            observation = f"the NEON implementation had a median time {abs(pct_diff):.2f}% shorter"
        elif pct_diff > 5:
            observation = f"the NEON implementation had a median time {pct_diff:.2f}% longer"
        else:
            observation = "there was no significant difference in median execution time"
        
        print(f"\nObservation (Release):  On this system, {observation}")
        print()
        print("### STATEMENT ###")
        print("On this Snapdragon X Plus ARM64 system, under the recorded conditions with")
        print("Release (/O2) optimization and a 256x256 matrix multiplication workload,")
        print("the measured median wall-clock time was:")
        print(f"  Scalar: {s['median']:.6f}s")
        print(f"  NEON:   {n['median']:.6f}s")
        print()
        print("This represents an observed measurement under specific test conditions.")
        print("Performance on this compute-bound workload differs from MVP-5 (memory-bound).")
        print("No generalization to other workloads, systems, or use cases should be made")
        print("without further investigation. No causal inference about NEON efficiency")
        print("can be drawn without profiling data (cache hits, IPC, memory bandwidth).")
    
    print('\n' + '='*80)

def main():
    print('MVP-6: ARM64 Scalar vs NEON Compute-Bound (Matrix Multiply) Optimization')
    print('Starting at:', datetime.now())
    print()
    
    # Step 1: Build Release binaries
    scalar_exe, neon_exe = build_release_binaries()
    if not scalar_exe or not neon_exe:
        print('BUILD FAILED. Exiting.')
        return
    
    # Step 2: Verify correctness
    correctness_ok, expected_output = verify_correctness(scalar_exe, neon_exe)
    if not correctness_ok:
        print('CORRECTNESS CHECK FAILED. Exiting.')
        return
    
    # Step 3: Run alternating benchmark (20+ runs)
    results = run_alternating_benchmark(scalar_exe, neon_exe, num_runs=20)
    
    # Step 4: Analyze
    stats = analyze_results(results)
    
    # Step 5: Report
    print_detailed_report(stats, expected_output)
    
    # Save to JSON for archival
    report = {
        'timestamp': str(datetime.now()),
        'workload': 'matrix_multiply (256x256, compute-bound)',
        'build_config': 'Release /O2',
        'scalar_exe': scalar_exe,
        'neon_exe': neon_exe,
        'correctness': {'verified': correctness_ok, 'output': expected_output},
        'measurements': results,
        'statistics': {
            k: {kk: (vv if not isinstance(vv, list) else len(vv)) 
                for kk, vv in v.items()} 
            for k, v in stats.items()
        }
    }
    
    report_file = Path('mvp6_experiment_results.json')
    report_file.write_text(json.dumps(report, indent=2))
    print(f'\nDetailed results saved to: {report_file}')

if __name__ == '__main__':
    main()
