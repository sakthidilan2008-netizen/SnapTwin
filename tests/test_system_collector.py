"""
Stage 1 tests: models import/validate cleanly, and SystemCollector produces
a well-formed, honest SystemSnapshot on whatever platform the tests run on
(this container is Linux, so we assert the *shape* and the *honesty*
guarantees — e.g. GPU/NPU fields degrading to None with warnings — rather
than asserting Windows-only values).
"""

from __future__ import annotations

import re
import sys

sys.path.insert(0, "backend")

import pytest

from collectors.system_collector import SystemCollector
from models.common import Architecture, EvidenceType, SourceMechanism
from models.telemetry import SystemSnapshot


def test_system_collector_returns_system_snapshot():
    snapshot = SystemCollector().collect()
    assert isinstance(snapshot, SystemSnapshot)


def test_os_architecture_is_normalized_enum_value():
    snapshot = SystemCollector().collect()
    assert snapshot.os.architecture in {"ARM64", "x64", "x86", "unknown"}


def test_cpu_architecture_matches_os_architecture_family():
    snapshot = SystemCollector().collect()
    # On a given host, CPU and OS-reported machine architecture should agree.
    assert snapshot.cpu.architecture == snapshot.os.architecture


def test_provenance_is_attached_and_observed():
    snapshot = SystemCollector().collect()
    assert snapshot.collected_via.evidence_type == EvidenceType.OBSERVED
    assert snapshot.collected_via.source == SourceMechanism.SYSTEM_INFO
    assert 0.0 <= snapshot.collected_via.confidence <= 1.0


def test_is_snapdragon_is_never_hardcoded_true_without_evidence():
    snapshot = SystemCollector().collect()
    model = snapshot.cpu.model
    if model:
        has_snapdragon_evidence = re.search(
            r"(snapdragon|qualcomm|oryon)", model, re.IGNORECASE
        ) is not None
        assert snapshot.cpu.is_snapdragon is has_snapdragon_evidence
    else:
        assert snapshot.cpu.is_snapdragon is None


def test_gpu_and_npu_degrade_honestly_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    collector = SystemCollector()
    snapshot = collector.collect()
    # GPU should be None (not fabricated) off Windows.
    assert snapshot.gpu is None
    # NPU should report available=None (unknown) rather than guessing True/False.
    assert snapshot.npu is not None
    assert snapshot.npu.available is None
    assert any("unavailable" in w.lower() or "not available" in w.lower() for w in snapshot.collector_warnings)


def test_memory_info_present_when_psutil_available():
    snapshot = SystemCollector().collect()
    # psutil is a declared dependency, so this should be populated in CI/dev.
    assert snapshot.memory is not None
    assert snapshot.memory.total_bytes is not None
    assert snapshot.memory.total_bytes > 0


def test_snapshot_serializes_to_json_round_trip():
    snapshot = SystemCollector().collect()
    payload = snapshot.model_dump_json()
    restored = SystemSnapshot.model_validate_json(payload)
    assert restored.id == snapshot.id
    assert restored.cpu.architecture == snapshot.cpu.architecture


def test_normalize_architecture_helper_covers_known_machine_strings():
    normalize = SystemCollector._normalize_architecture
    assert normalize("AMD64") == "x64"
    assert normalize("x86_64") == "x64"
    assert normalize("aarch64") == "ARM64"
    assert normalize("ARM64") == "ARM64"
    assert normalize("i686") == "x86"
    assert normalize("riscv64") == "unknown"
    assert normalize("") == "unknown"
