from __future__ import annotations

import logging
import os
from asyncio import Event, shield, sleep
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from random import uniform
from typing import TYPE_CHECKING
from uuid import UUID

from httpx import HTTPError
from typing_extensions import TypeVar

from contree_sdk._internals.client.client import ContreeClient
from contree_sdk._internals.models.instance import InstanceOperationResult
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.client._registry import RelationsRegistry
from contree_sdk.sdk.exceptions import (
    CancelledOperationError,
    FailedOperationError,
    OperationTimedOutError,
    WrongOperationTypeError,
    wrap_api_exception,
)
from contree_sdk.utils.models.operation import OperationStatus


if TYPE_CHECKING:
    from contree_sdk.sdk.managers.files._base import _FilesBaseManager
    from contree_sdk.sdk.managers.images._base import _ImagesBaseManager

_OperationResultT = TypeVar("_OperationResultT")


class _ContreeBase:
    files: _FilesBaseManager
    images: _ImagesBaseManager

    def __init__(self, config: ContreeConfig | None = None, *, token: str | None = None):
        if config is None:
            config = ContreeConfig()
            if token is not None:
                config = replace(config, token=token)
        else:
            assert token is None, "config is not empty, token should be passed through config itself"

        if config.token in os.environ:
            logging.info(f"Loading token from environment variable {config.token}")
            config = replace(config, token=os.environ[config.token])

        self._api: ContreeClient = self._create_api_client(config)
        self._config = replace(config, token="<hidden>")
        self._images_relations = RelationsRegistry(keep_n=self._config.images_relations_registry_size)

    @property
    def config(self) -> ContreeConfig:
        return self._config

    def _create_api_client(self, config: ContreeConfig) -> ContreeClient:
        return ContreeClient(
            token=config.token,
            base_url=config.base_url,
            transport_timeout=config.transport_timeout,
        )

    @asynccontextmanager
    async def _operation_canceller(self, operation_uuid: UUID):
        done = Event()
        try:
            yield done
        finally:
            if not done.is_set():
                await shield(self._cancel_operation(operation_uuid=operation_uuid))

    async def _cancel_operation(self, operation_uuid: UUID):
        with self._wrap_api_call():
            await self._api.cancel_operation(operation_uuid)

    async def _wait_operation(
        self,
        operation_uuid: UUID | str,
        result_type: type[_OperationResultT],
        timeout: float | None = None,
    ) -> tuple[_OperationResultT, InstanceOperationResult]:
        started = datetime.now()
        spent = 0
        timeout = timeout or self.config.operation_timeout
        resp = None
        finished = False
        final_statuses = {OperationStatus.FAILED, OperationStatus.SUCCESS, OperationStatus.CANCELLED}
        async with self._operation_canceller(operation_uuid) as finished_event:
            while not finished:
                if spent > timeout:
                    raise OperationTimedOutError(operation_uuid=operation_uuid)
                spent = (datetime.now() - started).total_seconds()
                with self._wrap_api_call():
                    resp = await self._api.get_operation_status(operation_uuid)
                if not isinstance(resp.metadata, result_type):
                    raise WrongOperationTypeError(
                        operation_uuid=operation_uuid,
                        expected=result_type,
                        actual=type(resp.metadata),
                    )
                interval = min(
                    self._get_interval(spent / timeout), timeout - spent + self.config.operation_poll_secs_min
                )
                finished = resp.status in final_statuses
                if finished:
                    finished_event.set()
                    break

                logging.info(f"Sleeping for {interval:0.2f} seconds for {resp.kind} operation {operation_uuid}")
                await sleep(interval)

        if resp.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=operation_uuid)
        if resp.status == OperationStatus.FAILED:
            raise FailedOperationError(operation_uuid=operation_uuid, error=resp.error)

        return resp.metadata, resp.result

    def _get_interval(self, progress_ration: float) -> float:
        progress_ration = progress_ration ** (1 / self.config.operation_poll_secs_backoff_grow)
        mid = 0.5
        jitter_size = 0.1 + 0.4 * (1 - 2 * abs(progress_ration - mid))
        progress_ration = progress_ration * (1 + uniform(-jitter_size, jitter_size))
        res = self.config.operation_poll_secs_min + progress_ration * (
            self.config.operation_poll_secs_max - self.config.operation_poll_secs_min
        )
        return max(self.config.operation_poll_secs_min, min(res, self.config.operation_poll_secs_max))

    @contextmanager
    def _wrap_api_call(self):
        try:
            yield
        except HTTPError as exc:
            raise wrap_api_exception(exc).with_traceback(exc.__traceback__) from exc


@dataclass
class OperationControl:
    finished: bool = False

    def done(self):
        self.finished = True
