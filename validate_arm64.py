#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from backend.analyzers.pe_analyzer import PEAnalyzer
from backend.benchmark.workload_builder import WorkloadBuilder
from backend.models.common import Architecture

# Build ARM64 scalar
builder = WorkloadBuilder()
artifact = builder.build(
    source_dir='backend/benchmark/workloads/vector_reduce',
    target=Architecture.ARM64,
    output_dir='build_arm64_scalar'
)

print('=== ARM64 SCALAR BUILD ===')
print(f'Status: {artifact.status.value}')
print(f'Executable: {artifact.executable_path}')
print(f'Detected Architecture: {artifact.detected_architecture.value if artifact.detected_architecture else "N/A"}')
print()

if artifact.executable_path:
    # Run PE analysis
    pe = PEAnalyzer()
    analysis = pe.analyze(artifact.executable_path)
    print('=== PE ANALYSIS ===')
    print(f'Architecture: {analysis.identity.architecture.value}')
    print(f'Classification: {analysis.identity.architecture_provenance.raw.get("classification", "N/A")}')
    print(f'Confidence: {analysis.identity.architecture_provenance.confidence}')
    print(f'PE Machine: {analysis.identity.architecture_provenance.raw.get("evidence", [{}])[0].get("value", "N/A")}')
    print()
    
    # Run correctness test
    print('=== CORRECTNESS TEST ===')
    artifact = builder.verify_output(artifact, "2988851968")
    print(f'Correctness Status: {artifact.correctness_status.value}')
    print(f'Expected Output: {artifact.expected_output}')
    print(f'Observed Output: {artifact.observed_output}')
else:
    print('Executable not built; skipping PE analysis and correctness test.')
