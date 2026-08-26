from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from contree_sdk.sdk.client._base import ContreeBase


class BaseManager:
    def __init__(self, client: ContreeBase):
        self.client = client
