from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import TypeVar

from contree_sdk.api.client.client import ContreeClient
from contree_sdk.config import ContreeConfig


if TYPE_CHECKING:
    from contree_sdk.sdk.managers.files._base import _FilesBaseManager
    from contree_sdk.sdk.managers.images._base import _ImagesBaseManager

_OperationResultT = TypeVar("_OperationResultT")


class _ContreeBase:
    files: _FilesBaseManager
    images: _ImagesBaseManager

    def __init__(self, config: ContreeConfig | None = None, *, token: str | None = None):
        if config is None:
            config = ContreeConfig(
                token=token,
            )
        else:
            assert token is None, "config is not empty, token should not be specifed"

        self._api = self._create_api_client(config)

    def _create_api_client(self, config: ContreeConfig):
        return ContreeClient(
            token=config.token,
            base_url=config.base_url,
        )

    async def _wait_operation(
        self, operation_uuid: UUID | str, result_type: type[_OperationResultT]
    ) -> _OperationResultT:
        pass  # todo
