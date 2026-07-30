from __future__ import annotations

import logging
from asyncio import Lock
from dataclasses import replace
from datetime import timedelta
from functools import partial
from time import time
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID
from weakref import WeakValueDictionary

from contree_client.base import ContreeAsyncClient
from contree_client.models import EventDataCompletion, EventDataExit, ImageImportRegistry

from contree_sdk._internals.client.provider import TransportProvider
from contree_sdk._internals.io.operation_waiter import MAIN_SPID, OperationWaiter
from contree_sdk._internals.lib.helpers import convert_data_to_type
from contree_sdk._internals.utils.circuit_retrier import CircuitRetrier
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import UnknownContreeError
from contree_sdk.sdk.exceptions.api import (
    ApiTimeoutError,
    ContreeTransportError,
    EventStreamInterruptedError,
    NotFoundError,
    TooEarlyError,
    TooManyRequestsError,
)
from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.utils.models.auth import WhoAmI


if TYPE_CHECKING:
    from contree_sdk.sdk.managers.files._base import _FilesBaseManager
    from contree_sdk.sdk.managers.images._base import _ImagesBaseManager


logger = logging.getLogger(__name__)


class _ContreeBase:
    files: _FilesBaseManager
    """Manager for file operations."""
    images: _ImagesBaseManager[_ContreeImageBase]
    """Manager for image operations."""

    _prefer_sync_transport: ClassVar[bool] = False

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

        self._transport = self._create_transport_provider(config)
        self._config = config
        self._token_info: WhoAmI | None = None
        start_exceptions = [TooManyRequestsError, ApiTimeoutError]
        stream_exceptions = [
            TooManyRequestsError,
            ApiTimeoutError,
            ContreeTransportError,
            NotFoundError,
            TooEarlyError,
            EventStreamInterruptedError,
        ]
        import_timeout = config.operation_import_timeout or config.operation_timeout
        spawn_timeout = config.operation_run_timeout or config.operation_timeout
        self._import_retrier = CircuitRetrier(
            exceptions=start_exceptions, retry_timeout=timedelta(seconds=import_timeout)
        )
        self._spawn_retrier = CircuitRetrier(
            exceptions=start_exceptions, retry_timeout=timedelta(seconds=spawn_timeout)
        )
        self._default_retrier = CircuitRetrier(
            exceptions=stream_exceptions, retry_timeout=timedelta(seconds=max(spawn_timeout, import_timeout))
        )
        self._waiters: WeakValueDictionary[UUID, OperationWaiter] = WeakValueDictionary()
        self._waiters_lock = Lock()

    @property
    def config(self) -> ContreeConfig:
        """Current client configuration."""
        return self._config

    @property
    def _api(self) -> ContreeAsyncClient:
        return self._transport.get()

    async def _get_token_info(self, refresh: bool = False) -> WhoAmI:
        if refresh or self._token_info is None:
            self._token_info = convert_data_to_type((await self._api.whoami()).to_dict(), WhoAmI)
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

    def _create_transport_provider(self, config: ContreeConfig) -> TransportProvider:
        sync_transport_mode = config.sync_transport_mode or ("blocking" if self._prefer_sync_transport else "thread")
        return TransportProvider(
            auth=config.auth,
            transport_timeout=config.transport_timeout,
            transport=config.transport,
            sync_transport_mode=sync_transport_mode,
            prefer_sync_transport=self._prefer_sync_transport,
        )

    # operations management

    async def _start_import(self, registry: ImageImportRegistry, *, tag: str | None, timeout: int) -> UUID:
        return UUID(await self._import_retrier(partial(self._api.import_image, registry, tag=tag, timeout=timeout)))

    async def _start_spawn(self, **request: Any) -> UUID:
        response = await self._spawn_retrier(partial(self._api.spawn_instance, **request))
        if not isinstance(response.uuid, str):
            raise UnknownContreeError(exception=ValueError(f"spawn response has no operation uuid: {response}"))
        return UUID(response.uuid)

    async def _get_operation_waiter(self, operation_uuid: UUID | str) -> OperationWaiter:
        if isinstance(operation_uuid, str):
            operation_uuid = UUID(operation_uuid)
        async with self._waiters_lock:
            waiter = self._waiters.get(operation_uuid)
            if waiter is None:
                waiter = OperationWaiter(client=self, operation_id=operation_uuid)
                self._waiters[operation_uuid] = waiter
            return waiter

    async def _wait_operation(
        self,
        operation_uuid: UUID | str,
        timeout: float | None = None,
        spid: int | None = MAIN_SPID,
    ) -> tuple[EventDataCompletion, EventDataExit | None]:
        if isinstance(operation_uuid, str):
            operation_uuid = UUID(operation_uuid)
        timeout = timeout or self.config.operation_timeout
        waiter = await self._get_operation_waiter(operation_uuid)
        return await waiter.wait_for_result(operation_timeout=timeout, spid=spid)
