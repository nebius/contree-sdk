from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contree_sdk.sdk.exceptions.base import ContreeError


@dataclass
class RequestInfo:
    url: str | None = None
    method: str | None = None


@dataclass
class ResponseInfo:
    headers: dict | None = None


@dataclass
class ContreeApiError(ContreeError):
    request: RequestInfo | None = None
    response: ResponseInfo | None = None


@dataclass
class ApiTimeoutError(ContreeApiError):
    timeout_type: Literal["connect", "read", "write", "pool"] | str | None = None


@dataclass
class ContreeTransportError(ContreeApiError):
    error: str | None = None
    _raw: Exception | None = None


@dataclass
class ApiStatusCodeError(ContreeApiError):
    status: int | None = None
    error: str | None = None


@dataclass
class NotFoundError(ApiStatusCodeError):
    status: int | None = 404


@dataclass
class TooManyRequestsError(ApiStatusCodeError):
    status: int | None = 429


@dataclass
class ForbiddenError(ApiStatusCodeError):
    status: int | None = 403
    _template = "You do not have permission to perform this action: {error}"


@dataclass
class UnprocessableEntityError(ApiStatusCodeError):
    status: int | None = 422


@dataclass
class TooEarlyError(ApiStatusCodeError):
    status: int | None = 425


@dataclass
class GoneError(ApiStatusCodeError):
    status: int | None = 410


@dataclass
class EventStreamError(ContreeApiError):
    pass


@dataclass
class MalformedEventError(EventStreamError):
    data: dict | None = None
    error: str | None = None
    _template = "SSE event cannot be parsed: {data} with error: {error}"


@dataclass
class EventStreamInterruptedError(EventStreamError):
    error: str | None = None
    _template = "Event stream was interrupted: {error}"
