from __future__ import annotations

import logging
from asyncio import Event, shield, sleep
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from datetime import datetime, timedelta
from functools import partial
from time import time
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import TypeVar

from contree_sdk._internals.client.client import ContreeClient
from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk._internals.models.instance import InstanceOperationResult, InstanceSpawnRequest
from contree_sdk._internals.models.operation import OperationModel
from contree_sdk._internals.utils.circuit_retrier import CircuitRetrier
from contree_sdk._internals.utils.other import get_wait_interval
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import (
    CancelledOperationError,
    FailedOperationError,
    NotFoundError,
    OperationTimedOutError,
    WrongOperationTypeError,
)
from contree_sdk.sdk.exceptions.api import (
    ApiTimeoutError,
    ContreeApiError,
    EventStreamError,
    ForbiddenError,
    TooManyRequestsError,
)
from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.utils.models.auth import WhoAmI
from contree_sdk.utils.models.operation import OperationStatus


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
        exceptions = [TooManyRequestsError, ApiTimeoutError]
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

    async def _start_operation(self, request: ImageImportRequest | InstanceSpawnRequest) -> UUID:
        start_method, circuit_retryer = self._operations[type(request)]
        return UUID(await circuit_retryer(partial(start_method, request)))

    @asynccontextmanager
    async def _operation_canceller(self, operation_uuid: UUID):
        done = Event()
        try:
            yield done
        finally:
            if not done.is_set():
                with suppress(ContreeApiError):
                    await shield(self._cancel_operation(operation_uuid=operation_uuid))

    async def _cancel_operation(self, operation_uuid: UUID):
        await self._api.cancel_operation(operation_uuid)

    async def _wait_operation(
        self,
        operation_uuid: UUID | str,
        result_type: type[_OperationResultT],
        timeout: float | None = None,
    ) -> tuple[_OperationResultT, InstanceOperationResult]:
        if isinstance(operation_uuid, str):
            operation_uuid = UUID(operation_uuid)
        started = datetime.now()
        spent = 0
        timeout = timeout or self.config.operation_timeout
        not_founds_num = 0
        last_event_id = -1

        async with self._operation_canceller(operation_uuid) as finished_event:
            while True:
                if spent > timeout:
                    raise OperationTimedOutError(operation_uuid=operation_uuid)
                spent = (datetime.now() - started).total_seconds()
                resp = None

                try:
                    async for item in self._api.stream_operation_events(operation_uuid, since=last_event_id):
                        last_event_id = item.id
                except (NotFoundError, ForbiddenError, EventStreamError):
                    pass

                try:
                    resp = await self._api.get_operation_status(operation_uuid)
                except NotFoundError:
                    if (not_founds_num := not_founds_num + 1) >= self.config.operation_poll_not_found_limit:
                        raise
                result = self._extract_operation_result(operation_uuid, resp, result_type)
                if result is not None:
                    finished_event.set()
                    return result

                interval = min(
                    get_wait_interval(self.config, spent / timeout),
                    timeout - spent + self.config.operation_poll_secs_min,
                )
                logger.debug(
                    f"Sleeping for {interval:0.2f} seconds for {result_type.__name__} operation {operation_uuid}"
                )
                await sleep(interval)

    @staticmethod
    def _extract_operation_result(
        operation_uuid: UUID,
        resp: OperationModel | None,
        result_type: type[_OperationResultT],
    ) -> tuple[_OperationResultT, InstanceOperationResult] | None:
        if resp is None:
            return None
        if not isinstance(resp.metadata, result_type):
            raise WrongOperationTypeError(
                operation_uuid=operation_uuid,
                expected=result_type,
                actual=type(resp.metadata),
            )
        if resp.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=operation_uuid)
        if resp.status == OperationStatus.FAILED:
            raise FailedOperationError(operation_uuid=operation_uuid, error=resp.error or "Unknown error")
        if resp.status != OperationStatus.SUCCESS:
            return None
        if resp.result is None:
            raise RuntimeError("Operation completed but result is None")
        return resp.metadata, resp.result
