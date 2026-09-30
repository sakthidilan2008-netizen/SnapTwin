#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from backend.benchmark.workload_builder import WorkloadBuilder
from backend.models.common import Architecture

builder = WorkloadBuilder()
artifact = builder.build(
    source_dir='backend/benchmark/workloads/vector_reduce',
    target=Architecture.ARM64,
    output_dir='build_arm64_scalar'
)

print('=== ARM64 SCALAR BUILD RESULT ===')
print(f'Status: {artifact.status.value}')
print(f'Detected Architecture: {artifact.detected_architecture.value if artifact.detected_architecture else "N/A"}')
print(f'Executable: {artifact.executable_path}')
print(f'Compiler: {artifact.compiler}')
print(f'Linker: {artifact.linker}')
if artifact.errors:
    print(f'Errors:')
    for err in artifact.errors:
        print(f'  {err}')
