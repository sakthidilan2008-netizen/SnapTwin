"""
tests/test_pe_analyzer.py

Stage 2 hardening-pass tests.  Covers:
  - error handling (missing file, directory, malformed/non-PE)
  - architecture detection: x64, x86
  - classification field (DETECTED / INFERRED / UNCERTAIN)
  - evidence provenance (source, field, value present and correct)
  - uncertainty / warnings surfaced when expected
  - ARM64 / ARM64EC tests explicitly skipped (no real fixture available)
"""

import os
import struct

import pefile
import pytest

from backend.analyzers.pe_analyzer import PEAnalyzer
from backend.models.common import Architecture, ArchitectureClassification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analyze(path: str):
    return PEAnalyzer().analyze(path)


def _arch_result_raw(analysis):
    """Pull the raw ArchitectureResult dict stored in Provenance.raw."""
    return analysis.identity.architecture_provenance.raw


# ---------------------------------------------------------------------------
# Error-handling tests (unchanged from Stage 2)
# ---------------------------------------------------------------------------

def test_missing_file():
    result = _analyze("C:/path/does/not/exist.exe")
    assert not result.analysis_complete
    assert any("File not found" in e for e in result.analyzer_errors)


def test_directory_instead_of_file(tmp_path):
    result = _analyze(str(tmp_path))
    assert not result.analysis_complete
    assert any("Path is a directory" in e for e in result.analyzer_errors)


def test_non_pe_file(tmp_path):
    fpath = tmp_path / "notape.txt"
    fpath.write_text("This is not a PE file")
    result = _analyze(str(fpath))
    assert not result.analysis_complete
    assert any("Malformed PE file" in e for e in result.analyzer_errors)


def test_malformed_pe_truncated(tmp_path):
    """A file that starts with MZ but is truncated before a valid PE header."""
    fpath = tmp_path / "truncated.exe"
    # MZ signature only — no real PE offset or headers
    fpath.write_bytes(b"MZ" + b"\x00" * 60)
    result = _analyze(str(fpath))
    assert not result.analysis_complete
    assert any("Malformed PE file" in e for e in result.analyzer_errors)


# ---------------------------------------------------------------------------
# x64 detection: architecture, classification, evidence, provenance
# ---------------------------------------------------------------------------

@pytest.fixture
def x64_path():
    """Find a genuine AMD64 PE fixture instead of assuming System32 is x64."""
    import shutil

    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        os.path.join(windir, "System32", "cmd.exe"),
        os.path.join(windir, "SysWOW64", "cmd.exe"),
        os.path.join(windir, "Sysnative", "cmd.exe"),
    ]
    path_cmd = shutil.which("cmd.exe")
    if path_cmd:
        candidates.append(path_cmd)

    seen = set()
    for path in candidates:
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen or not os.path.isfile(path):
            continue
        seen.add(normalized)
        try:
            pe = pefile.PE(path, fast_load=True)
            machine = pe.FILE_HEADER.Machine
            pe.close()
            if machine == 0x8664:  # IMAGE_FILE_MACHINE_AMD64 observed in the PE header.
                return path
        except (OSError, pefile.PEFormatError):
            continue
    pytest.skip("No genuine x64 (IMAGE_FILE_MACHINE_AMD64) PE fixture is available on this host")


def test_x64_architecture(x64_path):
    result = _analyze(x64_path)
    assert result.analysis_complete
    assert result.identity.architecture == Architecture.X64


def test_x64_classification_is_detected_or_uncertain(x64_path):
    """
    On a standard x64 Windows host cmd.exe is a plain AMD64 binary.
    If pefile successfully parses Load Config with a zero CHPEMetadataPointer
    it returns DETECTED.  If Load Config is absent/unparseable it returns
    UNCERTAIN (still x64, but annotated honestly).  Both are valid.
    """
    result = _analyze(x64_path)
    raw = _arch_result_raw(result)
    assert raw["classification"] in (
        ArchitectureClassification.DETECTED.value,
        ArchitectureClassification.UNCERTAIN.value,
    ), f"Unexpected classification: {raw['classification']}"


def test_x64_evidence_contains_coff_field(x64_path):
    result = _analyze(x64_path)
    raw = _arch_result_raw(result)
    coff_items = [e for e in raw["evidence"] if e["source"] == "COFF_FILE_HEADER"]
    assert coff_items, "No COFF_FILE_HEADER evidence item"
    assert coff_items[0]["field"] == "Machine"
    assert "AMD64" in coff_items[0]["value"]


def test_x64_provenance_attached(x64_path):
    result = _analyze(x64_path)
    prov = result.identity.architecture_provenance
    assert prov is not None
    assert prov.source.value == "pe_static_analysis"
    assert prov.evidence_type.value == "observed"
    assert 0.0 < prov.confidence <= 1.0


def test_x64_warnings_surfaced_when_uncertain(x64_path):
    """
    If classification is UNCERTAIN, warnings must propagate to
    analysis.analyzer_warnings.  If DETECTED, no architecture warnings needed.
    """
    result = _analyze(x64_path)
    raw = _arch_result_raw(result)
    if raw["classification"] == ArchitectureClassification.UNCERTAIN.value:
        assert any("[architecture]" in w for w in result.analyzer_warnings), (
            "UNCERTAIN classification must surface warnings in analyzer_warnings"
        )
    else:
        # DETECTED → raw warnings list should be empty
        assert raw["warnings"] == []


# ---------------------------------------------------------------------------
# x86 detection: architecture, classification, evidence
# ---------------------------------------------------------------------------

@pytest.fixture
def x86_path():
    path = r"C:\Windows\SysWOW64\cmd.exe"
    if not os.path.exists(path):
        pytest.skip("x86 fixture not available on this host")
    return path


def test_x86_architecture(x86_path):
    result = _analyze(x86_path)
    assert result.analysis_complete
    assert result.identity.architecture == Architecture.X86


def test_x86_classification_is_detected(x86_path):
    """
    x86 is unambiguous: IMAGE_FILE_MACHINE_I386 is a single authoritative
    field with no secondary check needed.  Must always be DETECTED.
    """
    result = _analyze(x86_path)
    raw = _arch_result_raw(result)
    assert raw["classification"] == ArchitectureClassification.DETECTED.value


def test_x86_evidence_contains_i386(x86_path):
    result = _analyze(x86_path)
    raw = _arch_result_raw(result)
    coff_items = [e for e in raw["evidence"] if e["source"] == "COFF_FILE_HEADER"]
    assert coff_items, "No COFF_FILE_HEADER evidence item"
    assert "I386" in coff_items[0]["value"]


def test_x86_no_warnings(x86_path):
    """x86 (DETECTED) must produce no architecture warnings."""
    result = _analyze(x86_path)
    raw = _arch_result_raw(result)
    assert raw["warnings"] == []
    assert not any("[architecture]" in w for w in result.analyzer_warnings)


def test_x86_confidence_is_1_0(x86_path):
    result = _analyze(x86_path)
    assert result.identity.architecture_provenance.confidence == 1.0


# ---------------------------------------------------------------------------
# ARM64 / ARM64EC – skipped, real fixtures required
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "Requires a genuine ARM64 PE fixture from a Windows/ARM device. "
        "Do not fabricate ARM64 test binaries."
    )
)
def test_arm64_pe():
    pass


@pytest.mark.skip(
    reason=(
        "Requires a genuine ARM64EC PE fixture from a Windows/ARM device. "
        "ARM64EC detection is INFERRED (CHPEMetadataPointer) and must be "
        "validated against a real binary, not a fabricated one."
    )
)
def test_arm64ec_pe():
    pass
