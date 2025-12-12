from dataclasses import dataclass
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
