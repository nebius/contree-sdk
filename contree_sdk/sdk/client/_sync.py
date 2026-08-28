from __future__ import annotations

from types import TracebackType

from typing_extensions import Self

from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk._internals.utils.wrapper import coro_sync
from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.managers.files._sync import FilesManagerSync
from contree_sdk.sdk.managers.images._sync import ImagesManagerSync
from contree_sdk.utils.models.auth import WhoAmI


class ContreeSync(_ContreeBase):
    """Synchronous ConTree SDK client."""

    images: ImagesManagerSync
    files: FilesManagerSync

    _prefer_sync_transport = True

    @keep_signature(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManagerSync(client=self)
        self.files = FilesManagerSync(client=self)

    def get_token_info(self, refresh: bool = False) -> WhoAmI:
        return coro_sync(self._get_token_info(refresh=refresh))

    def close(self) -> None:
        """Close the transport used by the synchronous facade."""
        coro_sync(self._transport.aclose())

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
