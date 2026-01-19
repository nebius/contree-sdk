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
    status: int = 404


@dataclass
class ForbiddenError(ApiStatusCodeError):
    status: int = 403
    _template = "You do not have permission to perform this action"
