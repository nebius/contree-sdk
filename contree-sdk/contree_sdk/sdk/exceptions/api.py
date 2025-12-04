from dataclasses import dataclass

from contree_sdk.sdk.exceptions.base import ContreeException


@dataclass
class ContreeApiException(ContreeException): ...


@dataclass
class ApiTimeoutError(ContreeApiException): ...


@dataclass
class ContreeTransportError(ContreeApiException): ...
