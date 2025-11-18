from dataclasses import dataclass
from enum import auto

from strenum import UppercaseStrEnum


class OperationStatus(UppercaseStrEnum):
    PENDING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    ASSIGNED = auto()


@dataclass
class RegistryCredentials:
    username: str
    password: str


@dataclass
class RegistryInfo:
    url: str
    credentials: RegistryCredentials | None = None


@dataclass
class ImageImportRequest:
    registry: RegistryInfo
    tag: str | None = None
    timeout: int | None = None


@dataclass
class ImageImportOperation:
    status: OperationStatus
    result: str | None = None
    error: str | None = None
    metadata: ImageImportRequest | None = None
