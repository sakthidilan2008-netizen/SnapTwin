from backend.collectors.capability_collector import CapabilityCollector
from backend.models.capability import CapabilityStatus


def test_capability_profile_has_observed_host_and_provenance():
    profile = CapabilityCollector().collect()
    assert profile.host_architecture.provenance is not None
    assert profile.cpu.provenance is not None
    assert profile.host_architecture.status in {
        CapabilityStatus.VERIFIED, CapabilityStatus.UNKNOWN
    }


def test_arm64_is_not_inferred_as_snapdragon(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "ARM64")
    monkeypatch.setattr("platform.processor", lambda: "Generic ARM processor")
    profile = CapabilityCollector().collect()
    assert profile.host_architecture.status == CapabilityStatus.VERIFIED
    assert profile.qualcomm.status != CapabilityStatus.VERIFIED
    assert profile.snapdragon.status != CapabilityStatus.VERIFIED


def test_missing_tool_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    tool = CapabilityCollector()._tool("clang", "clang.exe")
    assert tool.status == CapabilityStatus.UNAVAILABLE
    assert tool.path is None
    assert tool.provenance is not None


def test_known_tool_is_detected(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "C:/tools/" + name)
    monkeypatch.setattr(
        "backend.collectors.capability_collector.CapabilityCollector._version",
        staticmethod(lambda _: "test-version"),
    )
    tool = CapabilityCollector()._tool("clang", "clang.exe")
    assert tool.status == CapabilityStatus.VERIFIED
    assert tool.path == "C:/tools/clang.exe"
    assert tool.version == "test-version"


def test_unavailable_gpu_and_npu_are_not_fabricated():
    profile = CapabilityCollector().collect()
    assert profile.gpu.status != CapabilityStatus.VERIFIED
    assert profile.npu.status != CapabilityStatus.VERIFIED
