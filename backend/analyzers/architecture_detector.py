"""
Architecture detection from PE/COFF headers.

Design rule: OBSERVATION vs INTERPRETATION must be explicit.

- DETECTED     – a single authoritative PE field unambiguously determines the
                 architecture.  One evidence item, confidence == 1.0.
- INFERRED     – the primary field is ambiguous and a secondary field is used
                 to resolve it.  ARM64EC is the canonical case: the COFF Machine
                 field says AMD64 (for x64 compat), but CHPEMetadataPointer in
                 the Load Config directory reveals the hybrid nature.
                 Confidence < 1.0 because pefile may not expose all CHPE fields
                 in all binary versions.
- UNCERTAIN    – insufficient / contradictory metadata; the returned Architecture
                 is the safest non-crashing guess.  Consumers MUST surface warnings.

ARM64EC detection notes
-----------------------
An ARM64EC linked PE typically carries Machine == IMAGE_FILE_MACHINE_AMD64
(0x8664) so it loads on x64 loaders.  The definitive discriminator is the
CHPEMetadataPointer field in the Load Configuration directory:
  - non-zero  → CHPE (Compiled Hybrid Portable Executable) metadata is present
                → binary contains ARM64EC code alongside x64 shims
  - zero / absent → standard AMD64 PE

pefile parses CHPEMetadataPointer when the Load Config structure is large
enough to contain it (generally true for binaries built with VS 2019+ on
Windows 10/11 SDKs).  If the field is not exposed by the current pefile
version, we cannot distinguish ARM64EC from x64 and must return UNCERTAIN.

We do NOT classify a binary as ARM64EC based on filename, folder, or any
non-PE signal.  If CHPEMetadataPointer is absent or zero we return x64 /
DETECTED (no CHPE evidence found) rather than guessing INFERRED.
"""

from __future__ import annotations

import pefile

from backend.models.common import (
    Architecture,
    ArchitectureClassification,
    ArchitectureEvidenceItem,
    ArchitectureResult,
    EvidenceType,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MACHINE_NAMES: dict[int, str] = {
    v: k for k, v in pefile.MACHINE_TYPE.items() if isinstance(k, str)
}


def _machine_name(value: int) -> str:
    return _MACHINE_NAMES.get(value, f"0x{value:04X}")


def _coff_evidence(machine_value: int) -> ArchitectureEvidenceItem:
    return ArchitectureEvidenceItem(
        source="COFF_FILE_HEADER",
        field="Machine",
        value=_machine_name(machine_value),
        evidence_type=EvidenceType.OBSERVED,
    )


def _chpe_evidence(pointer_value: int) -> ArchitectureEvidenceItem:
    return ArchitectureEvidenceItem(
        source="LOAD_CONFIG_DIRECTORY",
        field="CHPEMetadataPointer",
        value=hex(pointer_value),
        evidence_type=EvidenceType.OBSERVED,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_architecture(pe: pefile.PE) -> ArchitectureResult:
    """
    Inspect PE/COFF headers and return a structured ArchitectureResult.

    The caller is responsible for loading and parsing the PE; this function
    only reads already-parsed structures and never raises.
    """
    machine: int = pe.FILE_HEADER.Machine
    machine_str = _machine_name(machine)

    # ------------------------------------------------------------------
    # I386 – unambiguous single-field detection
    # ------------------------------------------------------------------
    if machine == pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_I386"]:
        return ArchitectureResult(
            architecture=Architecture.X86,
            classification=ArchitectureClassification.DETECTED,
            evidence=[_coff_evidence(machine)],
            confidence=1.0,
        )

    # ------------------------------------------------------------------
    # ARM64 (pure) – unambiguous single-field detection
    # ------------------------------------------------------------------
    if machine == pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_ARM64"]:
        return ArchitectureResult(
            architecture=Architecture.ARM64,
            classification=ArchitectureClassification.DETECTED,
            evidence=[_coff_evidence(machine)],
            confidence=1.0,
        )

    # ------------------------------------------------------------------
    # AMD64 – x64 or ARM64EC masquerading as x64
    # ------------------------------------------------------------------
    if machine == pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_AMD64"]:
        primary_evidence = _coff_evidence(machine)

        # Attempt to read CHPEMetadataPointer from the Load Config directory.
        # This is only available when pefile has parsed DIRECTORY_ENTRY_LOAD_CONFIG
        # and the binary's Load Config structure is large enough to contain it.
        chpe_ptr: int | None = None
        chpe_field_present = False

        if hasattr(pe, "DIRECTORY_ENTRY_LOAD_CONFIG"):
            lc = pe.DIRECTORY_ENTRY_LOAD_CONFIG
            if hasattr(lc, "struct") and hasattr(lc.struct, "CHPEMetadataPointer"):
                chpe_field_present = True
                chpe_ptr = lc.struct.CHPEMetadataPointer

        # Case 1: CHPE pointer observed and non-zero → ARM64EC (INFERRED)
        # We say INFERRED, not DETECTED, because:
        #   (a) we are combining two fields, not reading one authoritative field
        #   (b) CHPEMetadataPointer alone does not rule out future hybrid formats
        if chpe_field_present and chpe_ptr:
            return ArchitectureResult(
                architecture=Architecture.ARM64EC,
                classification=ArchitectureClassification.INFERRED,
                evidence=[primary_evidence, _chpe_evidence(chpe_ptr)],
                confidence=0.90,
                warnings=[
                    "ARM64EC classification is INFERRED from CHPEMetadataPointer "
                    "in the Load Configuration directory.  This is strong PE "
                    "evidence but does not rule out other future hybrid formats "
                    "(e.g. ARM64X).  Treat as ARM64EC unless a more specific "
                    "discriminator is available.",
                ],
            )

        # Case 2: Load Config present, CHPEMetadataPointer field present but zero
        # → standard x64, no hybrid code detected (DETECTED)
        if chpe_field_present and chpe_ptr == 0:
            return ArchitectureResult(
                architecture=Architecture.X64,
                classification=ArchitectureClassification.DETECTED,
                evidence=[primary_evidence, _chpe_evidence(0)],
                confidence=1.0,
            )

        # Case 3: Load Config not parsed or CHPEMetadataPointer field absent
        # → cannot distinguish x64 from ARM64EC; return x64 as safest default
        # but flag UNCERTAIN so consumers know the check could not be completed.
        warnings = [
            "CHPEMetadataPointer could not be read from the Load Configuration "
            "directory.  This may mean the binary was built without a Load Config "
            "table, pefile could not parse it, or the structure predates the "
            "CHPEMetadataPointer field.  ARM64EC cannot be ruled out.  "
            "Treating as x64 (safest default) with UNCERTAIN classification."
        ]
        if not hasattr(pe, "DIRECTORY_ENTRY_LOAD_CONFIG"):
            warnings.append("DIRECTORY_ENTRY_LOAD_CONFIG was not found in this binary.")
        else:
            warnings.append(
                "DIRECTORY_ENTRY_LOAD_CONFIG was found but CHPEMetadataPointer "
                "field is absent from the parsed structure (pefile version too "
                "old or Load Config too small)."
            )

        return ArchitectureResult(
            architecture=Architecture.X64,
            classification=ArchitectureClassification.UNCERTAIN,
            evidence=[primary_evidence],
            confidence=0.75,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Everything else – genuinely unknown
    # ------------------------------------------------------------------
    return ArchitectureResult(
        architecture=Architecture.UNKNOWN,
        classification=ArchitectureClassification.UNCERTAIN,
        evidence=[_coff_evidence(machine)],
        confidence=0.0,
        warnings=[
            f"Unrecognised Machine type: {machine_str} (raw={hex(machine)}).  "
            "Architecture cannot be determined."
        ],
    )
