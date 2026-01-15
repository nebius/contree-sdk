from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contree_sdk.sdk.exceptions.base import ContreeException


@dataclass
class RequestInfo:
    url: str | None = None
    method: str | None = None


@dataclass
class ResponseInfo:
    headers: dict | None = None


@dataclass
class ContreeApiException(ContreeException):
    request: RequestInfo | None = None
    response: ResponseInfo | None = None


@dataclass
class ApiTimeoutError(ContreeApiException):
    timeout_type: Literal["connect", "read", "write", "pool"] | str | None = None


@dataclass
class ContreeTransportError(ContreeApiException):
    error: str | None = None
    _raw: Exception | None = None


@dataclass
class ApiStatusCodeError(ContreeApiException):
    status: int | None = None
    error: str | None = None


@dataclass
class NotFoundError(ApiStatusCodeError):
    status: int = 404


@dataclass
class ForbiddenError(ApiStatusCodeError):
    status: int = 403
    _template = "You do not have permission to perform this action"
