#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path
sys.path.insert(0, '.')

from backend.benchmark.workload_builder import WorkloadBuilder
from backend.models.common import Architecture
from backend.analyzers.pe_analyzer import PEAnalyzer

print('=== BUILDING ARM64 SCALAR AND NEON VARIANTS ===')
print()

def build_and_validate(output_dir, executable_name, description):
    builder = WorkloadBuilder()
    artifact = builder.build(
        source_dir='backend/benchmark/workloads/vector_reduce',
        target=Architecture.ARM64,
        output_dir=output_dir
    )
    
    print(f'\n--- {description} ---')
    print(f'Build Status: {artifact.status.value}')
    
    if artifact.status.value != 'BUILT':
        print(f'Build Failed: {artifact.errors}')
        return None
    
    exe_path = artifact.executable_path
    if exe_path:
        # Check if the correct executable exists
        scalar_exe = Path(output_dir) / 'Debug' / executable_name
        neon_exe = Path(output_dir) / 'Debug' / 'vector_reduce_neon.exe'
        
        # For scalar, look for vector_reduce.exe
        if executable_name == 'vector_reduce.exe':
            exe_path = str(scalar_exe) if scalar_exe.exists() else exe_path
        elif executable_name == 'vector_reduce_neon.exe':
            exe_path = str(neon_exe) if neon_exe.exists() else exe_path
        
        print(f'Executable: {exe_path}')
        
        # Run PE analysis
        pe = PEAnalyzer()
        analysis = pe.analyze(exe_path)
        print(f'PE Architecture: {analysis.identity.architecture.value}')
        print(f'PE Classification: {analysis.identity.architecture_provenance.raw.get("classification", "N/A")}')
        
        # Run executable to get output
        try:
            result = subprocess.run([exe_path], capture_output=True, text=True, timeout=30, cwd='C:\\Users\\Rashmika K\\SnapTwin')
            output = result.stdout.strip()
            print(f'Exit Code: {result.returncode}')
            print(f'Output: {output}')
            return output
        except Exception as e:
            print(f'Error running executable: {e}')
            return None
    else:
        print('No executable found')
        return None

# Build scalar
scalar_output = build_and_validate('build_arm64_scalar', 'vector_reduce.exe', 'ARM64 Scalar')

# Clean build directory and rebuild to get all targets
import shutil
if Path('build_arm64_both').exists():
    shutil.rmtree('build_arm64_both')

# Rebuild to get both scalar and neon
builder = WorkloadBuilder()
artifact = builder.build(
    source_dir='backend/benchmark/workloads/vector_reduce',
    target=Architecture.ARM64,
    output_dir='build_arm64_both'
)

print(f'\n--- ARM64 Scalar (rebuild) ---')
print(f'Build Status: {artifact.status.value}')

# Check for both executables in the build directory
debug_dir = Path('build_arm64_both') / 'Debug'
if debug_dir.exists():
    exes = list(debug_dir.glob('*.exe'))
    print(f'Executables found in build directory:')
    for exe in exes:
        print(f'  - {exe.name}')
        
        # Test each executable
        try:
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30, cwd='C:\\Users\\Rashmika K\\SnapTwin')
            print(f'    Output: {result.stdout.strip()}, Exit Code: {result.returncode}')
        except Exception as e:
            print(f'    Error: {e}')

print()
print('=== CORRECTNESS CHECK ===')
if scalar_output:
    expected = scalar_output
    print(f'Scalar output: {scalar_output}')
    print(f'Expected for NEON: {expected}')
    print('Both outputs must match to pass correctness check.')
