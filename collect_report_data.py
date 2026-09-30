#!/usr/bin/env python3
import sys
import json
from pathlib import Path
sys.path.insert(0, '.')

from backend.benchmark.workload_builder import WorkloadBuilder
from backend.analyzers.pe_analyzer import PEAnalyzer
from backend.collectors.capability_collector import CapabilityCollector
from backend.collectors.system_collector import SystemCollector
from backend.models.common import Architecture

print('=== FINAL VALIDATION AND REPORT DATA COLLECTION ===')
print()

# Collect environment data
cc = CapabilityCollector()
profile = cc.collect()
sc = SystemCollector()
system = sc.collect()

print('1. ENVIRONMENT DATA')
print(f'   CPU: {profile.cpu.name}')
print(f'   CPU Vendor: {profile.cpu.vendor}')
print(f'   OS: {profile.os_name} {profile.os_version}')
print(f'   Host Architecture: {profile.host_architecture.detail}')
print()

print('2. TOOLCHAIN DATA')
print(f'   MSVC: {profile.msvc.path}')
print(f'   MSVC Version: {profile.msvc.version}')
print(f'   ARM64 Compiler: {profile.arm64_compilation.status.value}')
print(f'   CMake: {profile.cmake.path}')
print(f'   Windows SDK: {profile.windows_sdk.path}')
print()

# Build both variants
builder = WorkloadBuilder()
scalar_build = builder.build(
    source_dir='backend/benchmark/workloads/vector_reduce',
    target=Architecture.ARM64,
    output_dir='build_final_report'
)

debug_dir = Path('build_final_report') / 'Debug'
scalar_exe = str(debug_dir / 'vector_reduce.exe')
neon_exe = str(debug_dir / 'vector_reduce_neon.exe')

print('3. BUILD ARTIFACTS')
scalar_exists = Path(scalar_exe).exists()
neon_exists = Path(neon_exe).exists()
print(f'   ARM64 Scalar: {"AVAILABLE" if scalar_exists else "UNAVAILABLE"} - {scalar_exe}')
print(f'   ARM64 NEON: {"AVAILABLE" if neon_exists else "UNAVAILABLE"} - {neon_exe}')
print()

# PE Analysis for both
print('4. PE ARCHITECTURE VALIDATION')
pe = PEAnalyzer()

if scalar_exists:
    scalar_pe = pe.analyze(scalar_exe)
    print(f'   Scalar:')
    print(f'     Requested: ARM64')
    print(f'     Detected: {scalar_pe.identity.architecture.value}')
    print(f'     PE Machine: {scalar_pe.identity.architecture_provenance.raw.get("evidence", [{}])[0].get("value", "N/A")}')
    print(f'     Confidence: {scalar_pe.identity.architecture_provenance.confidence}')
    print(f'     Classification: {scalar_pe.identity.architecture_provenance.raw.get("classification", "N/A")}')

if neon_exists:
    neon_pe = pe.analyze(neon_exe)
    print(f'   NEON:')
    print(f'     Requested: ARM64')
    print(f'     Detected: {neon_pe.identity.architecture.value}')
    print(f'     PE Machine: {neon_pe.identity.architecture_provenance.raw.get("evidence", [{}])[0].get("value", "N/A")}')
    print(f'     Confidence: {neon_pe.identity.architecture_provenance.confidence}')
    print(f'     Classification: {neon_pe.identity.architecture_provenance.raw.get("classification", "N/A")}')
print()

# Correctness
print('5. CORRECTNESS VALIDATION')
import subprocess
if scalar_exists:
    result = subprocess.run([scalar_exe], capture_output=True, text=True, timeout=30,
                           cwd='C:\\Users\\Rashmika K\\SnapTwin')
    scalar_output = result.stdout.strip()
    print(f'   Scalar output: {scalar_output}')

if neon_exists:
    result = subprocess.run([neon_exe], capture_output=True, text=True, timeout=30,
                           cwd='C:\\Users\\Rashmika K\\SnapTwin')
    neon_output = result.stdout.strip()
    print(f'   NEON output: {neon_output}')
    
    if scalar_exists and neon_output == scalar_output:
        print(f'   ✓ OUTPUTS MATCH: Correctness PASS')
    else:
        print(f'   ✗ OUTPUTS DIFFER: Correctness FAIL')
print()

print('6. BENCHMARK METADATA')
print(f'   Workload: vector_reduce (1M uint64 operations)')
print(f'   Runs per variant: 10 measured + 1 warmup')
print(f'   Timeout: 30 seconds')
print(f'   Metric: wall_time_seconds')
print()

print('=== REPORT READY ===')
print('Verify data above; all required fields are collected for the final report.')
