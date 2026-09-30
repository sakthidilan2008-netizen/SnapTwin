"""Typed environment capability facts for MVP-1."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .common import Provenance, SnapTwinBaseModel


class CapabilityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PRESENT_BUT_UNVERIFIED = "PRESENT_BUT_UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class CapabilityFact(SnapTwinBaseModel):
    status: CapabilityStatus
    provenance: Provenance
    detail: Optional[str] = None


class ToolCapability(CapabilityFact):
    path: Optional[str] = None
    version: Optional[str] = None


class HardwareCapability(CapabilityFact):
    name: Optional[str] = None
    vendor: Optional[str] = None
    information: Optional[str] = None


class CapabilityProfile(SnapTwinBaseModel):
    host_architecture: CapabilityFact
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    os_build: Optional[str] = None

    cpu: HardwareCapability
    physical_cores: Optional[int] = None
    logical_cores: Optional[int] = None

    qualcomm: CapabilityFact
    snapdragon: CapabilityFact

    msvc: ToolCapability
    linker: ToolCapability
    clang: ToolCapability
    clang_cl: ToolCapability
    cmake: ToolCapability
    windows_sdk: ToolCapability
    visual_studio: ToolCapability

    x64_execution: CapabilityFact
    arm64_execution: CapabilityFact
    arm64ec_execution: CapabilityFact
    arm64_compilation: CapabilityFact
    arm64ec_compilation: CapabilityFact

    gpu: HardwareCapability
    npu: HardwareCapability

    warnings: list[str] = Field(default_factory=list)
