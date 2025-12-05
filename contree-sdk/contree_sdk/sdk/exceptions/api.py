from dataclasses import dataclass

from contree_sdk.sdk.exceptions.base import ContreeException


@dataclass
class ContreeApiException(ContreeException): ...


@dataclass
class ApiTimeoutError(ContreeApiException): ...


@dataclass
class ContreeTransportError(ContreeApiException): ...


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
