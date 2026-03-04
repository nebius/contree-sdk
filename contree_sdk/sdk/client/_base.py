from __future__ import annotations

import logging
from asyncio import Event, shield, sleep
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID

from typing_extensions import TypeVar

from contree_sdk._internals.client.client import ContreeClient
from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk._internals.models.instance import InstanceOperationResult, InstanceSpawnRequest
from contree_sdk._internals.utils.circuit_retryer import CircuitRetryer
from contree_sdk._internals.utils.other import get_wait_interval
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import (
    CancelledOperationError,
    FailedOperationError,
    NotFoundError,
    OperationTimedOutError,
    WrongOperationTypeError,
)
from contree_sdk.sdk.exceptions.api import TooManyRequestsError
from contree_sdk.sdk.objects.image._base import _ContreeImageBase
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
            base_url: API server URL. Ignored if config is provided.
            token: Authentication token. Ignored if config is provided.

        Raises:
            ValueError: If config is provided along with base_url or token.

        """
        if config is None:
            config = ContreeConfig()
            if token is not None:
                config = replace(config, token=token)
            if base_url is not None:
                config = replace(config, base_url=base_url)
        else:
            if token is not None:
                raise ValueError("token must be passed via config when config is provided")
            if base_url is not None:
                raise ValueError("base_url must be passed via config when config is provided")

        config = config._load_field_from_env("token")
        config = config._load_field_from_env("base_url")

        self._api: ContreeClient = self._create_api_client(config)
        self._config = config
        exceptions = [TooManyRequestsError]
        self._operations = {
            ImageImportRequest: (self._api.start_import_image, CircuitRetryer(exceptions=exceptions)),
            InstanceSpawnRequest: (self._api.spawn_instance, CircuitRetryer(exceptions=exceptions)),
        }

    @property
    def config(self) -> ContreeConfig:
        """Current client configuration."""
        return self._config

    @staticmethod
    def _create_api_client(config: ContreeConfig) -> ContreeClient:
        return ContreeClient(
            token=config.token,
            base_url=config.base_url,
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
        resp = None
        finished = False
        final_statuses = {OperationStatus.FAILED, OperationStatus.SUCCESS, OperationStatus.CANCELLED}
        not_founds_num = 0
        async with self._operation_canceller(operation_uuid) as finished_event:
            while not finished:
                if spent > timeout:
                    raise OperationTimedOutError(operation_uuid=operation_uuid)
                spent = (datetime.now() - started).total_seconds()
                try:
                    resp = await self._api.get_operation_status(operation_uuid)
                except NotFoundError:
                    if not_founds_num >= self.config.operation_poll_not_found_limit:
                        raise
                    resp = None
                not_founds_num += int(resp is None)
                kind_str = ""
                if resp is not None:
                    kind_str = resp.kind + " "
                    if not isinstance(resp.metadata, result_type):
                        raise WrongOperationTypeError(
                            operation_uuid=operation_uuid,
                            expected=result_type,
                            actual=type(resp.metadata),
                        )
                    finished = resp.status in final_statuses
                    if finished:
                        finished_event.set()
                        break

                interval = min(
                    get_wait_interval(self.config, spent / timeout),
                    timeout - spent + self.config.operation_poll_secs_min,
                )
                logger.debug(f"Sleeping for {interval:0.2f} seconds for {kind_str}operation {operation_uuid}")
                await sleep(interval)

        if resp is None:
            raise RuntimeError("Operation response is None")
        if resp.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=operation_uuid)
        if resp.status == OperationStatus.FAILED:
            raise FailedOperationError(operation_uuid=operation_uuid, error=resp.error or "Unknown error")
        if resp.metadata is None or resp.result is None:
            raise RuntimeError("Operation completed but metadata or result is None")

        return resp.metadata, resp.result
