from enum import auto

from strenum import UppercaseStrEnum


class OperationStatus(UppercaseStrEnum):
    ASSIGNED = auto()
    PENDING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
