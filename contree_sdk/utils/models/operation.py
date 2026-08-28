from enum import auto

from strenum import LowercaseStrEnum, UppercaseStrEnum


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


class OperationStatus(UppercaseStrEnum):
    ASSIGNED = auto()
    PENDING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
