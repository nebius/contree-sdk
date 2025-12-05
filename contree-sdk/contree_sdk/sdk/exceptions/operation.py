from dataclasses import dataclass
from uuid import UUID

from contree_sdk.sdk.exceptions import ContreeException


@dataclass
class OperationError(ContreeException):
    operation_uuid: UUID

    _template = "Something went wrong with the operation {operation_uuid}"


@dataclass
class WrongOperationTypeError(OperationError):
    expected: type
    actual: type

    _template = "Wrong operation type {expected} != {actual}. Please report to SDK devs, should never happen."


@dataclass
class CancelledOperationError(OperationError):
    _template = "Operation {operation_uuid} was cancelled"


@dataclass
class FailedOperationError(OperationError):
    error: str
    _template = "Operation {operation_uuid} has failed"


@dataclass
class OperationTimedOutError(FailedOperationError):
    _template = "Operation {operation_uuid} has timed out"
