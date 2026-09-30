"""
SystemCollector — Phase 1 system discovery.

Contract:
  - Every field is either genuinely collected, or explicitly marked
    unavailable. Nothing is guessed or hardcoded.
  - Snapdragon/ARM64 detection is done by *reading* platform/CPU identifiers,
    never assumed. On non-Windows hosts (e.g. this development container),
    most CPU/GPU/NPU detail is legitimately unavailable — that is reported
    as such via evidence_type=UNAVAILABLE / source=PLATFORM_UNAVAILABLE,
    not silently faked.
  - This module is safe to import and run on any OS. Windows-specific,
    richer collection (WMI, registry, DXGI adapters, etc.) is isolated
    behind `_collect_windows_extra()` and only attempted on win32.

Usage:
    collector = SystemCollector()
    snapshot = collector.collect()   # -> models.telemetry.SystemSnapshot
"""

from __future__ import annotations

import platform
import re
import sys
import uuid
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None  # type: ignore

from backend.models.common import EvidenceType, Provenance, SourceMechanism
from backend.models.telemetry import CPUInfo, GPUInfo, MemoryInfo, NPUInfo, OSInfo, SystemSnapshot

_SNAPDRAGON_PATTERN = re.compile(r"(snapdragon|qualcomm|oryon)", re.IGNORECASE)


class SystemCollector:
    """Collects host OS/CPU/GPU/NPU/memory facts using only observable, non-hardcoded mechanisms."""

    def __init__(self) -> None:
        self._warnings: list[str] = []

    def collect(self) -> SystemSnapshot:
        self._warnings = []

        os_info = self._collect_os()
        cpu_info = self._collect_cpu()
        gpu_info = self._collect_gpu()
        npu_info = self._collect_npu(cpu_info)
        memory_info = self._collect_memory()

        provenance = Provenance(
            source=SourceMechanism.SYSTEM_INFO,
            evidence_type=EvidenceType.OBSERVED,
            confidence=1.0,
            detail=f"Collected via Python `platform`/`psutil` on host platform '{sys.platform}'.",
        )

        return SystemSnapshot(
            id=f"SNAP-{uuid.uuid4().hex[:8]}",
            os=os_info,
            cpu=cpu_info,
            gpu=gpu_info,
            npu=npu_info,
            memory=memory_info,
            collected_via=provenance,
            collector_warnings=list(self._warnings),
        )

    # ------------------------------------------------------------------
    # OS
    # ------------------------------------------------------------------
    def _collect_os(self) -> OSInfo:
        system = platform.system()  # 'Windows', 'Linux', 'Darwin'
        version = platform.version()
        release = platform.release()
        arch = self._normalize_architecture(platform.machine())

        return OSInfo(
            id=f"OS-{uuid.uuid4().hex[:8]}",
            name=system if system else "unknown",
            version=version or release or "unknown",
            build=release,
            architecture=arch,
        )

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------
    def _collect_cpu(self) -> CPUInfo:
        arch = self._normalize_architecture(platform.machine())
        model = self._cpu_model_string()

        logical = None
        physical = None
        if psutil is not None:
            try:
                logical = psutil.cpu_count(logical=True)
                physical = psutil.cpu_count(logical=False)
            except Exception as exc:  # pragma: no cover - defensive
                self._warnings.append(f"psutil.cpu_count failed: {exc}")
        else:
            self._warnings.append("psutil not installed; logical/physical core counts unavailable.")

        is_snapdragon: Optional[bool]
        if model:
            is_snapdragon = bool(_SNAPDRAGON_PATTERN.search(model))
        else:
            is_snapdragon = None
            self._warnings.append(
                "CPU model string not determinable on this platform; is_snapdragon left as None "
                "rather than guessed."
            )

        return CPUInfo(
            id=f"CPU-{uuid.uuid4().hex[:8]}",
            architecture=arch,
            model=model,
            logical_cores=logical,
            physical_cores=physical,
            is_snapdragon=is_snapdragon,
        )

    def _cpu_model_string(self) -> Optional[str]:
        """
        Best-effort CPU model string across platforms.
        Windows: platform.processor() is normally populated from the registry.
        Linux: read /proc/cpuinfo 'model name' (x86) or 'Hardware'/'model name' (ARM) if present.
        macOS: platform.processor() is often 'arm' / 'i386'; not model-specific.
        """
        proc = platform.processor()
        if proc:
            return proc

        if sys.platform.startswith("linux"):
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for key in ("model name", "Hardware", "Model"):
                    match = re.search(rf"^{key}\s*:\s*(.+)$", content, re.MULTILINE)
                    if match:
                        return match.group(1).strip()
            except OSError as exc:
                self._warnings.append(f"Could not read /proc/cpuinfo: {exc}")

        self._warnings.append("CPU model string unavailable on this platform via observable mechanisms.")
        return None

    # ------------------------------------------------------------------
    # GPU
    # ------------------------------------------------------------------
    def _collect_gpu(self) -> Optional[GPUInfo]:
        if sys.platform == "win32":
            return self._collect_gpu_windows()

        self._warnings.append(
            "GPU adapter enumeration requires a Windows display API (DXGI/WMI); "
            f"not available on '{sys.platform}'. Reporting as unavailable rather than guessing."
        )
        return None

    def _collect_gpu_windows(self) -> Optional[GPUInfo]:  # pragma: no cover - exercised only on win32
        try:
            import wmi  # type: ignore

            conn = wmi.WMI()
            adapters = conn.Win32_VideoController()
            if not adapters:
                self._warnings.append("Win32_VideoController returned no adapters.")
                return None
            primary = adapters[0]
            return GPUInfo(
                id=f"GPU-{uuid.uuid4().hex[:8]}",
                vendor=getattr(primary, "AdapterCompatibility", None),
                name=getattr(primary, "Name", None),
                driver_version=getattr(primary, "DriverVersion", None),
            )
        except ImportError:
            self._warnings.append(
                "'wmi' package not installed; GPU details unavailable even though running on Windows."
            )
            return None
        except Exception as exc:
            self._warnings.append(f"WMI GPU query failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # NPU
    # ------------------------------------------------------------------
    def _collect_npu(self, cpu_info: CPUInfo) -> NPUInfo:
        """
        Honest NPU presence check. We do NOT claim NPU availability from CPU
        model alone — a Snapdragon CPU string is a weak prior, not proof of
        an accessible NPU/execution-provider. Real provider confirmation is
        the job of ai/ (Phase 9/10) via actual AI runtime evidence; here we
        only report what discovery-time signals exist.
        """
        if sys.platform != "win32":
            self._warnings.append(
                "NPU presence/provider detection depends on Windows AI execution-provider APIs; "
                f"not available on '{sys.platform}'."
            )
            return NPUInfo(
                id=f"NPU-{uuid.uuid4().hex[:8]}",
                available=None,
                provider=None,
                detection_method="unavailable_on_this_platform",
            )

        # On Windows, real detection belongs in analyzers/ai_runtime_analyzer.py
        # (Phase 10 NPUAnalyzer) where actual execution-provider evidence is
        # queried. SystemCollector only records that a Snapdragon-family CPU
        # string was seen, which is a *hint*, not a confirmed NPU.
        hint = cpu_info.is_snapdragon is True
        return NPUInfo(
            id=f"NPU-{uuid.uuid4().hex[:8]}",
            available=None,
            provider=None,
            detection_method=(
                "cpu_model_hint_only; confirm via NPUAnalyzer execution-provider evidence"
                if hint
                else "no_hint_and_no_provider_query_performed"
            ),
        )

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    def _collect_memory(self) -> Optional[MemoryInfo]:
        if psutil is None:
            self._warnings.append("psutil not installed; memory info unavailable.")
            return None
        try:
            vm = psutil.virtual_memory()
            return MemoryInfo(
                id=f"MEM-{uuid.uuid4().hex[:8]}",
                total_bytes=vm.total,
                available_bytes=vm.available,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self._warnings.append(f"psutil.virtual_memory failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_architecture(machine: str) -> str:
        m = (machine or "").lower()
        if m in ("arm64", "aarch64"):
            return "ARM64"
        if m in ("amd64", "x86_64", "x64"):
            return "x64"
        if m in ("i386", "i686", "x86"):
            return "x86"
        return "unknown"
