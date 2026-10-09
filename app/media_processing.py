from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class MediaProcessingError(ValueError):
    """Raised when a processing request violates the fail-closed contract."""


class CapabilityAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    REQUIRES_DEPENDENCY = "requires_dependency"
    REQUIRES_HARDWARE = "requires_hardware"
    POLICY_BLOCKED = "policy_blocked"


class ProcessingState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaKind(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    SUBTITLE = "subtitle"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MediaAsset:
    asset_id: str
    sha256: str
    media_kind: MediaKind
    size_bytes: int
    relative_path: str

    def __post_init__(self) -> None:
        if not self.asset_id.strip():
            raise MediaProcessingError("asset_id is required")
        if len(self.sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.sha256.casefold()):
            raise MediaProcessingError("sha256 must be a 64-character hexadecimal digest")
        if self.size_bytes < 0:
            raise MediaProcessingError("size_bytes cannot be negative")
        if not self.relative_path.strip() or self.relative_path.startswith(("/", "\\")):
            raise MediaProcessingError("relative_path must be a non-empty relative path")
        normalized_parts = self.relative_path.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in normalized_parts):
            raise MediaProcessingError("relative_path cannot escape or ambiguously reference the media root")


@dataclass(frozen=True)
class MediaProcessingCapability:
    operation_id: str
    version: str
    accepted_inputs: tuple[MediaKind, ...]
    produced_kind: MediaKind | None
    availability: CapabilityAvailability
    dependency: str | None = None
    hardware: str | None = None
    note: str | None = None

    @property
    def executable(self) -> bool:
        return self.availability == CapabilityAvailability.AVAILABLE


@dataclass(frozen=True)
class ProcessingJob:
    job_id: str
    input_asset_id: str
    operation_id: str
    operation_version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise MediaProcessingError("job_id is required")
        if not self.input_asset_id.strip():
            raise MediaProcessingError("input_asset_id is required")
        if not self.operation_id.strip() or not self.operation_version.strip():
            raise MediaProcessingError("operation identity and version are required")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True)
class ProcessingReceipt:
    job_id: str
    state: ProcessingState
    input_asset_id: str
    input_sha256: str
    operation_id: str
    operation_version: str
    output_asset_id: str | None = None
    output_sha256: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.job_id,
                self.input_asset_id,
                self.input_sha256,
                self.operation_id,
                self.operation_version,
            )
        ):
            raise MediaProcessingError("receipt provenance fields are required")

        if self.state == ProcessingState.COMPLETED:
            if not self.output_asset_id or not self.output_sha256:
                raise MediaProcessingError("completed receipts require output identity and digest")
            if len(self.output_sha256) != 64:
                raise MediaProcessingError("completed receipt output digest must be sha256")
            if self.error_code:
                raise MediaProcessingError("completed receipts cannot contain an error_code")
        else:
            if self.output_asset_id or self.output_sha256:
                raise MediaProcessingError("non-completed receipts cannot claim a completed output")
            if self.state == ProcessingState.FAILED and not self.error_code:
                raise MediaProcessingError("failed receipts require an error_code")


@dataclass(frozen=True)
class BatchProcessingReceipt:
    batch_id: str
    items: tuple[ProcessingReceipt, ...]

    def __post_init__(self) -> None:
        if not self.batch_id.strip():
            raise MediaProcessingError("batch_id is required")
        if not self.items:
            raise MediaProcessingError("batch receipts require at least one item")
        job_ids = [item.job_id for item in self.items]
        if len(set(job_ids)) != len(job_ids):
            raise MediaProcessingError("batch receipt job_ids must be unique")

    @property
    def state(self) -> ProcessingState:
        states = {item.state for item in self.items}
        if states == {ProcessingState.COMPLETED}:
            return ProcessingState.COMPLETED
        if ProcessingState.RUNNING in states or ProcessingState.QUEUED in states:
            return ProcessingState.RUNNING
        if ProcessingState.FAILED in states:
            return ProcessingState.FAILED
        if states == {ProcessingState.CANCELLED}:
            return ProcessingState.CANCELLED
        return ProcessingState.FAILED


_CAPABILITIES = (
    MediaProcessingCapability(
        operation_id="probe",
        version="1",
        accepted_inputs=(MediaKind.AUDIO, MediaKind.VIDEO, MediaKind.IMAGE),
        produced_kind=None,
        availability=CapabilityAvailability.AVAILABLE,
        dependency="ffprobe",
        note="Metadata inspection only; no media mutation.",
    ),
    MediaProcessingCapability(
        operation_id="extract_audio",
        version="1",
        accepted_inputs=(MediaKind.VIDEO,),
        produced_kind=MediaKind.AUDIO,
        availability=CapabilityAvailability.REQUIRES_DEPENDENCY,
        dependency="ffmpeg",
    ),
    MediaProcessingCapability(
        operation_id="trim",
        version="1",
        accepted_inputs=(MediaKind.AUDIO, MediaKind.VIDEO),
        produced_kind=None,
        availability=CapabilityAvailability.REQUIRES_DEPENDENCY,
        dependency="ffmpeg",
    ),
    MediaProcessingCapability(
        operation_id="transcode",
        version="1",
        accepted_inputs=(MediaKind.AUDIO, MediaKind.VIDEO, MediaKind.IMAGE),
        produced_kind=None,
        availability=CapabilityAvailability.REQUIRES_DEPENDENCY,
        dependency="ffmpeg",
    ),
    MediaProcessingCapability(
        operation_id="transcribe",
        version="1",
        accepted_inputs=(MediaKind.AUDIO, MediaKind.VIDEO),
        produced_kind=MediaKind.SUBTITLE,
        availability=CapabilityAvailability.UNAVAILABLE,
        note="Owned ASR adapter is not implemented yet; integrate with Issue #20 rather than implying parity.",
    ),
    MediaProcessingCapability(
        operation_id="speaker_labels",
        version="1",
        accepted_inputs=(MediaKind.AUDIO, MediaKind.VIDEO),
        produced_kind=MediaKind.SUBTITLE,
        availability=CapabilityAvailability.REQUIRES_HARDWARE,
        hardware="certified local diarization runtime",
        note="No speaker identity recognition; anonymous labels only until a reviewed adapter exists.",
    ),
    MediaProcessingCapability(
        operation_id="privacy_blur",
        version="1",
        accepted_inputs=(MediaKind.VIDEO, MediaKind.IMAGE),
        produced_kind=None,
        availability=CapabilityAvailability.UNAVAILABLE,
        note="Advanced vision transform is intentionally deferred pending independent implementation and evaluation.",
    ),
    MediaProcessingCapability(
        operation_id="remove_watermark",
        version="1",
        accepted_inputs=(MediaKind.VIDEO, MediaKind.IMAGE),
        produced_kind=None,
        availability=CapabilityAvailability.POLICY_BLOCKED,
        note="Explicitly outside the authorized archive/product boundary.",
    ),
)

CAPABILITY_REGISTRY: Mapping[str, MediaProcessingCapability] = MappingProxyType(
    {capability.operation_id: capability for capability in _CAPABILITIES}
)


def get_processing_capability(operation_id: str) -> MediaProcessingCapability:
    key = (operation_id or "").strip().casefold()
    if not key:
        raise MediaProcessingError("operation_id is required")
    capability = CAPABILITY_REGISTRY.get(key)
    if capability is None:
        raise MediaProcessingError(f"Unknown media processing operation: {operation_id}")
    return capability


def plan_processing_job(
    *,
    job_id: str,
    input_asset: MediaAsset,
    operation_id: str,
    parameters: Mapping[str, Any] | None = None,
) -> ProcessingJob:
    capability = get_processing_capability(operation_id)
    if input_asset.media_kind not in capability.accepted_inputs:
        raise MediaProcessingError(
            f"Operation {capability.operation_id} does not accept {input_asset.media_kind.value} input"
        )
    if not capability.executable:
        raise MediaProcessingError(
            f"Operation {capability.operation_id} is not executable: {capability.availability.value}"
        )
    return ProcessingJob(
        job_id=job_id,
        input_asset_id=input_asset.asset_id,
        operation_id=capability.operation_id,
        operation_version=capability.version,
        parameters=parameters or {},
    )
