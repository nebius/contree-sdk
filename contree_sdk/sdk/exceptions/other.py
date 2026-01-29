from dataclasses import dataclass

from contree_sdk.sdk.exceptions import ContreeError


@dataclass
class UnknownContreeError(ContreeError):
    exception: Exception | None = None
