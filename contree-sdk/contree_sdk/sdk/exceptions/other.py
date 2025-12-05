from dataclasses import dataclass

from contree_sdk.sdk.exceptions import ContreeException


@dataclass
class UnknownContreeException(ContreeException):
    exception: Exception | None = None
