"""
PEAnalyzer – Stage 2 PE / binary static analysis.

Analyzes a single EXE or DLL and returns an ApplicationAnalysis.
Does NOT recurse into dependencies (that is Stage 3).

Every architecture observation is stored with full provenance via
ArchitectureResult so callers can distinguish:
  DETECTED  – directly read from one authoritative PE field
  INFERRED  – derived from a combination of fields (e.g. ARM64EC via CHPE)
  UNCERTAIN – metadata insufficient; classification is best-safe-guess only

Handles gracefully (no crash):
  - missing file
  - directory path
  - unreadable file
  - malformed / truncated PE
  - any other unexpected parsing exception
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone

import pefile

from backend.analyzers.architecture_detector import detect_architecture
from backend.models.application import ApplicationAnalysis, ApplicationIdentity
from backend.models.common import (
    EvidenceType,
    Provenance,
    SourceMechanism,
)


class PEAnalyzer:
    def analyze(self, path: str) -> ApplicationAnalysis:
        app_id = str(uuid.uuid4())
        analysis_id = str(uuid.uuid4())

        identity = ApplicationIdentity(
            id=app_id,
            display_name=os.path.basename(path),
            exe_path=path,
        )
        analysis = ApplicationAnalysis(id=analysis_id, identity=identity)

        # ------------------------------------------------------------------
        # Pre-flight path checks
        # ------------------------------------------------------------------
        if not os.path.exists(path):
            analysis.analyzer_errors.append(f"File not found: {path}")
            return analysis

        if os.path.isdir(path):
            analysis.analyzer_errors.append(f"Path is a directory: {path}")
            return analysis

        # ------------------------------------------------------------------
        # Read raw bytes + hash
        # ------------------------------------------------------------------
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            identity.file_size_bytes = len(data)
            identity.exe_sha256 = hashlib.sha256(data).hexdigest()
        except Exception as exc:
            analysis.analyzer_errors.append(f"Could not read file: {exc}")
            return analysis

        # ------------------------------------------------------------------
        # Parse PE structure
        # ------------------------------------------------------------------
        try:
            pe = pefile.PE(data=data, fast_load=True)
            pe.parse_data_directories(
                directories=[
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG"],
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"],
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"],
                ]
            )
        except Exception as exc:
            analysis.analyzer_errors.append(f"Malformed PE file: {exc}")
            return analysis

        # ------------------------------------------------------------------
        # Extract all PE metadata (each block is isolated so one failure
        # does not abort everything else)
        # ------------------------------------------------------------------
        try:
            self._extract_architecture(pe, identity, analysis)
        except Exception as exc:  # pragma: no cover
            analysis.analyzer_errors.append(f"Architecture extraction failed: {exc}")

        try:
            self._extract_pe_header(pe, identity)
        except Exception as exc:  # pragma: no cover
            analysis.analyzer_warnings.append(f"PE header extraction incomplete: {exc}")

        try:
            self._extract_imports(pe, analysis)
        except Exception as exc:  # pragma: no cover
            analysis.analyzer_warnings.append(f"Import extraction incomplete: {exc}")

        try:
            self._extract_security(pe, identity)
        except Exception as exc:  # pragma: no cover
            analysis.analyzer_warnings.append(f"Security directory check incomplete: {exc}")

        try:
            self._extract_manifest(pe, identity)
        except Exception as exc:  # pragma: no cover
            analysis.analyzer_warnings.append(f"Manifest extraction incomplete: {exc}")

        analysis.analysis_complete = True
        return analysis

    # ------------------------------------------------------------------
    # Private extraction helpers
    # ------------------------------------------------------------------

    def _extract_architecture(
        self,
        pe: pefile.PE,
        identity: ApplicationIdentity,
        analysis: ApplicationAnalysis,
    ) -> None:
        arch_result = detect_architecture(pe)

        identity.architecture = arch_result.architecture

        # Serialize the full ArchitectureResult into the Provenance.raw field
        # so it is available to every downstream consumer without re-parsing.
        identity.architecture_provenance = Provenance(
            source=SourceMechanism.PE_STATIC_ANALYSIS,
            evidence_type=EvidenceType.OBSERVED,
            confidence=arch_result.confidence,
            detail=(
                f"classification={arch_result.classification.value}; "
                f"evidence_fields={[e.field for e in arch_result.evidence]}"
            ),
            raw={
                "architecture": arch_result.architecture.value,
                "classification": arch_result.classification.value,
                "evidence": [e.model_dump() for e in arch_result.evidence],
                "confidence": arch_result.confidence,
                "warnings": arch_result.warnings,
            },
        )

        # Promote architecture warnings into the analysis-level warning list
        # so they surface to any caller inspecting analysis.analyzer_warnings.
        for w in arch_result.warnings:
            analysis.analyzer_warnings.append(f"[architecture] {w}")

    def _extract_pe_header(
        self,
        pe: pefile.PE,
        identity: ApplicationIdentity,
    ) -> None:
        identity.machine_type_raw = hex(pe.FILE_HEADER.Machine)

        if hasattr(pe, "OPTIONAL_HEADER") and hasattr(pe.OPTIONAL_HEADER, "Subsystem"):
            sub_id = pe.OPTIONAL_HEADER.Subsystem
            identity.subsystem = pefile.SUBSYSTEM_TYPE.get(sub_id, f"UNKNOWN_{sub_id}")

        ts = pe.FILE_HEADER.TimeDateStamp
        if ts != 0:
            try:
                identity.pe_timestamp = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).isoformat()
            except (OSError, OverflowError, ValueError):
                identity.pe_timestamp = str(ts)

    def _extract_imports(
        self,
        pe: pefile.PE,
        analysis: ApplicationAnalysis,
    ) -> None:
        if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                dll = entry.dll.decode("utf-8", errors="replace") if entry.dll else "UNKNOWN"
                analysis.imports.append(dll)

        if hasattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for entry in pe.DIRECTORY_ENTRY_DELAY_IMPORT:
                dll = entry.dll.decode("utf-8", errors="replace") if entry.dll else "UNKNOWN"
                analysis.delay_imports.append(dll)

    def _extract_security(
        self,
        pe: pefile.PE,
        identity: ApplicationIdentity,
    ) -> None:
        if not (hasattr(pe, "OPTIONAL_HEADER") and hasattr(pe.OPTIONAL_HEADER, "DATA_DIRECTORY")):
            identity.is_signed = False
            return
        sec = pe.OPTIONAL_HEADER.DATA_DIRECTORY[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_SECURITY"]
        ]
        identity.is_signed = sec.VirtualAddress != 0 and sec.Size != 0

    def _extract_manifest(
        self,
        pe: pefile.PE,
        identity: ApplicationIdentity,
    ) -> None:
        if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
            identity.manifest_present = False
            return
        rt_manifest_id = pefile.RESOURCE_TYPE.get("RT_MANIFEST", 24)
        for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if entry.id == rt_manifest_id:
                identity.manifest_present = True
                identity.manifest_summary = "Manifest resource present (RT_MANIFEST)"
                return
        identity.manifest_present = False
