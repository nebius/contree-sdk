from __future__ import annotations

from types import TracebackType

from typing_extensions import Self

from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.managers.files._async import FilesManager
from contree_sdk.sdk.managers.images._async import ImagesManager
from contree_sdk.utils.models.auth import WhoAmI


class Contree(_ContreeBase):
    """Asynchronous ConTree SDK client."""

    files: FilesManager
    images: ImagesManager

    @keep_signature(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManager(client=self)
        self.files = FilesManager(client=self)

    async def get_token_info(self, refresh: bool = False) -> WhoAmI:
        return await self._get_token_info(refresh=refresh)

    async def aclose(self) -> None:
        """Close the transport associated with the current event loop."""
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
