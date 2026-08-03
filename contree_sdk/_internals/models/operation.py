from dataclasses import dataclass
from datetime import datetime
from enum import auto

from strenum import LowercaseStrEnum

from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk._internals.models.instance import InstanceOperationMetadata, InstanceOperationResult
from contree_sdk.utils.models.operation import OperationStatus


class OperationKind(LowercaseStrEnum):
    IMAGE_IMPORT = auto()
    INSTANCE = auto()


@dataclass
class OperationModel:
    kind: OperationKind
    status: OperationStatus
    duration: float
    error: str | None = None
    metadata: InstanceOperationMetadata | ImageImportRequest | None = None
    result: InstanceOperationResult | None = None


class OperationEventType(LowercaseStrEnum):
    INIT = auto()
    SPAWN = auto()
    STDIN = auto()
    STDOUT = auto()
    STDERR = auto()
    EXIT = auto()
    TRUNCATED = auto()
    SIZE_CAP = auto()
    NETWORK = auto()
    SHUTDOWN = auto()
    COMPLETION = auto()


@dataclass
class OperationEvent:
    id: int
    ts: datetime
    type: OperationEventType
    data: dict
    spid: int | None = None


@dataclass
class EventDataCompletion:
    status: OperationStatus
    duration_ms: int
    result_image_uuid: str | None = None
    error: str | None = None


@dataclass
class EventDataExit:
    code: int
    duration_ms: int
    pid: int
    timed_out: bool
    resources: dict


@dataclass
class EventDataTruncated:
    stream: str
    bytes_emitted: int
    bytes_dropped: int
