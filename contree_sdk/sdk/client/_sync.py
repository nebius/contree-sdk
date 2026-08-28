from __future__ import annotations

from contree_client.base import ContreeSyncClient

from contree_sdk.sdk.client._base import (
    DEFAULT_IMAGES_LIST_BATCH_SIZE,
    DEFAULT_OPERATION_TIMEOUT,
    DEFAULT_TRUNCATE_OUTPUT_AT,
    ContreeBase,
)
from contree_sdk.sdk.managers.files._sync import FilesManagerSync
from contree_sdk.sdk.managers.images._sync import ImagesManagerSync


class ContreeSync(ContreeBase):
    """Synchronous ConTree SDK client.

    `client` is any `contree_client.base.ContreeSyncClient` (e.g.
    `contree_client.httpx.ContreeClient`); contree_sdk never builds one
    itself, so callers control transport, retries and auth.
    """

    images: ImagesManagerSync
    files: FilesManagerSync

    def __init__(
        self,
        client: ContreeSyncClient,
        *,
        operation_timeout: float = DEFAULT_OPERATION_TIMEOUT,
        operation_run_timeout: float | None = None,
        operation_import_timeout: float | None = None,
        images_list_batch_size: int = DEFAULT_IMAGES_LIST_BATCH_SIZE,
        default_truncate_output_at: int = DEFAULT_TRUNCATE_OUTPUT_AT,
    ) -> None:
        super().__init__(
            client,
            operation_timeout=operation_timeout,
            operation_run_timeout=operation_run_timeout,
            operation_import_timeout=operation_import_timeout,
            images_list_batch_size=images_list_batch_size,
            default_truncate_output_at=default_truncate_output_at,
        )
        self.images = ImagesManagerSync(client=self)
        self.files = FilesManagerSync(client=self)
