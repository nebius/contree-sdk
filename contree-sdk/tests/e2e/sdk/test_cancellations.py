from asyncio import get_event_loop, sleep
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from pytest_mock import MockerFixture, MockType

from contree_sdk import Contree, ContreeSync
from contree_sdk.api.models.operation import OperationStatus
from contree_sdk.sdk.client._base import _ContreeBase
from tests.utils.interrupter import interrupter


IMPORT_URL = "docker://ghcr.io/linuxserver/code-server:latest"


async def _get_operation_id_from_spy(spy_obj: MockType):
    while spy_obj.called is False:
        await sleep(0.01)
    return spy_obj.call_args.kwargs["operation_uuid"]


async def _wait_cancelled(operation_id: UUID, contree: _ContreeBase):
    started = datetime.now()
    while datetime.now() - started < timedelta(seconds=3):
        operation = await contree._api.get_operation_status(operation_id)
        if operation.status == OperationStatus.CANCELLED:
            return
        await sleep(0.1)
    raise AssertionError("Operation was not cancelled")


async def test_cancel_import(contree: Contree, mocker: MockerFixture):
    spy_wait = mocker.spy(contree, "_wait_operation")

    task = get_event_loop().create_task(contree.images.pull(IMPORT_URL))
    operation_id = await _get_operation_id_from_spy(spy_wait)
    task.cancel()
    await _wait_cancelled(operation_id, contree)


async def test_cancel_import_s(contree: Contree, contree_s: ContreeSync, mocker: MockerFixture):
    spy_wait = mocker.spy(contree_s, "_wait_operation")
    with pytest.raises(KeyboardInterrupt), interrupter(0.5):
        contree_s.images.pull(IMPORT_URL)
    operation_id = spy_wait.call_args.kwargs["operation_uuid"]
    await _wait_cancelled(operation_id, contree)
