from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from contree_sdk.sdk.managers.files._base import FilesBaseManager
    from contree_sdk.sdk.managers.images._base import ImagesBaseManager
    from contree_sdk.sdk.objects.image._base import ContreeImageBase


DEFAULT_OPERATION_TIMEOUT = 1000.0
DEFAULT_TRUNCATE_OUTPUT_AT = 65535
DEFAULT_IMAGES_LIST_BATCH_SIZE = 100


class ContreeBase:
    """Shared (non-IO) state for `ContreeSync`/`Contree`.

    Holds the injected `contree_client` backend and the small SDK-level
    defaults that used to live on the deleted `ContreeConfig`. All
    transport, retry and auth concerns belong to `client` now.
    """

    files: FilesBaseManager
    """Manager for file operations."""
    images: ImagesBaseManager[ContreeImageBase]
    """Manager for image operations."""

    def __init__(
        self,
        client: Any,
        *,
        operation_timeout: float = DEFAULT_OPERATION_TIMEOUT,
        operation_run_timeout: float | None = None,
        operation_import_timeout: float | None = None,
        images_list_batch_size: int = DEFAULT_IMAGES_LIST_BATCH_SIZE,
        default_truncate_output_at: int = DEFAULT_TRUNCATE_OUTPUT_AT,
    ) -> None:
        """Initialize the ConTree client.

        Args:
            client: An already-constructed `contree_client` backend
                (a `ContreeSyncClient`/`ContreeAsyncClient` implementation,
                e.g. from `contree_client.httpx`) that owns transport,
                retries and auth. contree_sdk performs no I/O of its own.
            operation_timeout: Default timeout (seconds) for operations.
            operation_run_timeout: Timeout for run operations; falls back to operation_timeout.
            operation_import_timeout: Timeout for import operations; falls back to operation_timeout.
            images_list_batch_size: Page size used when listing/iterating images.
            default_truncate_output_at: Default byte cap for stdout/stderr.

        """
        self.api = client
        self.operation_timeout = operation_timeout
        self.operation_run_timeout = operation_run_timeout
        self.operation_import_timeout = operation_import_timeout
        self.images_list_batch_size = images_list_batch_size
        self.default_truncate_output_at = default_truncate_output_at
