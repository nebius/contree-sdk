from __future__ import annotations

import logging
from asyncio import Lock
from dataclasses import replace
from datetime import timedelta
from functools import partial
from time import time
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import TypeVar

from contree_sdk._internals.client.client import ContreeClient
from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk._internals.models.instance import InstanceSpawnRequest
from contree_sdk._internals.models.operation import EventDataCompletion, EventDataExit
from contree_sdk._internals.utils.circuit_retrier import CircuitRetrier
from contree_sdk._internals.utils.operation_waiter import OperationWaiter
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions.api import ApiTimeoutError, EventStreamError, TooManyRequestsError
from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.utils.models.auth import WhoAmI


if TYPE_CHECKING:
    from contree_sdk.sdk.managers.files._base import _FilesBaseManager
    from contree_sdk.sdk.managers.images._base import _ImagesBaseManager

_OperationResultT = TypeVar("_OperationResultT")

logger = logging.getLogger(__name__)


class _ContreeBase:
    files: _FilesBaseManager
    """Manager for file operations."""
    images: _ImagesBaseManager[_ContreeImageBase]
    """Manager for image operations."""

    def __init__(self, config: ContreeConfig | None = None, *, base_url: str | None = None, token: str | None = None):
        """Initialize the ConTree client.

        Args:
            config: Full configuration object. If provided, base_url and token
                must not be passed separately.
            base_url: API server URL shorthand. Ignored if config is provided.
            token: Authentication token shorthand. Ignored if config is provided.

        Raises:
            ValueError: If config is provided along with base_url or token.

        """
        if config is None:
            if token is not None or base_url is not None:
                auth = IAMAuth()
                if token is not None:
                    auth = replace(auth, token=token)
                if base_url is not None:
                    auth = replace(auth, base_url=base_url)
                config = ContreeConfig(auth=auth)
            else:
                config = ContreeConfig()
        else:
            if token is not None:
                raise ValueError("token must be passed via config when config is provided")
            if base_url is not None:
                raise ValueError("base_url must be passed via config when config is provided")

        config = replace(config, auth=config.auth.resolve())

        self._api: ContreeClient = self._create_api_client(config)
        self._config = config
        self._token_info: WhoAmI | None = None
        exceptions = [TooManyRequestsError, ApiTimeoutError, EventStreamError]
        import_timeout = config.operation_import_timeout or config.operation_timeout
        spawn_timeout = config.operation_run_timeout or config.operation_timeout
        self._operations = {
            ImageImportRequest: (
                self._api.start_import_image,
                CircuitRetrier(exceptions=exceptions, retry_timeout=timedelta(seconds=import_timeout)),
            ),
            InstanceSpawnRequest: (
                self._api.spawn_instance,
                CircuitRetrier(exceptions=exceptions, retry_timeout=timedelta(seconds=spawn_timeout)),
            ),
        }
        self._default_retrier = CircuitRetrier(
            exceptions=exceptions, retry_timeout=timedelta(seconds=max(spawn_timeout, import_timeout))
        )
        self._waiters: dict[UUID, OperationWaiter] = {}
        self._waiters_lock = Lock()

    @property
    def config(self) -> ContreeConfig:
        """Current client configuration."""
        return self._config

    async def _get_token_info(self, refresh: bool = False) -> WhoAmI:
        if refresh or self._token_info is None:
            self._token_info = await self._api.whoami()
            self._warn_token_expiration(self._token_info)
        return self._token_info

    def _warn_token_expiration(self, token_info: WhoAmI) -> None:
        if token_info.token_expiration is None:
            return
        remaining = timedelta(seconds=token_info.token_expiration - time())
        if remaining < self._config.token_expiration_warning_threshold:
            hours = remaining.total_seconds() / 3600
            logger.warning(f"Token expires in {hours:.0f} hours")

    def _warn_if_timeout_exceeds_limit(self, timeout: float, limit_key: str) -> None:
        if self._token_info is None:
            return
        limit = self._token_info.limits.get(limit_key)
        if limit is not None and timeout > limit:
            logger.warning(f"Timeout {timeout:.0f}s exceeds {limit_key}={limit}")

    @staticmethod
    def _create_api_client(config: ContreeConfig) -> ContreeClient:
        return ContreeClient(
            auth=config.auth,
            transport_timeout=config.transport_timeout,
        )

    # operations management

    async def _get_operation_waiter(self, operation_uuid: UUID | str) -> OperationWaiter:
        if isinstance(operation_uuid, str):
            operation_uuid = UUID(operation_uuid)
        if operation_uuid not in self._waiters:
            async with self._waiters_lock:
                self._waiters[operation_uuid] = OperationWaiter(client=self, operation_id=operation_uuid)
        return self._waiters[operation_uuid]

    # todo think about removing them later

    async def _start_operation(self, request: ImageImportRequest | InstanceSpawnRequest) -> UUID:
        start_method, circuit_retryer = self._operations[type(request)]
        return UUID(await circuit_retryer(partial(start_method, request)))

    async def _wait_operation(
        self,
        operation_uuid: UUID | str,
        timeout: float | None = None,
    ) -> tuple[EventDataCompletion, EventDataExit | None]:
        if isinstance(operation_uuid, str):
            operation_uuid = UUID(operation_uuid)
        timeout = timeout or self.config.operation_timeout
        waiter = await self._get_operation_waiter(operation_uuid)
        return await waiter.wait_for_result(operation_timeout=timeout)
