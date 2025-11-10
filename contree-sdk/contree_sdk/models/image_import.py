from enum import auto

from pydantic import BaseModel
from strenum import UppercaseStrEnum


class OperationStatus(UppercaseStrEnum):
    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()


class RegistryCredentials(BaseModel):
    username: str
    password: str


class RegistryInfo(BaseModel):
    url: str
    credentials: RegistryCredentials | None = None


class ImageImportRequest(BaseModel):
    registry: RegistryInfo
    tag: str | None = None
    timeout: int | None = None


class ImageImportOperation(BaseModel):
    status: OperationStatus
    result: str | None = None
    error: str | None = None
    metadata: ImageImportRequest | None = None
