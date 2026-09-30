"""Observable host/toolchain capability discovery for MVP-1."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

from backend.models.capability import (
    CapabilityFact,
    CapabilityProfile,
    CapabilityStatus,
    HardwareCapability,
    ToolCapability,
)
from backend.models.common import EvidenceType, Provenance, SourceMechanism


class CapabilityCollector:
    """Collects only capabilities supported by direct local evidence."""

    def _provenance(self, source: SourceMechanism, detail: str,
                    evidence: EvidenceType = EvidenceType.OBSERVED) -> Provenance:
        return Provenance(source=source, evidence_type=evidence, confidence=1.0, detail=detail)

    def _fact(self, status: CapabilityStatus, detail: str,
              source: SourceMechanism = SourceMechanism.PROCESS_INFO) -> CapabilityFact:
        evidence = EvidenceType.UNAVAILABLE if status in {
            CapabilityStatus.UNAVAILABLE, CapabilityStatus.UNKNOWN
        } else EvidenceType.OBSERVED
        return CapabilityFact(
            id=f"CAP-{os.urandom(4).hex()}",
            status=status,
            provenance=self._provenance(source, detail, evidence),
            detail=detail,
        )

    def _tool(self, name: str, executable: str,
              candidates: tuple[str, ...] = ()) -> ToolCapability:
        path = shutil.which(executable)
        if path is None:
            for candidate in candidates:
                if Path(candidate).is_file():
                    path = candidate
                    break
        if path is None:
            detail = f"{name} executable was not found through PATH or known installed locations."
            return ToolCapability(
                id=f"CAP-{os.urandom(4).hex()}",
                status=CapabilityStatus.UNAVAILABLE,
                path=None,
                version=None,
                provenance=self._provenance(SourceMechanism.PLATFORM_UNAVAILABLE, detail, EvidenceType.UNAVAILABLE),
                detail=detail,
            )

        version = self._version(path)
        detail = f"{name} found at {path}."
        return ToolCapability(
            id=f"CAP-{os.urandom(4).hex()}",
            status=CapabilityStatus.VERIFIED,
            path=path,
            version=version,
            provenance=self._provenance(SourceMechanism.PROCESS_INFO, detail),
            detail=detail,
        )

    @staticmethod
    def _version(path: str) -> Optional[str]:
        for args in (("/version",), ("--version",), ("-version",)):
            try:
                result = subprocess.run([path, *args], capture_output=True, text=True,
                                        timeout=3, check=False)
                text = (result.stdout or result.stderr).strip()
                if text:
                    return text.splitlines()[0][:256]
            except (OSError, subprocess.SubprocessError):
                continue
        return None

    @staticmethod
    def _visual_studio_candidates(executable: str, target_arch: str = "x64") -> tuple[str, ...]:
        roots = (
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Microsoft Visual Studio",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Microsoft Visual Studio",
        )
        candidates: list[str] = []
        for root in roots:
            if not root.is_dir():
                continue
            patterns = {
                "cl.exe": (
                    f"**/VC/Tools/MSVC/**/bin/Hostx64/{target_arch}/cl.exe"
                    if target_arch != "arm64"
                    else "**/VC/Tools/MSVC/**/bin/Hostx64/arm64/cl.exe"
                ),
                "link.exe": (
                    f"**/VC/Tools/MSVC/**/bin/Hostx64/{target_arch}/link.exe"
                    if target_arch != "arm64"
                    else "**/VC/Tools/MSVC/**/bin/Hostx64/arm64/link.exe"
                ),
                "cmake.exe": "**/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe",
            }
            pattern = patterns.get(executable)
            if pattern is None:
                continue
            for p in root.glob(pattern):
                candidates.extend(str(p) for p in root.glob(pattern) if p.is_file())
        return tuple(candidates)

    def collect(self) -> CapabilityProfile:
        machine = platform.machine().lower()
        if machine in {"amd64", "x86_64", "x64"}:
            host_arch = "x64"
        elif machine in {"arm64", "aarch64"}:
            host_arch = "ARM64"
        elif machine in {"x86", "i386", "i686"}:
            host_arch = "x86"
        else:
            host_arch = "unknown"

        cpu_name = platform.processor() or None
        cpu_vendor = None
        if cpu_name:
            cpu_vendor = "Qualcomm" if re.search(r"qualcomm|snapdragon|oryon", cpu_name, re.I) else (
                "Intel" if re.search(r"intel|genuineintel", cpu_name, re.I) else None
            )
        qualcomm_state = CapabilityStatus.VERIFIED if cpu_vendor == "Qualcomm" else (
            CapabilityStatus.UNKNOWN if not cpu_name else CapabilityStatus.UNAVAILABLE
        )
        qualcomm_detail = f"CPU identity: {cpu_name or 'unavailable'}."

        msvc = self._tool("MSVC", "cl.exe", self._visual_studio_candidates("cl.exe"))
        linker = self._tool("linker", "link.exe", self._visual_studio_candidates("link.exe"))
        # Detect ARM64-targeting MSVC toolchain
        arm64_cl_candidates = self._visual_studio_candidates("cl.exe", target_arch="arm64")
        arm64_link_candidates = self._visual_studio_candidates("link.exe", target_arch="arm64")
        arm64_compiler_status = CapabilityStatus.VERIFIED if arm64_cl_candidates else CapabilityStatus.UNAVAILABLE
        arm64_compiler_path = arm64_cl_candidates[0] if arm64_cl_candidates else None
        
        clang = self._tool("clang", "clang.exe")
        clang_cl = self._tool("clang-cl", "clang-cl.exe")
        cmake = self._tool("CMake", "cmake.exe", self._visual_studio_candidates("cmake.exe"))

        sdk_paths = tuple(str(p) for p in (
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Windows Kits" / "10",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Windows Kits" / "10",
        ) if p.is_dir())
        sdk = self._tool("Windows SDK", "rc.exe", sdk_paths)
        vs_probe = self._visual_studio_candidates("cl.exe")
        vs_path = next((str(Path(p).parents[6]) for p in vs_probe if "Visual Studio" in p), None)
        vs = ToolCapability(
            id=f"CAP-{os.urandom(4).hex()}",
            status=CapabilityStatus.VERIFIED if vs_path else CapabilityStatus.UNAVAILABLE,
            path=vs_path,
            version=Path(vs_path).parts[-2] if vs_path else None,
            provenance=self._provenance(SourceMechanism.PROCESS_INFO, f"Visual Studio installation: {vs_path}" if vs_path else "Visual Studio installation was not discovered.", EvidenceType.OBSERVED if vs_path else EvidenceType.UNAVAILABLE),
        )

        arm64_exec = CapabilityStatus.VERIFIED if host_arch == "ARM64" else CapabilityStatus.UNAVAILABLE
        x64_exec = CapabilityStatus.VERIFIED if host_arch in {"x64", "ARM64"} else CapabilityStatus.UNKNOWN
        
        # Determine ARM64 compilation status based on detected toolchain
        arm64_compilation_detail = f"ARM64-targeting cl.exe located at {arm64_compiler_path}." if arm64_compiler_status == CapabilityStatus.VERIFIED else "ARM64-targeting MSVC compiler was not found."
        
        return CapabilityProfile(
            id=f"CAP-{os.urandom(4).hex()}",
            host_architecture=self._fact(CapabilityStatus.VERIFIED if host_arch != "unknown" else CapabilityStatus.UNKNOWN, f"platform.machine() returned {machine!r}.", SourceMechanism.SYSTEM_INFO),
            os_name=platform.system() or None,
            os_version=platform.version() or None,
            os_build=platform.release() or None,
            cpu=HardwareCapability(id=f"CAP-{os.urandom(4).hex()}", status=CapabilityStatus.VERIFIED if cpu_name else CapabilityStatus.UNKNOWN, name=cpu_name, vendor=cpu_vendor, provenance=self._provenance(SourceMechanism.SYSTEM_INFO, qualcomm_detail, EvidenceType.OBSERVED if cpu_name else EvidenceType.UNAVAILABLE)),
            physical_cores=psutil.cpu_count(logical=False) if psutil else None,
            logical_cores=psutil.cpu_count(logical=True) if psutil else None,
            qualcomm=self._fact(qualcomm_state, qualcomm_detail, SourceMechanism.SYSTEM_INFO),
            snapdragon=self._fact(qualcomm_state, qualcomm_detail, SourceMechanism.SYSTEM_INFO),
            msvc=msvc, linker=linker, clang=clang, clang_cl=clang_cl, cmake=cmake,
            windows_sdk=sdk, visual_studio=vs,
            x64_execution=self._fact(x64_exec, f"Host architecture is {host_arch}; no child-process probe was required."),
            arm64_execution=self._fact(arm64_exec, f"Host architecture is {host_arch}; ARM64 execution is not claimed on non-ARM64 hosts."),
            arm64ec_execution=self._fact(CapabilityStatus.UNAVAILABLE if host_arch != "ARM64" else CapabilityStatus.UNKNOWN, "ARM64EC execution was not independently verified."),
            arm64_compilation=self._fact(arm64_compiler_status, arm64_compilation_detail),
            arm64ec_compilation=self._fact(CapabilityStatus.PRESENT_BUT_UNVERIFIED if msvc.status == CapabilityStatus.VERIFIED else CapabilityStatus.UNAVAILABLE, "No ARM64EC compile probe was performed."),
            gpu=HardwareCapability(id=f"CAP-{os.urandom(4).hex()}", status=CapabilityStatus.UNKNOWN, provenance=self._provenance(SourceMechanism.PLATFORM_UNAVAILABLE, "GPU identity was not collected by this capability collector.", EvidenceType.UNAVAILABLE)),
            npu=HardwareCapability(id=f"CAP-{os.urandom(4).hex()}", status=CapabilityStatus.UNKNOWN, provenance=self._provenance(SourceMechanism.PLATFORM_UNAVAILABLE, "NPU identity was not collected by this capability collector.", EvidenceType.UNAVAILABLE)),
        )
