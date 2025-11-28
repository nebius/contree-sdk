from dataclasses import dataclass
from enum import auto

from strenum import LowercaseStrEnum, UppercaseStrEnum

from contree_sdk.api.models.image_import import ImageImportRequest
from contree_sdk.api.models.instance import InstanceOperationMetadata, InstanceOperationResult


class OperationKind(LowercaseStrEnum):
    IMAGE_IMPORT = auto()
    INSTANCE = auto()


class OperationStatus(UppercaseStrEnum):
    ASSIGNED = auto()
    PENDING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class OperationModel:
    kind: OperationKind
    status: OperationStatus
    duration: float
    error: str | None = None
    metadata: InstanceOperationMetadata | ImageImportRequest | None = None
    result: InstanceOperationResult | None = None
