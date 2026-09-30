"""
backend/analyzers/dll_resolver.py

Windows-aware DLL resolver.

Resolution order mirrors the Windows DLL loader search order for *safe search
mode* (which is the default since Windows XP SP2):

  1. KnownDLLs  – fast-path well-known system DLLs that bypass disk search.
                  We approximate this via a hardcoded set of the most common
                  names.  A future stage can consult the registry key
                  HKLM\\System\\CurrentControlSet\\Control\\Session Manager\\KnownDLLs.
  2. Application directory  – directory containing the importing binary.
  3. System32  – %SystemRoot%\System32
  4. SysWOW64  – %SystemRoot%\SysWOW64   (for 32-bit DLLs on 64-bit Windows)
  5. Windows directory  – %SystemRoot%
  6. Extra search paths  – caller-supplied list (configuration or test override)
  7. PATH  – entries in the PATH environment variable.

We do NOT search the Current Working Directory to avoid DLL planting false
positives.  We do NOT recurse into subdirectories.

The resolver is a pure Python class with no OS-level loading — it only does
filesystem probing.  It is designed to be injectable (pass a custom resolver
into DependencyAnalyzer) so tests can provide mock implementations.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from backend.models.common import EvidenceType, Provenance, SourceMechanism, utc_now
from backend.models.graph import DependencyResolution, ResolutionMethod, ResolutionStatus

# ---------------------------------------------------------------------------
# Heuristic: known system DLL basenames
# ---------------------------------------------------------------------------
# This list is intentionally conservative.  Adding every Windows DLL is not
# the goal; we just need a fast-path for the most ubiquitous names so we
# avoid opening them for architecture detection when analyze_system_dlls=False.

_KNOWN_SYSTEM_DLL_NAMES: frozenset[str] = frozenset(
    n.lower()
    for n in [
        # Core loader / CRT
        "ntdll.dll", "kernel32.dll", "kernelbase.dll", "msvcrt.dll",
        "ucrtbase.dll", "vcruntime140.dll", "vcruntime140_1.dll",
        "api-ms-win-crt-runtime-l1-1-0.dll",
        # Concurrency / sync
        "synchronization.dll",
        # User32 / GDI
        "user32.dll", "gdi32.dll", "gdi32full.dll", "win32u.dll",
        # COM / OLE
        "ole32.dll", "oleaut32.dll", "combase.dll",
        # Crypto / security
        "advapi32.dll", "crypt32.dll", "bcrypt.dll", "ncrypt.dll",
        "sechost.dll", "ntlmshared.dll",
        # Networking
        "ws2_32.dll", "wininet.dll", "winhttp.dll", "dnsapi.dll",
        "iphlpapi.dll",
        # Shell / UI
        "shell32.dll", "shlwapi.dll", "comctl32.dll", "comdlg32.dll",
        "uxtheme.dll",
        # Runtime support
        "rpcrt4.dll", "msvcr140.dll", "msvcp140.dll",
        # DirectX / media
        "d3d11.dll", "d3d12.dll", "dxgi.dll", "d2d1.dll", "dwrite.dll",
        "mf.dll", "mfplat.dll", "mfreadwrite.dll",
        # WinRT / modern
        "windows.storage.dll", "windows.ui.dll",
        # Imaging
        "windowscodecs.dll",
    ]
)


def _is_known_system_dll(name: str) -> bool:
    return name.lower() in _KNOWN_SYSTEM_DLL_NAMES


# ---------------------------------------------------------------------------
# Abstract resolver interface  (allows test injection)
# ---------------------------------------------------------------------------

class AbstractDLLResolver(ABC):
    @abstractmethod
    def resolve(
        self,
        name: str,
        importing_binary_path: str,
        extra_search_paths: Optional[list[str]] = None,
    ) -> DependencyResolution:
        ...


# ---------------------------------------------------------------------------
# Concrete Windows filesystem resolver
# ---------------------------------------------------------------------------

class DLLResolver(AbstractDLLResolver):
    """
    Resolves a DLL name to a filesystem path using a deterministic ordered
    search that approximates the Windows safe-search-mode DLL loader order.

    Parameters
    ----------
    system_root:
        Override for %SystemRoot% (default: ``os.environ.get("SystemRoot",
        "C:\\Windows")``).  Useful in tests.
    """

    def __init__(self, system_root: Optional[str] = None) -> None:
        self._system_root = system_root or os.environ.get("SystemRoot", r"C:\Windows")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        name: str,
        importing_binary_path: str,
        extra_search_paths: Optional[list[str]] = None,
    ) -> DependencyResolution:
        """
        Return a DependencyResolution for the requested DLL name.

        The caller supplies the path of the binary that declared the import
        so we can check the application directory first.
        """
        is_system = _is_known_system_dll(name)
        search_dirs = self._build_search_order(
            importing_binary_path, extra_search_paths or []
        )

        for directory, method in search_dirs:
            candidate = os.path.join(directory, name)
            # Case-insensitive match on Windows; exact match elsewhere.
            hit = self._probe(candidate)
            if hit:
                return DependencyResolution(
                    requested_name=name,
                    resolved_path=hit,
                    status=ResolutionStatus.RESOLVED,
                    method=method,
                    is_system_dll=is_system,
                    provenance=Provenance(
                        source=SourceMechanism.PE_STATIC_ANALYSIS,
                        evidence_type=EvidenceType.OBSERVED,
                        confidence=1.0,
                        detail=f"Found via {method.value}: {hit}",
                        timestamp=utc_now(),
                    ),
                )

        # Not found anywhere
        return DependencyResolution(
            requested_name=name,
            resolved_path=None,
            status=ResolutionStatus.MISSING,
            method=ResolutionMethod.UNKNOWN,
            is_system_dll=is_system,
            provenance=Provenance(
                source=SourceMechanism.PE_STATIC_ANALYSIS,
                evidence_type=EvidenceType.OBSERVED,
                confidence=1.0,
                detail=f"Not found in any search location ({len(search_dirs)} dirs searched).",
                timestamp=utc_now(),
            ),
            notes=[
                f"Searched {len(search_dirs)} directories; none contained '{name}'."
            ],
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_search_order(
        self,
        importing_binary_path: str,
        extra_search_paths: list[str],
    ) -> list[tuple[str, ResolutionMethod]]:
        """
        Build the ordered list of (directory, method) tuples to probe.
        """
        system32  = os.path.join(self._system_root, "System32")
        syswow64  = os.path.join(self._system_root, "SysWOW64")
        windir    = self._system_root
        app_dir   = os.path.dirname(os.path.abspath(importing_binary_path))

        order: list[tuple[str, ResolutionMethod]] = []

        # Extra paths first (caller override, highest priority after KnownDLLs)
        for p in extra_search_paths:
            order.append((p, ResolutionMethod.EXTRA_SEARCH))

        order.append((app_dir,   ResolutionMethod.APPLICATION_DIR))
        order.append((system32,  ResolutionMethod.SYSTEM32))
        order.append((syswow64,  ResolutionMethod.SYSWOW64))
        order.append((windir,    ResolutionMethod.WINDOWS_DIR))

        # PATH entries
        for p in os.environ.get("PATH", "").split(os.pathsep):
            if p:
                order.append((p, ResolutionMethod.PATH_ENV))

        return order

    @staticmethod
    def _probe(candidate: str) -> Optional[str]:
        """
        Return the canonical path if the file exists and is a regular file,
        else None.  On Windows, path probing is case-insensitive by the OS.
        """
        try:
            if os.path.isfile(candidate):
                return os.path.normpath(candidate)
        except OSError:
            pass
        return None
