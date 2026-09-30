from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Optional

from backend.analyzers.pe_analyzer import PEAnalyzer
from backend.benchmark.architecture_models import BuildArtifact, BuildStatus, CorrectnessStatus
from backend.collectors.capability_collector import CapabilityCollector
from backend.models.common import Architecture, EvidenceType, Provenance, SourceMechanism


class WorkloadBuilder:
    def __init__(self, capability_collector=None, pe_analyzer=None):
        self.capabilities = capability_collector or CapabilityCollector()
        self.pe = pe_analyzer or PEAnalyzer()

    def build(self, source_dir: str, target: Architecture, output_dir: str, build_config: str = "Debug", workload_name: str = None) -> BuildArtifact:
        profile = self.capabilities.collect()
        tool = profile.msvc
        if target == Architecture.X64:
            available = tool.status.value == "VERIFIED" and profile.cmake.status.value == "VERIFIED"
        elif target == Architecture.ARM64:
            available = profile.arm64_compilation.status.value == "VERIFIED"
        elif target == Architecture.ARM64EC:
            available = profile.arm64ec_compilation.status.value == "VERIFIED"
        else:
            available = False
        provenance = [tool.provenance, profile.cmake.provenance]
        if not available:
            return BuildArtifact(
                id=f"ART-{uuid.uuid4().hex[:8]}", workload=source_dir, target=target,
                compiler=tool.path, linker=profile.linker.path, sdk=profile.windows_sdk.path,
                status=BuildStatus.UNAVAILABLE, provenance=provenance,
                errors=[f"Required toolchain for {target.value} is unavailable or unverified."],
            )
        
        # Extract workload name from source_dir if not provided
        if not workload_name:
            workload_name = Path(source_dir).name or "workload"
        
        build_path = Path(output_dir); build_path.mkdir(parents=True, exist_ok=True)
        
        # For ARM64, use vcvarsall to set up the environment
        vcvars_path = None
        if target == Architecture.ARM64:
            vcvars_candidates = list((Path(tool.path or "").parents[4] / "Auxiliary" / "Build" / "vcvarsall.bat").glob("*"))
            if not vcvars_candidates:
                vcvars_path = str(Path(tool.path or "").parents[4] / "Auxiliary" / "Build" / "vcvarsall.bat")
        
        cmake_path = profile.cmake.path or "cmake"
        command = [cmake_path, "-S", source_dir, "-B", str(build_path), f"-DCMAKE_BUILD_TYPE={build_config}"]
        
        try:
            # Configure step
            configured = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
            if configured.returncode != 0:
                return BuildArtifact(id=f"ART-{uuid.uuid4().hex[:8]}", workload=source_dir, target=target, status=BuildStatus.FAILED, command=command, provenance=provenance, errors=[configured.stderr[-2000:]])
            
            # Build step — use nmake or appropriate build tool for this CMake version
            # For older CMake, we may need to use NMake Makefiles or call the generator directly
            build_commands = []
            
            # Try cmake --build first (modern CMake)
            modern_build = [cmake_path, "--build", str(build_path)]
            built = subprocess.run(modern_build, capture_output=True, text=True, check=False, timeout=120)
            
            # If that fails, try to find and use nmake directly
            if built.returncode != 0 and target == Architecture.ARM64:
                # For ARM64, setup environment via vcvarsall and use nmake
                vcvars = Path(str(Path(tool.path or "").parents[4])) / "Auxiliary" / "Build" / "vcvarsall.bat"
                if vcvars.is_file():
                    # Create a batch file to run cmake configure+build with proper env
                    batch_file = build_path / "build_arm64.bat"
                    batch_content = f"""@echo off
call "{vcvars}" arm64
cd /d "{build_path}"
nmake
"""
                    batch_file.write_text(batch_content)
                    built = subprocess.run(
                        [str(batch_file)],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=120,
                        cwd=str(build_path),
                        shell=True
                    )
            
            if built.returncode != 0:
                return BuildArtifact(id=f"ART-{uuid.uuid4().hex[:8]}", workload=source_dir, target=target, status=BuildStatus.FAILED, command=command, provenance=provenance, errors=[built.stderr[-2000:] if built.stderr else "Build failed, no error output."])
        except (OSError, subprocess.SubprocessError) as exc:
            return BuildArtifact(id=f"ART-{uuid.uuid4().hex[:8]}", workload=source_dir, target=target, status=BuildStatus.FAILED, command=command, provenance=provenance, errors=[str(exc)])
        
        executable = next((str(p) for p in build_path.rglob(f"{workload_name}.exe")), None)
        if not executable:
            return BuildArtifact(id=f"ART-{uuid.uuid4().hex[:8]}", workload=source_dir, target=target, status=BuildStatus.FAILED, command=command, provenance=provenance, errors=[f"Build completed but {workload_name}.exe was not found."])
        analysis = self.pe.analyze(executable)
        detected = analysis.identity.architecture
        status = BuildStatus.BUILT if detected == target else BuildStatus.FAILED
        return BuildArtifact(id=f"ART-{uuid.uuid4().hex[:8]}", workload=source_dir, target=target, compiler=tool.path, linker=profile.linker.path, sdk=profile.windows_sdk.path, command=command, status=status, executable_path=executable, detected_architecture=detected, provenance=provenance, errors=[] if status == BuildStatus.BUILT else [f"Requested {target.value}, detected {detected.value}."])

    def verify_output(self, artifact: BuildArtifact, expected_output: str) -> BuildArtifact:
        if artifact.status != BuildStatus.BUILT or not artifact.executable_path:
            artifact.correctness_status = CorrectnessStatus.UNAVAILABLE
            return artifact
        try:
            result = subprocess.run([artifact.executable_path], capture_output=True, text=True, timeout=30, check=False)
            observed = result.stdout.strip()
            artifact.expected_output = expected_output
            artifact.observed_output = observed
            artifact.correctness_status = CorrectnessStatus.PASS if result.returncode == 0 and observed == expected_output else CorrectnessStatus.FAIL
        except (OSError, subprocess.SubprocessError):
            artifact.correctness_status = CorrectnessStatus.UNAVAILABLE
        return artifact
